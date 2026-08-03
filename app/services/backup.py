import glob
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

BACKUP_DIR = Path("/data/backups")
MAX_BACKUPS_RETAINED = 30


def perform_db_backup() -> str:
    """
    Executes nightly SQLite backup using sqlite3 backup API.
    Maintains 30-day retention by purging oldest backups.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"kai_backup_{timestamp}.db"

    # Extract SQLite database file path from DATABASE_URL
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        source_db_path = db_url.replace("sqlite:///", "")
    else:
        source_db_path = "/data/kai.db"

    if not os.path.exists(source_db_path):
        logger.warning(f"Source database file '{source_db_path}' does not exist yet. Creating backup directory.")
        return ""

    try:
        source_conn = sqlite3.connect(source_db_path)
        backup_conn = sqlite3.connect(str(backup_file))
        with backup_conn:
            source_conn.backup(backup_conn)
        source_conn.close()
        backup_conn.close()
        logger.info(f"Database backup created successfully at: {backup_file}")
    except Exception as err:
        logger.error(f"Error during SQLite database backup: {err}")
        # Fallback to copy
        shutil.copy2(source_db_path, backup_file)

    cleanup_old_backups()
    return str(backup_file)


def cleanup_old_backups():
    """Purges backups older than MAX_BACKUPS_RETAINED (30)."""
    try:
        backups = sorted(glob.glob(str(BACKUP_DIR / "kai_backup_*.db")))
        if len(backups) > MAX_BACKUPS_RETAINED:
            to_delete = backups[:-MAX_BACKUPS_RETAINED]
            for f in to_delete:
                os.remove(f)
                logger.info(f"Purged old backup file: {f}")
    except Exception as err:
        logger.error(f"Error cleaning up old database backups: {err}")
