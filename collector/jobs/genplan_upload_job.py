"""Upload photos from photo_to_upload/ to MSI Holes API."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import httpx

from collector.config import (
    GENPLAN_PHOTO_UPLOAD_DIR,
    GENPLAN_PHOTO_UPLOADED_DIR,
    MSI_HOLES_BASE_URL,
    MSI_HOLES_CLIENT_ID,
    MSI_HOLES_CLIENT_SECRET,
    MSI_HOLES_CREDENTIALS_FILE,
    MSI_HOLES_TOKEN_ENDPOINT,
)
from collector.db import local_connection, log_job_run
from collector.genplan_photo_exif import (
    extract_photo_upload_meta,
    is_photo_file,
    photo_mime_type,
)
from collector.genplan_upload import insert_uploaded_photo, load_uploaded_file_names
from collector.msi_holes_client import MsiHolesClient

logger = logging.getLogger(__name__)

JOB_NAME = "genplan_upload"
API_UPLOAD = "/api/upload"


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _list_photos(upload_dir: Path) -> list[Path]:
    if not upload_dir.is_dir():
        return []
    photos = [p for p in sorted(upload_dir.iterdir()) if is_photo_file(p)]
    return photos


def _upload_photo(api: MsiHolesClient, path: Path) -> dict:
    meta = extract_photo_upload_meta(path)
    form_data = meta.as_form_data()
    mime = photo_mime_type(path)

    with path.open("rb") as photo_file:
        resp = api.post(
            API_UPLOAD,
            data=form_data,
            files={"photo": (path.name, photo_file, mime)},
        )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"upload returned unexpected body: {data!r}")

    insert_uploaded_photo(data, file_name=path.name, request_meta=meta)
    return data


def _archive_photo(path: Path, archive_dir: Path) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / path.name
    if dest.exists():
        dest.unlink()
    shutil.move(str(path), str(dest))


def run() -> None:
    _require_credentials()
    run_id = None

    upload_dir = GENPLAN_PHOTO_UPLOAD_DIR
    archive_dir = GENPLAN_PHOTO_UPLOADED_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)

    photos = _list_photos(upload_dir)
    known_names = load_uploaded_file_names()
    pending = [p for p in photos if p.name not in known_names]
    skipped = len(photos) - len(pending)

    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"Found {len(photos)} photo(s) in {upload_dir.name}, "
            f"{len(pending)} to upload, {skipped} already in DB",
        )

    if not pending:
        message = f"No new photos in {upload_dir.name}"
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=0,
                run_id=run_id,
            )
        logger.info("genplan_upload finished: %s", message)
        return

    uploaded = 0
    errors: list[str] = []

    try:
        with MsiHolesClient(
            client_id=MSI_HOLES_CLIENT_ID,
            client_secret=MSI_HOLES_CLIENT_SECRET,
            base_url=MSI_HOLES_BASE_URL,
            token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
            timeout=120.0,
        ) as api:
            for path in pending:
                try:
                    logger.info("Uploading %s", path.name)
                    response = _upload_photo(api, path)
                    _archive_photo(path, archive_dir)
                    uploaded += 1
                    logger.info(
                        "Uploaded %s -> uuid=%s",
                        path.name,
                        response.get("uuid"),
                    )
                except (httpx.HTTPError, ValueError, OSError) as exc:
                    logger.warning("Failed to upload %s: %s", path.name, exc)
                    errors.append(f"{path.name}: {exc}")
    except Exception as exc:
        logger.exception("genplan_upload job failed")
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "failed",
                str(exc),
                rows_affected=uploaded,
                run_id=run_id,
            )
        raise

    if uploaded == 0:
        message = f"0 photo(s) uploaded, {len(errors)} error(s)"
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", message, rows_affected=0, run_id=run_id)
        raise RuntimeError("; ".join(errors) if errors else message)

    message_parts = [f"{uploaded} photo(s) uploaded"]
    if skipped:
        message_parts.append(f"{skipped} skipped (already in DB)")
    if errors:
        message_parts.append(f"{len(errors)} error(s): " + "; ".join(errors[:5]))
        if len(errors) > 5:
            message_parts.append("...")

    job_status = "failed" if errors and not uploaded else "success"
    message = "; ".join(message_parts)

    with local_connection() as conn:
        log_job_run(
            conn,
            JOB_NAME,
            job_status,
            message,
            rows_affected=uploaded,
            run_id=run_id,
        )

    logger.info("genplan_upload finished: %s", message)
