"""Scheduled CRM task sync audit with alert on gap or missing scoped tasks."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

JOB_NAME = "crm_task_sync_audit"

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.crm_task_sync_audit import (  # noqa: E402
    collect_crm_scoped,
    collect_duplicate_task_keys,
    collect_false_tasked,
    collect_split_rows,
    render_report,
)

SCOPED_COLUMNS = ("earthwork_id", "localwork_id", "avr_mos_id")


@dataclass(frozen=True)
class AuditSummary:
    total_geom: int
    total_gap: int
    false_tasked: int
    duplicate_keys: int
    zero_scoped: tuple[str, ...]
    alert: bool
    message: str


def _evaluate(
    *,
    split_rows: list,
    false_tasked: dict[str, int],
    crm_scoped: dict[str, dict[str, int]],
    duplicate_keys: list,
) -> AuditSummary:
    total_geom = sum(r.with_geom for r in split_rows)
    total_gap = sum(r.gap for r in split_rows)
    false_tasked_total = sum(false_tasked.values())
    zero_scoped = tuple(
        col for col in SCOPED_COLUMNS if crm_scoped.get(col, {}).get("total", 0) == 0
    )

    parts: list[str] = []
    if total_gap > 0:
        parts.append(f"gap={total_gap}")
    if zero_scoped:
        parts.append(f"zero_scoped={','.join(zero_scoped)}")
    if false_tasked_total > 0:
        parts.append(f"false_tasked={false_tasked_total}")
    if duplicate_keys:
        parts.append(f"duplicate_task_key={len(duplicate_keys)}")

    alert = bool(parts)
    message = "OK" if not alert else "; ".join(parts)
    return AuditSummary(
        total_geom=total_geom,
        total_gap=total_gap,
        false_tasked=false_tasked_total,
        duplicate_keys=len(duplicate_keys),
        zero_scoped=zero_scoped,
        alert=alert,
        message=message,
    )


def run(*, report_dir: Path | None = None) -> AuditSummary:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started CRM task sync audit")

    try:
        with local_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                split_rows = collect_split_rows(cur)
                false_tasked = collect_false_tasked(cur)
                crm_scoped = collect_crm_scoped(cur)
                duplicate_keys = collect_duplicate_task_keys(cur)

        summary = _evaluate(
            split_rows=split_rows,
            false_tasked=false_tasked,
            crm_scoped=crm_scoped,
            duplicate_keys=duplicate_keys,
        )

        out_dir = report_dir or (_ROOT / "reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        report_path = out_dir / f"audit_{stamp}.md"
        report_path.write_text(
            render_report(
                title=f"CRM Task Sync Audit {stamp}",
                split_rows=split_rows,
                false_tasked=false_tasked,
                crm_scoped=crm_scoped,
                duplicate_keys=duplicate_keys,
                multi_match=[],
                job_runs=[],
            ),
            encoding="utf-8",
        )

        status = "failed" if summary.alert else "success"
        log_message = f"{summary.message}; report={report_path.name}"
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                status,
                log_message,
                rows_affected=summary.total_gap,
                run_id=run_id,
            )

        if summary.alert:
            logger.error("CRM task sync audit ALERT: %s", summary.message)
        else:
            logger.info("CRM task sync audit OK (geom=%s)", summary.total_geom)

        return summary

    except Exception as exc:
        logger.exception("%s job failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
