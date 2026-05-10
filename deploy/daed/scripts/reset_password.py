#!/usr/bin/env python3
"""
Reset daed web UI user password.

Usage:
    python3 reset_password.py <new-password>

Example:
    python3 reset_password.py mysecurepassword
"""

import sqlite3
import hashlib
import secrets
import sys
import os


def reset_password(db_path: str, new_password: str):
    """Reset the daed user password in wing.db."""
    if not os.path.exists(db_path):
        print(f"Error: wing.db not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)

    # Generate new JWT secret (hex string used as salt)
    jwt_secret = secrets.token_hex(32)

    # Hash: SHAKE-256 of (jwt_secret_as_string + password)
    h = hashlib.shake_256()
    h.update(jwt_secret.encode())
    h.update(new_password.encode())
    password_hash = h.hexdigest(32)

    # Check if user exists
    cursor = conn.execute("SELECT id, username FROM users LIMIT 1")
    user = cursor.fetchone()
    if not user:
        print("Error: No user found in database")
        conn.close()
        sys.exit(1)

    conn.execute(
        "UPDATE users SET password_hash = ?, jwt_secret = ? WHERE id = ?",
        (password_hash, jwt_secret, user[0]),
    )
    conn.commit()
    conn.close()

    print(f"Password reset for user '{user[1]}': {new_password}")
    print("Restart daed if it's running: docker restart daed")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.join(
        os.path.dirname(script_dir), "config", "wing.db"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 reset_password.py <new-password> [wing.db path]")
        sys.exit(1)

    db_path = default_db
    password = None

    for arg in sys.argv[1:]:
        if arg.endswith(".db") or "/" in arg:
            db_path = arg
        elif password is None:
            password = arg

    if password is None:
        print("Error: password is required")
        sys.exit(1)

    reset_password(db_path, password)
