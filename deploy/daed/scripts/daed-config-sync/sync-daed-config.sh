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

  selected_count="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table WHERE selected = 1;")"
  if [ "$selected_count" -lt 1 ]; then
    echo "no selected row found in table $table" >&2
    exit 1
  fi

  prepared_file="$TMP_DIR/$table.conf"
  prepare_section_file "$section" "$source_file" "$prepared_file"

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

require_file "$DB_PATH"
require_file "$CONFIG_DIR/global.conf"
require_file "$CONFIG_DIR/dns.conf"
require_file "$CONFIG_DIR/routing.conf"

sync_selected_row "configs" "global" "global" "$CONFIG_DIR/global.conf"
sync_selected_row "dns" "dns" "dns" "$CONFIG_DIR/dns.conf"
sync_selected_row "routings" "routing" "routing" "$CONFIG_DIR/routing.conf"

echo "daed config sync complete"
