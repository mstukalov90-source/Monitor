"""Fetch genplan photo UUIDs and metadata from MSI Holes API into jsons_genplan/."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from collector.config import (
    GENPLAN_FETCH_META_LIMIT,
    GENPLAN_JSON_DIR,
    GENPLAN_SEARCH_LAT,
    GENPLAN_SEARCH_LNG,
    GENPLAN_SEARCH_RADIUS_M,
    MSI_HOLES_BASE_URL,
    MSI_HOLES_CLIENT_ID,
    MSI_HOLES_CLIENT_SECRET,
    MSI_HOLES_CREDENTIALS_FILE,
    MSI_HOLES_TOKEN_ENDPOINT,
)
from collector.db import local_connection, log_job_run
from collector.genplan_uuids import (
    load_genplan_uuid_area_uuids,
    load_genplan_uuids_with_meta,
)
from collector.msi_holes_client import MsiHolesClient

logger = logging.getLogger(__name__)

JOB_NAME = "genplan_fetch"

API_SPATIAL_SEARCH = "/spatial_search"
API_PHOTOS_META = "/api/photos/meta/{uuid}"


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _spatial_search_payload() -> dict[str, float | int]:
    return {
        "lat": GENPLAN_SEARCH_LAT,
        "lng": GENPLAN_SEARCH_LNG,
        "radius_m": GENPLAN_SEARCH_RADIUS_M,
    }


def _spatial_search(api: MsiHolesClient) -> list[str]:
    body = _spatial_search_payload()
    # API expects form fields (json body returns 400).
    resp = api.post(API_SPATIAL_SEARCH, data=body)
    resp.raise_for_status()
    data = resp.json()
    uuids = data.get("uuids")
    if not isinstance(uuids, list):
        raise ValueError(f"spatial_search returned unexpected body: {data!r}")
    return [str(u) for u in uuids]


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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def run() -> None:
    _require_credentials()
    run_id = None

    genplan_dir = GENPLAN_JSON_DIR
    genplan_dir.mkdir(parents=True, exist_ok=True)

    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"spatial_search lat={GENPLAN_SEARCH_LAT} lng={GENPLAN_SEARCH_LNG} "
            f"radius_m={GENPLAN_SEARCH_RADIUS_M}",
        )

    with local_connection() as conn:
        with conn.cursor() as cur:
            known_with_meta = load_genplan_uuids_with_meta(cur)
            known_uuid_area = load_genplan_uuid_area_uuids(cur)

    total_uuids = 0
    pending_meta: list[str] = []
    new_uuid_area: list[str] = []
    fetch_uuids: list[str] = []
    meta_saved = 0
    meta_errors: list[str] = []

    try:
        with MsiHolesClient(
            client_id=MSI_HOLES_CLIENT_ID,
            client_secret=MSI_HOLES_CLIENT_SECRET,
            base_url=MSI_HOLES_BASE_URL,
            token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
            timeout=60.0,
        ) as api:
            all_uuids = _spatial_search(api)
            total_uuids = len(all_uuids)
            pending_meta = [u for u in all_uuids if u not in known_with_meta]
            new_uuid_area = [u for u in pending_meta if u not in known_uuid_area]

            logger.info(
                "spatial_search: %s total uuid(s), %s pending meta, %s new uuid_area, %s with meta",
                total_uuids,
                len(pending_meta),
                len(new_uuid_area),
                total_uuids - len(pending_meta),
            )

            if not pending_meta:
                message = (
                    f"spatial_search returned {total_uuids} uuid(s), "
                    "0 pending meta; nothing to fetch"
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
                logger.info("genplan_fetch finished: %s", message)
                return

            fetch_uuids = pending_meta
            if GENPLAN_FETCH_META_LIMIT > 0:
                fetch_uuids = pending_meta[:GENPLAN_FETCH_META_LIMIT]
                logger.info(
                    "GENPLAN_FETCH_META_LIMIT=%s: processing %s of %s pending uuid(s)",
                    GENPLAN_FETCH_META_LIMIT,
                    len(fetch_uuids),
                    len(pending_meta),
                )

            uuids_for_area_file = [u for u in fetch_uuids if u not in known_uuid_area]
            if uuids_for_area_file:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                uuid_area_path = genplan_dir / f"uuid_area_{stamp}.json"
                _write_json(uuid_area_path, {"uuids": uuids_for_area_file})
                logger.info(
                    "Wrote %s (%s uuid(s))", uuid_area_path.name, len(uuids_for_area_file)
                )

            for uuid in fetch_uuids:
                try:
                    meta = _fetch_photo_meta(api, uuid)
                    meta_path = genplan_dir / f"{uuid}.json"
                    _write_json(meta_path, meta)
                    meta_saved += 1
                    logger.debug("Fetched meta for %s", uuid)
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("Failed to fetch meta for %s: %s", uuid, exc)
                    meta_errors.append(f"{uuid}: {exc}")

    except Exception as exc:
        logger.exception("genplan_fetch job failed")
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

    processed = len(fetch_uuids) if pending_meta else 0
    if meta_saved == 0:
        message = (
            f"spatial_search: {total_uuids} total, {len(pending_meta)} pending meta, "
            f"{processed} processed; 0 meta saved, {len(meta_errors)} error(s)"
        )
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", message, rows_affected=0, run_id=run_id)
        raise RuntimeError(message)

    message_parts = [
        f"spatial_search: {total_uuids} total, {len(pending_meta)} pending meta",
        f"{meta_saved} meta file(s) written",
    ]
    if meta_errors:
        message_parts.append(f"{len(meta_errors)} meta error(s): " + "; ".join(meta_errors[:5]))
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

    logger.info("genplan_fetch finished: %s", message)
