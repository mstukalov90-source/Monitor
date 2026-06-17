"""Fetch photo metadata from MSI Holes API for genplan.uploaded_photo UUIDs."""

from __future__ import annotations

import logging

import httpx

from collector.config import (
    GENPLAN_FETCH_UPLOADED_LIMIT,
    MSI_HOLES_BASE_URL,
    MSI_HOLES_CLIENT_ID,
    MSI_HOLES_CLIENT_SECRET,
    MSI_HOLES_CREDENTIALS_FILE,
    MSI_HOLES_TOKEN_ENDPOINT,
)
from collector.db import local_connection, log_job_run
from collector.genplan_ingest import upsert_photo_meta
from collector.genplan_uuids import load_uploaded_uuids_pending_meta
from collector.msi_holes_client import MsiHolesClient

logger = logging.getLogger(__name__)

JOB_NAME = "genplan_fetch_uploaded"
API_PHOTOS_META = "/api/photos/meta/{uuid}"


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _fetch_photo_meta(api: MsiHolesClient, uuid: str) -> dict:
    resp = api.get(
        API_PHOTOS_META.format(uuid=uuid),
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"photo meta for {uuid} is not a JSON object: {data!r}")
    return data


def run() -> None:
    _require_credentials()
    run_id = None

    with local_connection() as conn:
        with conn.cursor() as cur:
            pending_uuids = load_uploaded_uuids_pending_meta(cur)

    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"{len(pending_uuids)} uploaded photo uuid(s) pending meta fetch",
        )

    if not pending_uuids:
        message = "0 uploaded photo uuid(s) pending meta fetch"
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=0,
                run_id=run_id,
            )
        logger.info("genplan_fetch_uploaded finished: %s", message)
        return

    fetch_uuids = pending_uuids
    if GENPLAN_FETCH_UPLOADED_LIMIT > 0:
        fetch_uuids = pending_uuids[:GENPLAN_FETCH_UPLOADED_LIMIT]
        logger.info(
            "GENPLAN_FETCH_UPLOADED_LIMIT=%s: processing %s of %s pending uuid(s)",
            GENPLAN_FETCH_UPLOADED_LIMIT,
            len(fetch_uuids),
            len(pending_uuids),
        )

    meta_saved = 0
    skipped = 0
    meta_errors: list[str] = []

    try:
        with MsiHolesClient(
            client_id=MSI_HOLES_CLIENT_ID,
            client_secret=MSI_HOLES_CLIENT_SECRET,
            base_url=MSI_HOLES_BASE_URL,
            token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
            timeout=60.0,
        ) as api:
            for uuid in fetch_uuids:
                try:
                    meta = _fetch_photo_meta(api, uuid)
                    upsert_photo_meta(meta, source=f"fetch_uploaded:{uuid}")
                    meta_saved += 1
                    logger.info("Upserted meta for %s", uuid)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        skipped += 1
                        logger.warning("Meta not ready for %s (404)", uuid)
                        continue
                    logger.warning("Failed to fetch meta for %s: %s", uuid, exc)
                    meta_errors.append(f"{uuid}: {exc}")
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("Failed to fetch meta for %s: %s", uuid, exc)
                    meta_errors.append(f"{uuid}: {exc}")
    except Exception as exc:
        logger.exception("genplan_fetch_uploaded job failed")
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "failed",
                str(exc),
                rows_affected=meta_saved,
                run_id=run_id,
            )
        raise

    if meta_saved == 0 and meta_errors:
        message = (
            f"{len(fetch_uuids)} pending uuid(s), 0 meta saved, "
            f"{skipped} not ready (404), {len(meta_errors)} error(s)"
        )
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", message, rows_affected=0, run_id=run_id)
        raise RuntimeError(message)

    message_parts = [
        f"{len(pending_uuids)} pending",
        f"{meta_saved} meta upserted",
    ]
    if skipped:
        message_parts.append(f"{skipped} not ready (404)")
    if meta_errors:
        message_parts.append(f"{len(meta_errors)} error(s): " + "; ".join(meta_errors[:5]))
        if len(meta_errors) > 5:
            message_parts.append("...")

    message = "; ".join(message_parts)

    with local_connection() as conn:
        log_job_run(
            conn,
            JOB_NAME,
            "success",
            message,
            rows_affected=meta_saved,
            run_id=run_id,
        )

    logger.info("genplan_fetch_uploaded finished: %s", message)
