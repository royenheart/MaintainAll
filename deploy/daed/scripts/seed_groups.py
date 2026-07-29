#!/usr/bin/env python3
"""
Seed / upsert daed outbound groups from config/groups.txt into wing.db.

Same logic as daed-config-sync (runs automatically on docker compose).
Use this for a one-shot update without rebuilding the sync image:

    python3 scripts/seed_groups.py
    docker restart daed

Groups defined in config/private.conf (git-ignored DSL) are included too.

Does NOT attach nodes after first seed — add/replace them in the Web UI.
Empty fixed groups get exactly one node cloned from proxy (dae constraint).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

VALID_POLICIES = {"random", "fixed", "min", "min_avg10", "min_moving_avg"}


def parse_groups(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        while len(parts) < 3:
            parts.append("")
        name, policy, param = parts[0], parts[1], parts[2]
        if not name or not policy:
            print(f"skip invalid line: {raw}", file=sys.stderr)
            continue
        if policy not in VALID_POLICIES:
            print(f"skip unknown policy '{policy}' for '{name}'", file=sys.stderr)
            continue
        rows.append((name, policy, param))
    return rows


def expand_private_groups(private_conf: Path) -> list[tuple[str, str, str]]:
    awk_script = (
        Path(__file__).resolve().parent / "daed-config-sync" / "expand-private.awk"
    )
    try:
        result = subprocess.run(
            [
                "awk",
                "-v",
                "mode=groups",
                "-f",
                str(awk_script),
                str(private_conf),
                str(private_conf),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"warn: failed to expand {private_conf}: {exc}", file=sys.stderr)
        return []
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    rows: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split("|")]
        while len(parts) < 3:
            parts.append("")
        rows.append((parts[0], parts[1], parts[2]))
    return rows


def seed_groups(db_path: Path, groups_file: Path) -> int:
    if not db_path.is_file():
        print(f"Error: wing.db not found at {db_path}", file=sys.stderr)
        return 1
    if not groups_file.is_file():
        print(f"Error: groups file not found at {groups_file}", file=sys.stderr)
        return 1

    rows = parse_groups(groups_file)
    private_conf = db_path.parent / "private.conf"
    if private_conf.is_file():
        rows += expand_private_groups(private_conf)
    if not rows:
        print("No groups defined.")
        return 0

    conn = sqlite3.connect(str(db_path))
    created = updated = unchanged = 0

    for name, policy, param in rows:
        cur = conn.execute(
            "SELECT id, policy FROM groups WHERE name = ? LIMIT 1", (name,)
        )
        row = cur.fetchone()
        if not row:
            conn.execute(
                "INSERT INTO groups (name, policy, version) VALUES (?, ?, 0)",
                (name, policy),
            )
            gid = conn.execute(
                "SELECT id FROM groups WHERE name = ?", (name,)
            ).fetchone()[0]
            created += 1
            print(f"created group {name} (id={gid} policy={policy})")
        else:
            gid, old_policy = row
            if old_policy != policy:
                conn.execute(
                    "UPDATE groups SET policy = ?, version = version + 1 WHERE id = ?",
                    (policy, gid),
                )
                updated += 1
                print(f"updated group {name} policy ({old_policy} -> {policy})")
            else:
                unchanged += 1

        if policy == "fixed":
            idx = param if param.isdigit() else "0"
            pcur = conn.execute(
                "SELECT value FROM group_policy_params "
                "WHERE group_id = ? AND key = '' LIMIT 1",
                (gid,),
            ).fetchone()
            if not pcur:
                conn.execute(
                    "INSERT INTO group_policy_params (key, value, group_id) "
                    "VALUES ('', ?, ?)",
                    (idx, gid),
                )
                conn.execute(
                    "UPDATE groups SET version = version + 1 WHERE id = ?", (gid,)
                )
                print(f"  set fixed index={idx} for {name}")
            elif pcur[0] != idx:
                conn.execute(
                    "UPDATE group_policy_params SET value = ? "
                    "WHERE group_id = ? AND key = ''",
                    (idx, gid),
                )
                conn.execute(
                    "UPDATE groups SET version = version + 1 WHERE id = ?", (gid,)
                )
                print(f"  updated fixed index ({pcur[0]} -> {idx}) for {name}")
        else:
            orphan = conn.execute(
                "SELECT COUNT(*) FROM group_policy_params WHERE group_id = ?",
                (gid,),
            ).fetchone()[0]
            if orphan:
                conn.execute(
                    "DELETE FROM group_policy_params WHERE group_id = ?", (gid,)
                )
                conn.execute(
                    "UPDATE groups SET version = version + 1 WHERE id = ?", (gid,)
                )
                print(f"  cleared policy params for {name}")

        # Seed exactly one node into empty sticky groups (fixed allows only 1).
        if name != "proxy":
            ncount = conn.execute(
                "SELECT COUNT(*) FROM group_nodes WHERE group_id = ?", (gid,)
            ).fetchone()[0]
            scount = conn.execute(
                "SELECT COUNT(*) FROM group_subscriptions WHERE group_id = ?",
                (gid,),
            ).fetchone()[0]
            if ncount == 0 and scount == 0:
                proxy = conn.execute(
                    "SELECT id FROM groups WHERE name = 'proxy' LIMIT 1"
                ).fetchone()
                if not proxy:
                    print(
                        f"  warn: group {name} is empty and proxy not found",
                        file=sys.stderr,
                    )
                else:
                    pid = proxy[0]
                    pick = conn.execute(
                        "SELECT n.id, n.name FROM nodes n "
                        "WHERE n.subscription_id IN ("
                        "  SELECT subscription_id FROM group_subscriptions "
                        "  WHERE group_id = ?"
                        ") OR n.id IN ("
                        "  SELECT node_id FROM group_nodes WHERE group_id = ?"
                        ") ORDER BY CASE n.protocol "
                        "  WHEN 'anytls' THEN 0 WHEN 'tuic' THEN 1 ELSE 2 END, "
                        "n.id LIMIT 1",
                        (pid, pid),
                    ).fetchone()
                    if not pick:
                        pick = conn.execute(
                            "SELECT id, name FROM nodes ORDER BY id LIMIT 1"
                        ).fetchone()
                    if pick:
                        conn.execute(
                            "INSERT OR IGNORE INTO group_nodes "
                            "(group_id, node_id) VALUES (?, ?)",
                            (gid, pick[0]),
                        )
                        conn.execute(
                            "UPDATE groups SET version = version + 1 WHERE id = ?",
                            (gid,),
                        )
                        print(
                            f"  seeded {name} with 1 node: "
                            f"{pick[1]} (id={pick[0]})"
                        )
                    else:
                        print(
                            f"  warn: group {name} empty and no nodes to seed",
                            file=sys.stderr,
                        )

    conn.commit()
    print(
        f"\ngroups sync: created={created} updated={updated} unchanged={unchanged}"
    )
    for gid, gname, gpolicy in conn.execute(
        "SELECT id, name, policy FROM groups ORDER BY id"
    ):
        print(f"  {gid}|{gname}|{gpolicy}")
    conn.close()
    print("\nRestart daed to apply: docker restart daed")
    return 0


if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    daed_dir = script_dir.parent
    default_db = daed_dir / "config" / "wing.db"
    default_groups = daed_dir / "config" / "groups.txt"

    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_db
    groups_file = Path(sys.argv[2]) if len(sys.argv) > 2 else default_groups
    sys.exit(seed_groups(db_path, groups_file))
