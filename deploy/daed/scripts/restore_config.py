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
import sys
import os


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
