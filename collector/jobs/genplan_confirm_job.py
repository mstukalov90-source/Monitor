"""Send CRM snapshot photo confirms to MSI Holes genplan API.

Daily 18:30 Europe/Moscow. Limits GENPLAN_CONFIRM_LIMIT_TRUE / _FALSE (0 = none).
"""

from __future__ import annotations

import logging

from collector.config import (
    GENPLAN_CONFIRM_LIMIT_FALSE,
    GENPLAN_CONFIRM_LIMIT_TRUE,
    GENPLAN_PHOTO_CONFIRM_LOG_SQL,
    MSI_HOLES_BASE_URL,
    MSI_HOLES_CLIENT_ID,
    MSI_HOLES_CLIENT_SECRET,
    MSI_HOLES_CREDENTIALS_FILE,
    MSI_HOLES_TOKEN_ENDPOINT,
    MSI_HOLES_VERIFY_SSL,
)
from collector.db import execute_sql_file, local_connection, log_job_run
from collector.genplan_photo_confirm import (
    apply_limit,
    count_skipped_cam,
    count_skipped_null_cam,
    exclude_already_sent,
    load_false_candidates,
    load_sent_confirms,
    load_true_candidates,
    send_confirms,
)
from collector.msi_holes_client import MsiHolesClient

logger = logging.getLogger(__name__)

JOB_NAME = "genplan_confirm"


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _ensure_log_table(conn) -> None:
    if not GENPLAN_PHOTO_CONFIRM_LOG_SQL.exists():
        raise FileNotFoundError(f"SQL migration not found: {GENPLAN_PHOTO_CONFIRM_LOG_SQL}")
    execute_sql_file(conn, GENPLAN_PHOTO_CONFIRM_LOG_SQL)


def _format_message(
    *,
    sent_true: int,
    sent_false: int,
    skipped_cam: int,
    skipped_null_cam: int,
    skipped_idempotent: int,
    errors: int,
    error_details: list[str],
) -> str:
    parts = [
        f"sent_true={sent_true}",
        f"sent_false={sent_false}",
        f"skipped_cam={skipped_cam}",
        f"skipped_null_cam={skipped_null_cam}",
        f"skipped_idempotent={skipped_idempotent}",
        f"errors={errors}",
    ]
    if error_details:
        preview = "; ".join(error_details[:5])
        parts.append(preview)
        if len(error_details) > 5:
            parts.append("...")
    return " ".join(parts)


def run() -> None:
    _require_credentials()
    run_id = None

    with local_connection() as conn:
        _ensure_log_table(conn)
        run_id = log_job_run(conn, JOB_NAME, "running", "Started genplan photo confirm")

    try:
        with local_connection() as conn:
            _ensure_log_table(conn)
            with conn.cursor() as cur:
                skipped_null_cam = count_skipped_null_cam(cur)
                skipped_cam = count_skipped_cam(cur)
                true_rows = load_true_candidates(cur)
                false_rows = load_false_candidates(cur)
                sent = load_sent_confirms(cur)

        true_pending, skip_true = exclude_already_sent(true_rows, sent)
        false_pending, skip_false = exclude_already_sent(false_rows, sent)
        skipped_idempotent = skip_true + skip_false

        if GENPLAN_CONFIRM_LIMIT_TRUE > 0:
            logger.info(
                "GENPLAN_CONFIRM_LIMIT_TRUE=%s: %s pending true",
                GENPLAN_CONFIRM_LIMIT_TRUE,
                len(true_pending),
            )
        if GENPLAN_CONFIRM_LIMIT_FALSE > 0:
            logger.info(
                "GENPLAN_CONFIRM_LIMIT_FALSE=%s: %s pending false",
                GENPLAN_CONFIRM_LIMIT_FALSE,
                len(false_pending),
            )

        to_send = apply_limit(true_pending, GENPLAN_CONFIRM_LIMIT_TRUE) + apply_limit(
            false_pending, GENPLAN_CONFIRM_LIMIT_FALSE
        )

        if not to_send:
            message = _format_message(
                sent_true=0,
                sent_false=0,
                skipped_cam=skipped_cam,
                skipped_null_cam=skipped_null_cam,
                skipped_idempotent=skipped_idempotent,
                errors=0,
                error_details=[],
            )
            with local_connection() as conn:
                log_job_run(
                    conn,
                    JOB_NAME,
                    "success",
                    message,
                    rows_affected=0,
                    run_id=run_id,
                )
            logger.info("genplan_confirm finished: %s", message)
            return

        with MsiHolesClient(
            client_id=MSI_HOLES_CLIENT_ID,
            client_secret=MSI_HOLES_CLIENT_SECRET,
            base_url=MSI_HOLES_BASE_URL,
            token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
            timeout=60.0,
            verify=MSI_HOLES_VERIFY_SSL,
        ) as api:
            with local_connection() as conn:
                result = send_confirms(api, conn, to_send)

        message = _format_message(
            sent_true=result.sent_true,
            sent_false=result.sent_false,
            skipped_cam=skipped_cam,
            skipped_null_cam=skipped_null_cam,
            skipped_idempotent=skipped_idempotent,
            errors=result.errors,
            error_details=result.error_details,
        )
        rows_affected = result.sent_true + result.sent_false

        if rows_affected == 0 and result.errors:
            with local_connection() as conn:
                log_job_run(
                    conn,
                    JOB_NAME,
                    "failed",
                    message,
                    rows_affected=0,
                    run_id=run_id,
                )
            raise RuntimeError(message)

        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=rows_affected,
                run_id=run_id,
            )
        logger.info("genplan_confirm finished: %s", message)

    except Exception as exc:
        logger.exception("genplan_confirm job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise


if __name__ == "__main__":
    run()
