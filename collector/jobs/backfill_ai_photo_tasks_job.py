"""One-time backfill crm.tasks from genplan.photo_meta (AI disruption photos)."""

from __future__ import annotations

import logging

from collector.crm_photo_task_sync import sync_ai_photo_tasks
from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

JOB_NAME = "backfill_ai_photo_tasks"


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started AI photo task backfill")

    try:
        with local_connection() as conn:
            with conn.cursor() as cur:
                result = sync_ai_photo_tasks(cur)

        message = (
            f"inserted={result.inserted} updated={result.updated} "
            f"anchored={result.linked}"
        )
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=result.inserted,
                run_id=run_id,
            )
        logger.info("backfill_ai_photo_tasks finished: %s", message)

    except Exception as exc:
        logger.exception("backfill_ai_photo_tasks job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
