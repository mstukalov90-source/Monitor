"""04:00 job (after lens_sync) — copy web_geo boundaries_aip into stroymonitoring."""

from __future__ import annotations

import logging

from collector.config import (
    STROYMONITORING_LOCAL_SCHEMA,
    STROYMONITORING_LOCAL_TABLE,
    STROYMONITORING_REMOTE_SCHEMA,
    STROYMONITORING_REMOTE_TABLE,
)
from collector.db import local_connection, log_job_run, web_geo_connection
from collector.table_sync import sync_table

logger = logging.getLogger(__name__)

JOB_NAME = "stroymonitoring_sync"


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started stroymonitoring sync")

    try:
        with web_geo_connection() as remote_conn, local_connection() as local_conn:
            count = sync_table(
                remote_conn,
                local_conn,
                STROYMONITORING_REMOTE_SCHEMA,
                STROYMONITORING_REMOTE_TABLE,
                STROYMONITORING_LOCAL_SCHEMA,
                STROYMONITORING_LOCAL_TABLE,
            )

        qualified = f"{STROYMONITORING_LOCAL_SCHEMA}.{STROYMONITORING_LOCAL_TABLE}"
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                f"Synced {qualified}: {count} rows",
                rows_affected=count,
                run_id=run_id,
            )
        logger.info("stroymonitoring_sync finished: %s rows in %s", count, qualified)

    except Exception as exc:
        logger.exception("stroymonitoring_sync job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
