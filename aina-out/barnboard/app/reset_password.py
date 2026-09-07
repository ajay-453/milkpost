#!/usr/bin/env python3
"""Barnboard admin password reset — the last-resort recovery when NO owner can
log in (e.g. the sole owner forgot their password). Run it on the server that
holds the database; access to that box is the credential.

Usage (from the app/ directory, with the app's Python/venv):
    python3 reset_password.py <username>            # prints a one-time reset link
    python3 reset_password.py <username> --set       # prompts for a new password directly
    python3 reset_password.py --list                 # list usernames

The reset link is opened in a browser at your Barnboard URL. If you set the
password directly, all of that user's sessions are signed out.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from app import db


def main() -> int:
    ap = argparse.ArgumentParser(description="Barnboard admin password reset")
    ap.add_argument("username", nargs="?", help="account to reset")
    ap.add_argument("--set", action="store_true",
                    help="set a new password now instead of printing a link")
    ap.add_argument("--list", action="store_true", help="list usernames and exit")
    ap.add_argument("--base-url", default="http://localhost:8000",
                    help="your Barnboard URL, used to build the reset link")
    args = ap.parse_args()

    db.init_db()
    con = db.get_db()

    if args.list:
        for r in con.execute("SELECT username, role, approved FROM users ORDER BY id"):
            flag = "owner" if r["role"] == "owner" else "helper"
            state = "active" if r["approved"] else "pending"
            print(f"  {r['username']:<20} {flag:<8} {state}")
        return 0

    if not args.username:
        ap.error("username is required (or use --list)")

    user = con.execute("SELECT * FROM users WHERE username = ?", (args.username,)).fetchone()
    if not user:
        print(f"No such user: {args.username}", file=sys.stderr)
        return 1

    if args.set:
        p1 = getpass.getpass("New password (8+ chars): ")
        if len(p1) < 8:
            print("Password too short.", file=sys.stderr)
            return 1
        if p1 != getpass.getpass("Repeat: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
        con.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                    (db.hash_password(p1), user["id"]))
        con.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        con.commit()
        print(f"Password set for {args.username}. All their sessions were signed out.")
        return 0

    token = db.create_reset(con, user["id"])
    con.commit()
    link = args.base_url.rstrip("/") + f"/reset/{token}"
    print(f"One-time reset link for {args.username} (valid {db.RESET_HOURS}h):\n\n  {link}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
