#!/usr/bin/env python3
"""
Export daed/dae configuration from wing.db to text files.

Usage:
    python3 export_config.py [output_dir]

Output files:
    global.conf   - Global dae config
    dns.conf      - DNS config
    routing.conf  - Routing config

The exported configs are plain text containing ONLY the inner content
(without the "global {}", "dns {}", "routing {}" wrappers).
"""

import sqlite3
import sys
import os
from pathlib import Path


def export_config(db_path: str, output_dir: str):
    """Export daed config from wing.db to text files."""
    if not os.path.exists(db_path):
        print(f"Error: wing.db not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    tables = {
        "configs": ("global", "global.conf"),
        "dns": ("dns", "dns.conf"),
        "routings": ("routing", "routing.conf"),
    }

    for table, (column, filename) in tables.items():
        cursor = conn.execute(
            f"SELECT {column} FROM {table} WHERE selected = 1"
        )
        row = cursor.fetchone()
        if not row:
            print(f"Warning: No selected {table} found, using first entry")
            cursor = conn.execute(f"SELECT {column} FROM {table} LIMIT 1")
            row = cursor.fetchone()

        if row and row[0]:
            content = row[0]
            # Strip the outer wrapper (e.g., "global { ... }" -> "...")
            content = strip_config_wrapper(content)
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w") as f:
                f.write(content)
            print(f"Exported: {filepath}")
        else:
            print(f"Warning: No {column} config found")

    # Export subscription info
    cursor = conn.execute(
        "SELECT tag, link, cron_exp, cron_enable FROM subscriptions"
    )
    subs = cursor.fetchall()
    if subs:
        sub_file = os.path.join(output_dir, "subscriptions.txt")
        with open(sub_file, "w") as f:
            for tag, link, cron, enabled in subs:
                f.write(f"tag={tag}\n")
                f.write(f"link={link}\n")
                f.write(f"cron={cron}\n")
                f.write(f"cron_enable={enabled}\n")
                f.write("---\n")
        print(f"Exported: {sub_file} ({len(subs)} subscription(s))")

    conn.close()
    print("\nExport complete.")


def strip_config_wrapper(content: str) -> str:
    """Strip the outer 'section { ... }' wrapper from dae config."""
    content = content.strip()
    # Match "section {" at start and "}" at end
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        inner = content[first_brace + 1 : last_brace].strip()
        return inner
    return content


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.join(
        os.path.dirname(script_dir), "config", "wing.db"
    )
    default_out = os.path.join(os.path.dirname(script_dir), "exported")

    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db
    output_dir = sys.argv[2] if len(sys.argv) > 2 else default_out

    os.makedirs(output_dir, exist_ok=True)
    export_config(db_path, output_dir)
