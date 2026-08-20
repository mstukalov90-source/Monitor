"""22:25 job — create crm.tasks for new odh_export.ogh-disruption rows."""

from __future__ import annotations

import logging

from collector.crm_ogh_disruption_task_sync import sync_ogh_disruption_tasks
from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

JOB_NAME = "ogh_disruption_crm_tasks"


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(
            conn, JOB_NAME, "running", "Started ogh-disruption CRM task sync"
        )

    try:
        with local_connection() as conn:
            with conn.cursor() as cur:
                result = sync_ogh_disruption_tasks(cur)

        message = f"inserted={result.inserted} anchored={result.linked}"
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=result.inserted,
                run_id=run_id,
            )
        logger.info("%s finished: %s", JOB_NAME, message)

    except Exception as exc:
        logger.exception("%s job failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
