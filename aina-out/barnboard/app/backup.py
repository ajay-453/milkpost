#!/usr/bin/env python3
"""Barnboard database backup — atomic, dependency-free.

Uses SQLite's online .backup API (safe while the app is running), writes a
timestamped copy into a backups dir, and keeps the newest N. Run it from cron
or a scheduled task; it needs only the stdlib.

Usage:
  python3 backup.py                 # back up DB_PATH -> ./backups/, keep 7
  python3 backup.py --dir /mnt/x    # choose backup directory
  python3 backup.py --keep 14
  python3 backup.py --verify FILE   # restore-drill: open a backup read-only and
                                    # print its row counts (proves it restores)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(HERE, "barnboard.db"))
TABLES = ["cows", "milk_logs", "treatments", "breedings", "sales", "users", "sessions"]


def counts(path: str) -> dict:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {}
    for t in TABLES:
        try:
            out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.Error:
            out[t] = "-"
    con.close()
    return out


def backup(dest_dir: str, keep: int) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(dest_dir, f"barnboard-{stamp}.db")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)          # online, consistent snapshot
    dst.close(); src.close()
    # rotate: keep the newest `keep`
    backups = sorted(f for f in os.listdir(dest_dir)
                     if f.startswith("barnboard-") and f.endswith(".db"))
    for old in backups[:-keep]:
        os.remove(os.path.join(dest_dir, old))
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(HERE, "backups"))
    ap.add_argument("--keep", type=int, default=7)
    ap.add_argument("--verify", help="path to a backup file to restore-check")
    args = ap.parse_args()

    if args.verify:
        if not os.path.exists(args.verify):
            print(f"no such backup: {args.verify}", file=sys.stderr); return 1
        print(f"restore-drill OK — {args.verify} row counts: {counts(args.verify)}")
        return 0

    dest = backup(args.dir, args.keep)
    print(f"backed up {DB_PATH} -> {dest}")
    print(f"verify:   live={counts(DB_PATH)}")
    print(f"          copy={counts(dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
