"""Backfill crm.tasks for data_mos split tables without full ETL export."""

from __future__ import annotations

import logging

from collector.crm_task_sync import CrmTaskSyncResult, sync_crm_tasks_after_etl
from collector.crm_task_sync_config import SERVICE_TASK_SYNC
from collector.data_mos_tasked import refresh_all_tasked_parents
from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

JOB_NAME = "backfill_data_mos_crm_tasks"

SERVICE_ORDER = ("items_62501", "items_62441", "items_62461", "items_2855")


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started data_mos CRM task backfill")

    try:
        totals = CrmTaskSyncResult()
        per_service: list[str] = []

        with local_connection() as conn:
            with conn.cursor() as cur:
                for service_name in SERVICE_ORDER:
                    if service_name not in SERVICE_TASK_SYNC:
                        continue
                    cfg = SERVICE_TASK_SYNC[service_name]
                    refresh_all_tasked_parents(cur, cfg.parent_table)
                    result = sync_crm_tasks_after_etl(cur, service_name)
                    totals.inserted += result.inserted
                    totals.linked += result.linked
                    totals.tasked_parents += result.tasked_parents
                    totals.sent_to_field += result.sent_to_field
                    per_service.append(
                        f"{service_name}: inserted={result.inserted} "
                        f"linked={result.linked} tasked_parents={result.tasked_parents} "
                        f"sent_to_field={result.sent_to_field}"
                    )

        message = (
            f"total inserted={totals.inserted} linked={totals.linked} "
            f"tasked_parents={totals.tasked_parents} "
            f"sent_to_field={totals.sent_to_field}; "
            + "; ".join(per_service)
        )
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=totals.inserted,
                run_id=run_id,
            )
        logger.info("%s finished: %s", JOB_NAME, message)

    except Exception as exc:
        logger.exception("%s job failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
