"""04:00 job — copy remote public schema tables into local lens schema."""

from __future__ import annotations

import logging

from collector.db import (
    list_remote_public_tables,
    local_connection,
    log_job_run,
    remote_connection,
)
from collector.table_sync import sync_table

logger = logging.getLogger(__name__)

JOB_NAME = "lens_sync"


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started lens sync")

    total_rows = 0
    tables_synced = 0

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

        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                f"Synced {tables_synced} tables, {total_rows} rows",
                rows_affected=total_rows,
                run_id=run_id,
            )
        logger.info("lens_sync finished: %s tables, %s rows", tables_synced, total_rows)

    except Exception as exc:
        logger.exception("lens_sync job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
