"""04:00 job — copy remote public schema tables into local lens schema."""

from __future__ import annotations

import logging
from pathlib import Path

from collector.db import (
    execute_sql_file,
    list_remote_public_tables,
    local_connection,
    log_job_run,
    remote_connection,
)
from collector.lens_stroymonitoring_purge import purge_reports
from collector.table_sync import sync_table

logger = logging.getLogger(__name__)

JOB_NAME = "lens_sync"
REPORTS_GEOM_SQL = Path(__file__).resolve().parents[2] / "sql" / "08_reports_geom.sql"


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started lens sync")

    total_rows = 0
    tables_synced = 0
    purged = 0

    try:
        with remote_connection() as remote_conn, local_connection() as local_conn:
            tables = list_remote_public_tables(remote_conn)
            if not tables:
                logger.warning("No tables found in remote public schema")

            for table_name in tables:
                count = sync_table(
                    remote_conn,
                    local_conn,
                    "public",
                    table_name,
                    "lens",
                    table_name,
                )
                total_rows += count
                tables_synced += 1
                logger.info("Synced lens.%s: %s rows", table_name, count)

            # Keep reports.geom maintained after each sync cycle.
            if REPORTS_GEOM_SQL.exists():
                execute_sql_file(local_conn, REPORTS_GEOM_SQL)
                logger.info("Applied SQL migration: %s", REPORTS_GEOM_SQL.name)
            else:
                logger.warning("SQL migration file not found: %s", REPORTS_GEOM_SQL)

            with local_conn.cursor() as cur:
                purged = purge_reports(cur)

        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                f"Synced {tables_synced} tables, {total_rows} rows, purged {purged} reports",
                rows_affected=total_rows,
                run_id=run_id,
            )
        logger.info(
            "lens_sync finished: %s tables, %s rows, purged %s reports",
            tables_synced,
            total_rows,
            purged,
        )

    except Exception as exc:
        logger.exception("lens_sync job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
