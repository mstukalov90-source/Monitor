"""Download genplan photos (disruption=true inside hood polygon) from MSI Holes API."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx
from psycopg2.extras import RealDictCursor

from collector.config import (
    GENPLAN_DOWNLOAD_DIR,
    GENPLAN_DOWNLOAD_HOOD_GID,
    MSI_HOLES_BASE_URL,
    MSI_HOLES_CLIENT_ID,
    MSI_HOLES_CLIENT_SECRET,
    MSI_HOLES_CREDENTIALS_FILE,
    MSI_HOLES_TOKEN_ENDPOINT,
)
from collector.db import local_connection, log_job_run
from collector.msi_holes_client import MsiHolesClient

logger = logging.getLogger(__name__)

JOB_NAME = "genplan_download"
API_PHOTOS_IMAGE = "/api/photos/images/{uuid}"

_PHOTO_ROWS_SQL = """
SELECT
    pm.uuid,
    pm.image_name
FROM genplan.photo_meta pm
JOIN odh_export.hood h ON h.gid = %(hood_gid)s
WHERE pm.disruption IS TRUE
  AND pm.uuid IS NOT NULL
  AND btrim(pm.uuid) <> ''
  AND pm.geom IS NOT NULL
  AND ST_Within(pm.geom, h.geom)
ORDER BY pm.loaded_at DESC
"""

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _load_photo_rows(hood_gid: int) -> list[dict[str, Any]]:
    with local_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_PHOTO_ROWS_SQL, {"hood_gid": hood_gid})
            return list(cur.fetchall())


def _safe_filename(image_name: str | None, uuid: str) -> str:
    if image_name and str(image_name).strip():
        name = _UNSAFE_FILENAME.sub("_", Path(str(image_name).strip()).name)
        if name and name not in (".", ".."):
            return name
    return f"{uuid}.jpg"


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".jpg"
    lowered = content_type.split(";", 1)[0].strip().lower()
    if lowered == "image/png":
        return ".png"
    if lowered in ("image/jpeg", "image/jpg"):
        return ".jpg"
    return ".jpg"


def _ensure_extension(path: Path, content_type: str | None) -> Path:
    ext = _extension_from_content_type(content_type)
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        return path.with_suffix(ext)
    return path


def _download_photo(api: MsiHolesClient, uuid: str, dest: Path) -> None:
    resp = api.get(
        API_PHOTOS_IMAGE.format(uuid=uuid),
        headers={"Accept": "image/jpeg, image/png"},
    )
    resp.raise_for_status()
    dest = _ensure_extension(dest, resp.headers.get("content-type"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)


def run() -> None:
    _require_credentials()
    hood_gid = GENPLAN_DOWNLOAD_HOOD_GID
    download_dir = GENPLAN_DOWNLOAD_DIR
    run_id = None

    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"hood_gid={hood_gid} -> {download_dir.name}/",
        )

    rows = _load_photo_rows(hood_gid)
    if not rows:
        message = f"0 photo(s) matched disruption=true in hood gid={hood_gid}"
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=0,
                run_id=run_id,
            )
        logger.info("genplan_download finished: %s", message)
        return

    downloaded = 0
    skipped = 0
    errors: list[str] = []

    try:
        with MsiHolesClient(
            client_id=MSI_HOLES_CLIENT_ID,
            client_secret=MSI_HOLES_CLIENT_SECRET,
            base_url=MSI_HOLES_BASE_URL,
            token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
            timeout=120.0,
        ) as api:
            for row in rows:
                uuid = str(row["uuid"]).strip()
                dest = download_dir / _safe_filename(row.get("image_name"), uuid)
                if dest.exists():
                    skipped += 1
                    logger.debug("Skip existing %s", dest.name)
                    continue
                try:
                    _download_photo(api, uuid, dest)
                    downloaded += 1
                    logger.info("Downloaded %s -> %s", uuid, dest.name)
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    logger.warning("Failed to download %s: %s", uuid, exc)
                    errors.append(f"{uuid}: {exc}")
    except Exception as exc:
        logger.exception("genplan_download job failed")
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "failed",
                str(exc),
                rows_affected=downloaded,
                run_id=run_id,
            )
        raise

    message_parts = [
        f"{len(rows)} matched",
        f"{downloaded} downloaded",
    ]
    if skipped:
        message_parts.append(f"{skipped} skipped (already on disk)")
    if errors:
        message_parts.append(f"{len(errors)} error(s): " + "; ".join(errors[:5]))
        if len(errors) > 5:
            message_parts.append("...")

    job_status = "failed" if errors and downloaded == 0 else "success"
    message = "; ".join(message_parts)

    with local_connection() as conn:
        log_job_run(
            conn,
            JOB_NAME,
            job_status,
            message,
            rows_affected=downloaded,
            run_id=run_id,
        )

    logger.info("genplan_download finished: %s", message)
    if job_status == "failed":
        raise RuntimeError(message)
