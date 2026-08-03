#!/usr/bin/env python3
"""
CLI Restore Script for KAI Assistant SQLite Database.
Usage:
  python scripts/restore.py list
  python scripts/restore.py restore <backup_filename>
"""
import glob
import os
import shutil
import sys
from pathlib import Path

BACKUP_DIR = Path("/data/backups")
DB_PATH = Path("/data/kai.db")


def list_backups():
    backups = sorted(glob.glob(str(BACKUP_DIR / "kai_backup_*.db")))
    if not backups:
        print("No backups found in /data/backups/")
        return
    print("Available backups:")
    for b in backups:
        size = os.path.getsize(b)
        print(f"  - {os.path.basename(b)} ({size / 1024:.1f} KB)")


def restore_backup(backup_name: str):
    target = BACKUP_DIR / backup_name if not backup_name.startswith("/") else Path(backup_name)
    if not target.exists():
        print(f"Error: Backup file '{target}' does not exist.")
        sys.exit(1)

    print(f"Restoring database from '{target}' to '{DB_PATH}'...")
    if DB_PATH.exists():
        safety_copy = DB_PATH.with_suffix(".pre_restore.bak")
        shutil.copy2(DB_PATH, safety_copy)
        print(f"Safety copy of current DB created at '{safety_copy}'")

    shutil.copy2(target, DB_PATH)
    print("Database restored successfully.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "list":
        list_backups()
    elif cmd == "restore" and len(sys.argv) >= 3:
        restore_backup(sys.argv[2])
    else:
        print(__doc__)
