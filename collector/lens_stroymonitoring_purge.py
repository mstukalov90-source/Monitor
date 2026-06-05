"""Purge stale rows from lens.reports and stroymonitoring.boundaries_aip after sync."""

from __future__ import annotations

import logging

from psycopg2.extensions import cursor as Cursor

logger = logging.getLogger(__name__)


def ensure_purge_functions(cur: Cursor) -> None:
    """Create purge functions if missing (no-op when applied via initdb migration)."""
    cur.execute(
        """
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'stroymonitoring' AND p.proname = 'purge_boundaries_aip'
        """
    )
    if cur.fetchone() is not None:
        return

    from collector.config import LENS_STROYMONITORING_PURGE_FUNCTIONS_SQL
    from collector.db import execute_sql_file

    if not LENS_STROYMONITORING_PURGE_FUNCTIONS_SQL.exists():
        raise FileNotFoundError(
            f"Purge functions SQL not found: {LENS_STROYMONITORING_PURGE_FUNCTIONS_SQL}"
        )
    logger.info("Installing lens/stroymonitoring purge SQL functions")
    execute_sql_file(cur.connection, LENS_STROYMONITORING_PURGE_FUNCTIONS_SQL)


def purge_boundaries_aip(cur: Cursor) -> int:
    """Delete rows matching purge rules in stroymonitoring.boundaries_aip."""
    ensure_purge_functions(cur)
    cur.execute("SELECT stroymonitoring.purge_boundaries_aip()")
    deleted = cur.fetchone()[0]
    logger.info(
        "Purged %s rows from stroymonitoring.boundaries_aip",
        deleted,
    )
    return deleted


def purge_reports(cur: Cursor) -> int:
    """Delete rows matching purge rules in lens.reports."""
    ensure_purge_functions(cur)
    cur.execute("SELECT lens.purge_reports()")
    deleted = cur.fetchone()[0]
    logger.info("Purged %s rows from lens.reports", deleted)
    return deleted
