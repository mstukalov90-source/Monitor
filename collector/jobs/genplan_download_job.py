"""Download genplan photos (disruption=true) from MSI Holes API.

Missing ``{uuid}.ext`` files are retried on every run. Unique legacy files named
by ``image_name`` are promoted (hardlink/copy) to the canonical name without a
re-fetch. Colliding ``image_name`` values are not promoted (false skip risk).
"""

from __future__ import annotations

import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from psycopg2.extras import RealDictCursor

from collector.config import (
    GENPLAN_DOWNLOAD_DIR,
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
WHERE pm.disruption IS TRUE
  AND pm.uuid IS NOT NULL
  AND btrim(pm.uuid) <> ''
  AND pm.geom IS NOT NULL
ORDER BY pm.loaded_at DESC
"""

_UUID_SUFFIXES = (".jpg", ".jpeg", ".png")
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _load_photo_rows() -> list[dict[str, Any]]:
    with local_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_PHOTO_ROWS_SQL)
            return list(cur.fetchall())


def _is_nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not remove %s", path, exc_info=True)


def _remove_empty(path: Path) -> None:
    try:
        if path.is_file() and path.stat().st_size == 0:
            path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not remove empty %s", path, exc_info=True)


def _legacy_filename(image_name: str | None) -> str | None:
    if not image_name or not str(image_name).strip():
        return None
    name = _UNSAFE_FILENAME.sub("_", Path(str(image_name).strip()).name)
    if name and name not in (".", ".."):
        return name
    return None


def _find_canonical(download_dir: Path, uuid: str) -> Path | None:
    for suffix in _UUID_SUFFIXES:
        candidate = download_dir / f"{uuid}{suffix}"
        _remove_empty(candidate)
        if _is_nonempty_file(candidate):
            return candidate
    return None


def _promote_legacy(download_dir: Path, uuid: str, image_name: str | None) -> Path | None:
    """Copy/hardlink a unique legacy image_name file to ``{uuid}.ext``."""
    legacy_name = _legacy_filename(image_name)
    if not legacy_name:
        return None
    legacy = download_dir / legacy_name
    _remove_empty(legacy)
    if not _is_nonempty_file(legacy):
        return None

    suffix = legacy.suffix.lower() if legacy.suffix.lower() in _UUID_SUFFIXES else ".jpg"
    dest = download_dir / f"{uuid}{suffix}"
    if _is_nonempty_file(dest):
        return dest

    try:
        try:
            dest.hardlink_to(legacy)
        except OSError:
            shutil.copy2(legacy, dest)
    except OSError as exc:
        logger.warning("Failed to promote legacy %s -> %s: %s", legacy.name, dest.name, exc)
        _unlink_quiet(dest)
        return None

    if not _is_nonempty_file(dest):
        _unlink_quiet(dest)
        return None
    return dest


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".jpg"
    lowered = content_type.split(";", 1)[0].strip().lower()
    if lowered == "image/png":
        return ".png"
    if lowered in ("image/jpeg", "image/jpg"):
        return ".jpg"
    return ".jpg"


def _download_photo(api: MsiHolesClient, uuid: str, download_dir: Path) -> Path:
    """Download image for uuid into ``{uuid}.ext`` via atomic temp + replace."""
    resp = api.get(
        API_PHOTOS_IMAGE.format(uuid=uuid),
        headers={"Accept": "image/jpeg, image/png"},
    )
    resp.raise_for_status()

    ext = _extension_from_content_type(resp.headers.get("content-type"))
    dest = download_dir / f"{uuid}{ext}"
    part = download_dir / f".{uuid}.part"

    download_dir.mkdir(parents=True, exist_ok=True)
    try:
        part.write_bytes(resp.content)
        if part.stat().st_size == 0:
            raise ValueError(f"empty response body for {uuid}")
        part.replace(dest)
    except Exception:
        _unlink_quiet(part)
        raise

    return dest


def run() -> None:
    _require_credentials()
    download_dir = GENPLAN_DOWNLOAD_DIR
    run_id = None

    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"disruption=true -> {download_dir.name}/ (retry missing)",
        )

    rows = _load_photo_rows()
    if not rows:
        message = "0 photo(s) matched disruption=true"
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

    legacy_counts: Counter[str] = Counter()
    for row in rows:
        legacy = _legacy_filename(row.get("image_name"))
        if legacy:
            legacy_counts[legacy] += 1

    skipped = 0
    promoted = 0
    to_fetch: list[dict[str, Any]] = []

    for row in rows:
        uuid = str(row["uuid"]).strip()
        if _find_canonical(download_dir, uuid) is not None:
            skipped += 1
            continue

        legacy = _legacy_filename(row.get("image_name"))
        if legacy and legacy_counts[legacy] == 1:
            if _promote_legacy(download_dir, uuid, row.get("image_name")) is not None:
                promoted += 1
                logger.info("Promoted legacy %s -> %s.jpg|.png", legacy, uuid)
                continue

        to_fetch.append(row)

    downloaded = 0
    errors: list[str] = []

    try:
        if to_fetch:
            with MsiHolesClient(
                client_id=MSI_HOLES_CLIENT_ID,
                client_secret=MSI_HOLES_CLIENT_SECRET,
                base_url=MSI_HOLES_BASE_URL,
                token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
                timeout=120.0,
            ) as api:
                for row in to_fetch:
                    uuid = str(row["uuid"]).strip()
                    try:
                        dest = _download_photo(api, uuid, download_dir)
                        downloaded += 1
                        logger.info("Downloaded %s -> %s", uuid, dest.name)
                    except (httpx.HTTPError, OSError, ValueError) as exc:
                        logger.warning("Failed to download %s: %s", uuid, exc)
                        errors.append(f"{uuid}: {exc}")
                        _unlink_quiet(download_dir / f".{uuid}.part")
                        for suffix in _UUID_SUFFIXES:
                            _remove_empty(download_dir / f"{uuid}{suffix}")
    except Exception as exc:
        logger.exception("genplan_download job failed")
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "failed",
                str(exc),
                rows_affected=downloaded + promoted,
                run_id=run_id,
            )
        raise

    message_parts = [
        f"{len(rows)} matched",
        f"{len(to_fetch)} missing",
        f"{downloaded} downloaded",
    ]
    if promoted:
        message_parts.append(f"{promoted} promoted from legacy")
    if skipped:
        message_parts.append(f"{skipped} skipped (already on disk)")
    if errors:
        message_parts.append(f"{len(errors)} error(s): " + "; ".join(errors[:5]))
        if len(errors) > 5:
            message_parts.append("...")

    job_status = (
        "failed" if errors and downloaded == 0 and promoted == 0 and to_fetch else "success"
    )
    message = "; ".join(message_parts)

    with local_connection() as conn:
        log_job_run(
            conn,
            JOB_NAME,
            job_status,
            message,
            rows_affected=downloaded + promoted,
            run_id=run_id,
        )

    logger.info("genplan_download finished: %s", message)
    if job_status == "failed":
        raise RuntimeError(message)
