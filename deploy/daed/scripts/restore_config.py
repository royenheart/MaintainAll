#!/usr/bin/env python3
"""
Restore daed/dae configuration from text files to wing.db.

Usage:
    python3 restore_config.py [input_dir]

Reads from:
    config/global.conf   - Global dae config (inner content)
    config/dns.conf      - DNS config (inner content)
    config/routing.conf  - Routing config (inner content)

Wraps each in its section name and writes to wing.db.

NOTE: This does NOT restore user credentials. You will need to
reset the password after restoring:
    python3 scripts/reset_password.py
"""

import sqlite3
import subprocess
import sys
import os


PRIVATE_RULES_MARKER = "# private-rules"


def expand_private_rules(config_dir: str, known_groups: set) -> list:
    """Translate config/private.conf DSL into dae routing lines."""
    private = os.path.join(config_dir, "private.conf")
    if not os.path.exists(private):
        return []
    awk_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "daed-config-sync",
        "expand-private.awk",
    )
    try:
        result = subprocess.run(
            [
                "awk",
                "-v",
                "mode=routing",
                "-v",
                "known_groups=" + " ".join(sorted(known_groups)),
                "-f",
                awk_script,
                private,
                private,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"Warning: failed to expand {private}: {exc}")
        return []
    if result.stderr:
        print(result.stderr, end="")
    return result.stdout.splitlines()


def inject_private_rules(routing_text: str, private_lines: list) -> str:
    if not private_lines:
        return routing_text
    if not any(
        line.strip() == PRIVATE_RULES_MARKER for line in routing_text.splitlines()
    ):
        print(
            f"Warning: expanded private rules exist but no"
            f" '{PRIVATE_RULES_MARKER}' marker in routing.conf; skipping"
        )
        return routing_text

    merged = []
    for line in routing_text.splitlines():
        if line.strip() == PRIVATE_RULES_MARKER:
            merged.append(
                "# ── Private rules (private.conf, not version-controlled) ──"
            )
            merged.extend(private_lines)
        else:
            merged.append(line)
    print("Merged private rules from private.conf")
    return "\n".join(merged)


def known_group_names(db_conn, config_dir: str) -> set:
    names = set()
    try:
        names.update(
            row[0] for row in db_conn.execute("SELECT name FROM groups")
        )
    except sqlite3.Error:
        pass
    groups_txt = os.path.join(config_dir, "groups.txt")
    if os.path.exists(groups_txt):
        with open(groups_txt, "r") as f:
            for raw in f:
                name = raw.split("#", 1)[0].split("|", 1)[0].strip()
                if name:
                    names.add(name)
    return names


def restore_config(db_path: str, input_dir: str):
    """Restore daed config from text files to wing.db."""
    if not os.path.exists(db_path):
        print(f"Error: wing.db not found at {db_path}")
        sys.exit(1)

    files = {
        "global": "global.conf",
        "dns": "dns.conf",
        "routing": "routing.conf",
    }
    tables = {
        "global": ("configs", "global"),
        "dns": ("dns", "dns"),
        "routing": ("routings", "routing"),
    }

    conn = sqlite3.connect(db_path)

    for section, filename in files.items():
        filepath = os.path.join(input_dir, filename)
        if not os.path.exists(filepath):
            print(f"Warning: {filepath} not found, skipping {section}")
            continue

        with open(filepath, "r") as f:
            inner_content = f.read().strip()

        if section == "routing":
            config_dir = os.path.dirname(db_path)
            private_lines = expand_private_rules(
                config_dir, known_group_names(conn, config_dir)
            )
            inner_content = inject_private_rules(
                inner_content, private_lines
            ).strip()

        # Wrap with section header
        wrapped = f"{section} {{\n{inner_content}\n}}\n"

        table, column = tables[section]
        # Update the selected config
        cursor = conn.execute(
            f"UPDATE {table} SET {column} = ? WHERE selected = 1",
            (wrapped,),
        )
        if cursor.rowcount == 0:
            # No selected config, update the first one
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE id = 1",
                (wrapped,),
            )
        print(f"Restored: {section} from {filename}")

    conn.commit()
    conn.close()
    print("\nRestore complete. Please restart daed:")
    print("  docker restart daed")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.join(
        os.path.dirname(script_dir), "config", "wing.db"
    )
    default_in = os.path.join(os.path.dirname(script_dir), "config")

    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db
    input_dir = sys.argv[2] if len(sys.argv) > 2 else default_in

    restore_config(db_path, input_dir)
