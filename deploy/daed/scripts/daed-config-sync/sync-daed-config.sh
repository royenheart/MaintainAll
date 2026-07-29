#!/bin/sh
set -eu

CONFIG_DIR="${1:-/etc/daed}"
DB_PATH="${2:-$CONFIG_DIR/wing.db}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

require_file() {
  if [ ! -f "$1" ]; then
    echo "missing required file: $1" >&2
    exit 1
  fi
}

first_nonempty_line() {
  awk '
    /^[[:space:]]*$/ { next }
    { print; exit }
  ' "$1"
}

prepare_section_file() {
  section="$1"
  source_file="$2"
  output_file="$3"

  first_line="$(first_nonempty_line "$source_file" || true)"
  if printf '%s\n' "$first_line" | grep -Eq "^${section}[[:space:]]*\\{"; then
    cp "$source_file" "$output_file"
    return
  fi

  {
    printf '%s {\n' "$section"
    sed -e '$a\' "$source_file"
    printf '}\n'
  } >"$output_file"
}

sync_selected_row() {
  table="$1"
  column="$2"
  section="$3"
  source_file="$4"

  table_exists="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$table';")"
  if [ "$table_exists" -lt 1 ]; then
    echo "error: table '$table' missing in $DB_PATH (fresh database?)" >&2
    echo "hint: boot daed once to initialize the schema: docker compose up -d --no-deps daed" >&2
    exit 1
  fi

  prepared_file="$TMP_DIR/$table.conf"
  prepare_section_file "$section" "$source_file" "$prepared_file"

  selected_count="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table WHERE selected = 1;")"
  if [ "$selected_count" -lt 1 ]; then
    row_count="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table;")"
    if [ "$row_count" -lt 1 ]; then
      # dae-wing creates tables on first boot but no default config rows;
      # insert one so a fresh deployment can sync without manual UI steps.
      sqlite3 "$DB_PATH" "
        INSERT INTO $table (name, \"$column\", selected, version)
        VALUES ('default', CAST(readfile('$prepared_file') AS TEXT), 1, 0);
      "
      echo "initialized $table with default selected row"
      return
    fi
    first_id="$(sqlite3 "$DB_PATH" "SELECT id FROM $table ORDER BY id LIMIT 1;")"
    sqlite3 "$DB_PATH" "UPDATE $table SET selected = 1 WHERE id = $first_id;"
    echo "warn: no selected row in $table; fell back to id=$first_id" >&2
  fi

  before_version="$(sqlite3 "$DB_PATH" "SELECT version FROM $table WHERE selected = 1 LIMIT 1;")"
  sqlite3 "$DB_PATH" "
    UPDATE $table
    SET \"$column\" = CAST(readfile('$prepared_file') AS TEXT),
        version = version + CASE
          WHEN \"$column\" != CAST(readfile('$prepared_file') AS TEXT) THEN 1
          ELSE 0
        END
    WHERE selected = 1;
  "
  after_version="$(sqlite3 "$DB_PATH" "SELECT version FROM $table WHERE selected = 1 LIMIT 1;")"

  if [ "$before_version" != "$after_version" ]; then
    echo "updated $table ($before_version -> $after_version)"
  else
    echo "unchanged $table (version $after_version)"
  fi
}

# Seed / upsert outbound groups from groups.txt (nodes stay UI-managed).
# Format: name|policy|param   (# comments and blank lines ignored)
sync_groups() {
  groups_file="$1"
  if [ ! -f "$groups_file" ]; then
    echo "skip groups: $groups_file not found"
    return 0
  fi

  table_exists="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='groups';")"
  if [ "$table_exists" -lt 1 ]; then
    echo "skip groups: groups table missing (fresh DB before first daed boot?)"
    return 0
  fi

  created=0
  updated=0
  unchanged=0

  # Strip CR, comments, blanks
  while IFS= read -r raw || [ -n "$raw" ]; do
    line="$(printf '%s' "$raw" | tr -d '\r' | sed 's/#.*//;s/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue

    name="$(printf '%s' "$line" | cut -d'|' -f1 | sed 's/[[:space:]]*$//')"
    policy="$(printf '%s' "$line" | cut -d'|' -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    param="$(printf '%s' "$line" | cut -d'|' -f3 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    if [ -z "$name" ] || [ -z "$policy" ]; then
      echo "skip invalid groups line: $raw" >&2
      continue
    fi

    case "$policy" in
      random|fixed|min|min_avg10|min_moving_avg) ;;
      *)
        echo "skip unknown policy '$policy' for group '$name'" >&2
        continue
        ;;
    esac

    existing="$(sqlite3 "$DB_PATH" "SELECT id || '|' || policy FROM groups WHERE name = '$name' LIMIT 1;")"
    if [ -z "$existing" ]; then
      sqlite3 "$DB_PATH" "INSERT INTO groups (name, policy, version) VALUES ('$name', '$policy', 0);"
      gid="$(sqlite3 "$DB_PATH" "SELECT id FROM groups WHERE name = '$name' LIMIT 1;")"
      created=$((created + 1))
      echo "created group $name (id=$gid policy=$policy)"
    else
      gid="$(printf '%s' "$existing" | cut -d'|' -f1)"
      old_policy="$(printf '%s' "$existing" | cut -d'|' -f2)"
      if [ "$old_policy" != "$policy" ]; then
        sqlite3 "$DB_PATH" "UPDATE groups SET policy = '$policy', version = version + 1 WHERE id = $gid;"
        updated=$((updated + 1))
        echo "updated group $name policy ($old_policy -> $policy)"
      else
        unchanged=$((unchanged + 1))
      fi
    fi

    # fixed(N) stores index in group_policy_params (empty key, value = index)
    if [ "$policy" = "fixed" ]; then
      idx="${param:-0}"
      case "$idx" in
        ''|*[!0-9]*) idx=0 ;;
      esac
      cur="$(sqlite3 "$DB_PATH" "SELECT value FROM group_policy_params WHERE group_id = $gid AND key = '' LIMIT 1;")"
      if [ -z "$cur" ]; then
        sqlite3 "$DB_PATH" "INSERT INTO group_policy_params (key, value, group_id) VALUES ('', '$idx', $gid);"
        sqlite3 "$DB_PATH" "UPDATE groups SET version = version + 1 WHERE id = $gid;"
        echo "  set fixed index=$idx for $name"
      elif [ "$cur" != "$idx" ]; then
        sqlite3 "$DB_PATH" "UPDATE group_policy_params SET value = '$idx' WHERE group_id = $gid AND key = '';"
        sqlite3 "$DB_PATH" "UPDATE groups SET version = version + 1 WHERE id = $gid;"
        echo "  updated fixed index ($cur -> $idx) for $name"
      fi
    else
      # Non-fixed: drop leftover fixed params if any
      orphan="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM group_policy_params WHERE group_id = $gid;")"
      if [ "$orphan" -gt 0 ]; then
        sqlite3 "$DB_PATH" "DELETE FROM group_policy_params WHERE group_id = $gid;"
        sqlite3 "$DB_PATH" "UPDATE groups SET version = version + 1 WHERE id = $gid;"
        echo "  cleared policy params for $name"
      fi
    fi

    # Sticky groups referenced by routing must not be empty or dae refuses to
    # load full routing. Seed ONLY when still empty (never overwrite UI edits).
    # dae rule: policy=fixed allows exactly ONE node (no whole subscription).
    if [ "$name" != "proxy" ]; then
      ncount="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM group_nodes WHERE group_id = $gid;")"
      scount="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM group_subscriptions WHERE group_id = $gid;")"
      if [ "$ncount" -eq 0 ] && [ "$scount" -eq 0 ]; then
        proxy_id="$(sqlite3 "$DB_PATH" "SELECT id FROM groups WHERE name = 'proxy' LIMIT 1;")"
        if [ -n "$proxy_id" ]; then
          # Prefer anytls > tuic > other from proxy's subscription(s) / nodes
          pick="$(sqlite3 "$DB_PATH" "
            SELECT n.id FROM nodes n
            WHERE n.subscription_id IN (
              SELECT subscription_id FROM group_subscriptions WHERE group_id = $proxy_id
            ) OR n.id IN (
              SELECT node_id FROM group_nodes WHERE group_id = $proxy_id
            )
            ORDER BY CASE n.protocol
              WHEN 'anytls' THEN 0 WHEN 'tuic' THEN 1 ELSE 2 END, n.id
            LIMIT 1;
          ")"
          if [ -z "$pick" ]; then
            pick="$(sqlite3 "$DB_PATH" "SELECT id FROM nodes ORDER BY id LIMIT 1;")"
          fi
          if [ -n "$pick" ]; then
            sqlite3 "$DB_PATH" "INSERT OR IGNORE INTO group_nodes (group_id, node_id) VALUES ($gid, $pick);"
            sqlite3 "$DB_PATH" "UPDATE groups SET version = version + 1 WHERE id = $gid;"
            pname="$(sqlite3 "$DB_PATH" "SELECT name FROM nodes WHERE id = $pick;")"
            echo "  seeded $name with 1 node: $pname (id=$pick)"
          else
            echo "  warn: group $name empty and no nodes available to seed" >&2
          fi
        else
          echo "  warn: group $name is empty and proxy not found" >&2
        fi
      fi
    fi
  done < "$groups_file"

  echo "groups sync: created=$created updated=$updated unchanged=$unchanged"
  sqlite3 "$DB_PATH" "SELECT id, name, policy FROM groups ORDER BY id;" | sed 's/^/  /'
}

if [ ! -f "$DB_PATH" ]; then
  echo "wing.db not found at $DB_PATH; skipping sync."
  echo "daed creates it on first boot; re-run sync afterwards (docker compose up -d)."
  exit 0
fi
require_file "$CONFIG_DIR/global.conf"
require_file "$CONFIG_DIR/dns.conf"
require_file "$CONFIG_DIR/routing.conf"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
EXPAND_AWK="${EXPAND_AWK:-$SCRIPT_DIR/expand-private.awk}"

# Expand config/private.conf (git-ignored DSL: group defs + shorthand rules).
# Groups are upserted into wing.db; rules are injected into the routing config
# at the "# private-rules" marker. Private URLs land only in wing.db (also
# git-ignored), never in the tracked routing.conf.
merge_private_rules() {
  src="$1"
  priv="$2"
  out="$3"

  if [ ! -s "$priv" ]; then
    cp "$src" "$out"
    return
  fi

  if ! grep -Eq '^# private-rules[[:space:]]*$' "$src"; then
    cp "$src" "$out"
    echo "warn: expanded private rules exist but no '# private-rules' marker in $src; skipping private rules" >&2
    return
  fi

  awk -v priv="$priv" '
    /^# private-rules[[:space:]]*$/ {
      print "# ── Private rules (private.conf, not version-controlled) ──"
      while ((getline line < priv) > 0) print line
      close(priv)
      next
    }
    { print }
  ' "$src" >"$out"
  echo "merged private rules from private.conf"
}

PRIVATE_CONF="$CONFIG_DIR/private.conf"
PRIVATE_ROUTING="$TMP_DIR/private.routing"
PRIVATE_GROUPS="$TMP_DIR/private.groups"
ROUTING_MERGED="$TMP_DIR/routing.merged.conf"
: >"$PRIVATE_ROUTING"
: >"$PRIVATE_GROUPS"

if [ -f "$PRIVATE_CONF" ]; then
  known_groups="$(
    {
      if [ -f "$CONFIG_DIR/groups.txt" ]; then
        sed 's/#.*//;s/|.*//;s/[[:space:]]//g' "$CONFIG_DIR/groups.txt"
      fi
      sqlite3 "$DB_PATH" "SELECT name FROM groups;" 2>/dev/null || true
    } | awk 'NF' | sort -u | tr '\n' ' '
  )"
  awk -v mode=routing -v known_groups="$known_groups" \
    -f "$EXPAND_AWK" "$PRIVATE_CONF" "$PRIVATE_CONF" >"$PRIVATE_ROUTING"
  awk -v mode=groups -f "$EXPAND_AWK" "$PRIVATE_CONF" "$PRIVATE_CONF" \
    >"$PRIVATE_GROUPS"
fi

merge_private_rules "$CONFIG_DIR/routing.conf" "$PRIVATE_ROUTING" "$ROUTING_MERGED"

sync_selected_row "configs" "global" "global" "$CONFIG_DIR/global.conf"
sync_selected_row "dns" "dns" "dns" "$CONFIG_DIR/dns.conf"
sync_selected_row "routings" "routing" "routing" "$ROUTING_MERGED"
sync_groups "$CONFIG_DIR/groups.txt"
if [ -s "$PRIVATE_GROUPS" ]; then
  sync_groups "$PRIVATE_GROUPS"
fi

echo "daed config sync complete"
