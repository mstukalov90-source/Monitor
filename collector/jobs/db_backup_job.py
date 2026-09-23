"""Nightly pg_dump backups of the local PostGIS database.

Daily dump at 06:30 keeps 1 day (previous daily is pruned after the new one
lands); on Fridays the same run also writes a weekly dump kept for 7 days.
Dumps are custom-format (-Fc, compressed), restorable with pg_restore.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from collector.config import (
    BACKUP_DIR,
    DB_BACKUP_DAILY_KEEP_DAYS,
    DB_BACKUP_WEEKLY_KEEP_DAYS,
    LOCAL_DB,
)
from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

JOB_NAME = "db_backup"
DAILY = "daily"
WEEKLY = "weekly"
FRIDAY = 4
_FILE_PREFIX = "monitor_"


def _dump_path(backup_dir: Path, kind: str, now: datetime) -> Path:
    return backup_dir / f"{_FILE_PREFIX}{now:%Y%m%d_%H%M}.{kind}.dump"


def _pg_dump_command(target: Path) -> list[str]:
    return [
        "pg_dump",
        "-h",
        LOCAL_DB["host"],
        "-p",
        str(LOCAL_DB["port"]),
        "-U",
        LOCAL_DB["user"],
        "-Fc",
        "-f",
        str(target),
        LOCAL_DB["dbname"],
    ]


def take_backup(kind: str, backup_dir: Path, *, now: datetime | None = None) -> Path:
    """Run pg_dump into backup_dir; return the dump file path."""
    now = now or datetime.now()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = _dump_path(backup_dir, kind, now)
    env = {**os.environ, "PGPASSWORD": LOCAL_DB["password"]}
    completed = subprocess.run(
        _pg_dump_command(target),
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        stderr = (completed.stderr or "").strip()[:500]
        raise RuntimeError(f"pg_dump failed (rc={completed.returncode}): {stderr}")
    logger.info(
        "Backup written: %s (%.1f MB)", target.name, target.stat().st_size / 1_048_576
    )
    return target


def prune_backups(
    kind: str,
    keep_days: float,
    backup_dir: Path,
    *,
    now: datetime | None = None,
) -> list[Path]:
    """Delete <prefix>*.<kind>.dump files older than keep_days; return them."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=keep_days)
    deleted: list[Path] = []
    for path in sorted(backup_dir.glob(f"{_FILE_PREFIX}*.{kind}.dump")):
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            path.unlink()
            deleted.append(path)
            logger.info("Pruned old backup %s", path.name)
    return deleted


def run() -> None:
    now = datetime.now()
    kinds: list[tuple[str, float]] = [(DAILY, DB_BACKUP_DAILY_KEEP_DAYS)]
    if now.weekday() == FRIDAY:
        kinds.append((WEEKLY, DB_BACKUP_WEEKLY_KEEP_DAYS))

    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", f"Kinds: {[k for k, _ in kinds]}")

    try:
        parts: list[str] = []
        for kind, keep_days in kinds:
            target = take_backup(kind, BACKUP_DIR, now=now)
            pruned = prune_backups(kind, keep_days, BACKUP_DIR, now=now)
            parts.append(
                f"{kind}: {target.name} {target.stat().st_size / 1_048_576:.1f} MB, "
                f"pruned {len(pruned)}"
            )
        message = "; ".join(parts)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "success", message, run_id=run_id)
        logger.info("%s finished: %s", JOB_NAME, message)
    except Exception as exc:
        logger.exception("%s failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
