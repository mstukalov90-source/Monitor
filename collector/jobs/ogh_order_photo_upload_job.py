"""Upload field photos from OGH Заказы share to MSI Holes genplan API.

Reads public.mview_mon_op_prod (SELECT only) and the CIFS share (read-only).
Does not move or delete files. Incremental state lives in genplan.ogh_order_photo_log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from psycopg2.extras import RealDictCursor

from collector.config import (
    MSI_HOLES_BASE_URL,
    MSI_HOLES_CLIENT_ID,
    MSI_HOLES_CLIENT_SECRET,
    MSI_HOLES_CREDENTIALS_FILE,
    MSI_HOLES_TOKEN_ENDPOINT,
    MSI_HOLES_VERIFY_SSL,
    OGH_ORDER_PHOTO_EDF_AFTER,
    OGH_ORDER_PHOTO_LOG_SQL,
    OGH_ZAKAZY_DIR,
)
from collector.db import execute_sql_file, local_connection, log_job_run
from collector.genplan_photo_exif import (
    extract_photo_upload_meta,
    is_photo_file,
    photo_mime_type,
)
from collector.genplan_upload import insert_uploaded_photo
from collector.msi_holes_client import MsiHolesClient
from collector.ogh_order_photo_paths import (
    ZakazyPathError,
    file_relpath,
    photo_dir_for_url,
)

logger = logging.getLogger(__name__)

JOB_NAME = "ogh_order_photo_upload"
JOB_NAME_DRY = "ogh_order_photo_upload_dry"
API_UPLOAD = "/api/upload"

OGNO_LIKE = "12/ОГХ-%"
OPERNM = "Проверка результатов съемки"

_SELECT_SQL = """
SELECT oid, ogno, ono, edf, url
FROM public.mview_mon_op_prod
WHERE ogno LIKE %s
  AND opernm = %s
  AND edf > %s
ORDER BY edf, oid
"""


@dataclass
class OrderRow:
    oid: Any
    ogno: str | None
    url: str | None
    edf: date | None


@dataclass
class DryRowResult:
    oid: Any
    ogno: str | None
    url: str | None
    photo_dir: str | None
    photos: int = 0
    error: str | None = None


@dataclass
class RunStats:
    rows: int = 0
    ok_dirs: int = 0
    photos_found: int = 0
    uploaded: int = 0
    skipped_uploaded: int = 0
    missing: int = 0
    bad_url: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _ensure_log_table(conn) -> None:
    if not OGH_ORDER_PHOTO_LOG_SQL.exists():
        raise FileNotFoundError(f"SQL migration not found: {OGH_ORDER_PHOTO_LOG_SQL}")
    execute_sql_file(conn, OGH_ORDER_PHOTO_LOG_SQL)


def _load_rows() -> list[OrderRow]:
    with local_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_SELECT_SQL, (OGNO_LIKE, OPERNM, OGH_ORDER_PHOTO_EDF_AFTER))
            return [
                OrderRow(
                    oid=row["oid"],
                    ogno=row["ogno"],
                    url=row["url"],
                    edf=row["edf"],
                )
                for row in cur.fetchall()
            ]


def _load_uploaded_relpaths() -> set[str]:
    with local_connection() as conn:
        _ensure_log_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_relpath
                FROM genplan.ogh_order_photo_log
                WHERE status = 'uploaded'
                """
            )
            return {row[0] for row in cur.fetchall()}


def _upsert_log(
    *,
    source_oid: Any,
    ogno: str | None,
    source_url: str | None,
    source_relpath: str,
    status: str,
    genplan_uuid: str | None = None,
    error_message: str | None = None,
) -> None:
    with local_connection() as conn:
        _ensure_log_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO genplan.ogh_order_photo_log (
                    source_oid, ogno, source_url, source_relpath,
                    status, genplan_uuid, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_relpath) DO UPDATE SET
                    source_oid = EXCLUDED.source_oid,
                    ogno = EXCLUDED.ogno,
                    source_url = EXCLUDED.source_url,
                    status = EXCLUDED.status,
                    genplan_uuid = COALESCE(EXCLUDED.genplan_uuid, genplan.ogh_order_photo_log.genplan_uuid),
                    error_message = EXCLUDED.error_message,
                    processed_at = NOW()
                WHERE genplan.ogh_order_photo_log.status IS DISTINCT FROM 'uploaded'
                """,
                (
                    source_oid,
                    ogno,
                    source_url,
                    source_relpath,
                    status,
                    genplan_uuid,
                    error_message,
                ),
            )


def _list_photos(photo_dir: Path) -> list[Path]:
    if not photo_dir.is_dir():
        return []
    return [path for path in sorted(photo_dir.iterdir()) if is_photo_file(path)]


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


def _inspect_row(row: OrderRow, root: Path) -> DryRowResult:
    try:
        photo_dir = photo_dir_for_url(row.url, root)
    except ZakazyPathError as exc:
        return DryRowResult(
            oid=row.oid,
            ogno=row.ogno,
            url=row.url,
            photo_dir=None,
            error=str(exc),
        )
    if not photo_dir.is_dir():
        return DryRowResult(
            oid=row.oid,
            ogno=row.ogno,
            url=row.url,
            photo_dir=str(photo_dir),
            error="no_dir",
        )
    photos = _list_photos(photo_dir)
    if not photos:
        return DryRowResult(
            oid=row.oid,
            ogno=row.ogno,
            url=row.url,
            photo_dir=str(photo_dir),
            error="empty",
        )
    return DryRowResult(
        oid=row.oid,
        ogno=row.ogno,
        url=row.url,
        photo_dir=str(photo_dir),
        photos=len(photos),
    )


def run_dry() -> None:
    run(dry_run=True)


def run(*, dry_run: bool = False) -> None:
    job_name = JOB_NAME_DRY if dry_run else JOB_NAME
    if not dry_run:
        _require_credentials()

    root = OGH_ZAKAZY_DIR
    rows = _load_rows()
    stats = RunStats(rows=len(rows))
    run_id = None

    with local_connection() as conn:
        _ensure_log_table(conn)
        run_id = log_job_run(
            conn,
            job_name,
            "running",
            f"{len(rows)} mview row(s), root={root}, dry_run={dry_run}",
        )

    uploaded_relpaths = set() if dry_run else _load_uploaded_relpaths()

    try:
        if dry_run:
            _run_dry(rows, root, stats)
        else:
            _run_upload(rows, root, stats, uploaded_relpaths)
    except Exception as exc:
        logger.exception("%s job failed", job_name)
        with local_connection() as conn:
            log_job_run(conn, job_name, "failed", str(exc), rows_affected=stats.uploaded, run_id=run_id)
        raise

    message = (
        f"rows={stats.rows} ok_dirs={stats.ok_dirs} photos={stats.photos_found} "
        f"uploaded={stats.uploaded} skipped={stats.skipped_uploaded} "
        f"missing={stats.missing} bad_url={stats.bad_url} failed={stats.failed}"
    )
    if stats.errors:
        message += "; " + "; ".join(stats.errors[:8])
        if len(stats.errors) > 8:
            message += "; ..."

    status = "failed" if stats.failed and not dry_run and stats.uploaded == 0 else "success"
    with local_connection() as conn:
        log_job_run(
            conn,
            job_name,
            status,
            message,
            rows_affected=stats.uploaded if not dry_run else stats.photos_found,
            run_id=run_id,
        )
    logger.info("%s finished: %s", job_name, message)
    if status == "failed":
        raise RuntimeError(message)


def _run_dry(rows: list[OrderRow], root: Path, stats: RunStats) -> None:
    for row in rows:
        result = _inspect_row(row, root)
        if result.error == "empty" or result.error == "no_dir":
            stats.missing += 1
            logger.warning(
                "dry oid=%s ogno=%s %s %s",
                row.oid,
                row.ogno,
                result.error,
                result.photo_dir,
            )
            continue
        if result.error:
            stats.bad_url += 1
            logger.warning("dry oid=%s ogno=%s bad_url=%r (%s)", row.oid, row.ogno, row.url, result.error)
            continue
        stats.ok_dirs += 1
        stats.photos_found += result.photos
        logger.info(
            "dry oid=%s ogno=%s photos=%s dir=%s",
            row.oid,
            row.ogno,
            result.photos,
            result.photo_dir,
        )


def _run_upload(
    rows: list[OrderRow],
    root: Path,
    stats: RunStats,
    uploaded_relpaths: set[str],
) -> None:
    api: MsiHolesClient | None = None
    for row in rows:
        result = _inspect_row(row, root)
        if result.error:
            rel = result.photo_dir or f"bad-url/{row.oid}"
            if result.error in {"no_dir", "empty"}:
                stats.missing += 1
            else:
                stats.bad_url += 1
            _upsert_log(
                source_oid=row.oid,
                ogno=row.ogno,
                source_url=row.url,
                source_relpath=rel,
                status="skipped_missing",
                error_message=result.error,
            )
            logger.warning(
                "oid=%s ogno=%s skip=%s url=%r dir=%s",
                row.oid,
                row.ogno,
                result.error,
                row.url,
                result.photo_dir,
            )
            continue

        photo_dir = Path(result.photo_dir)  # type: ignore[arg-type]
        photos = _list_photos(photo_dir)
        stats.ok_dirs += 1
        stats.photos_found += len(photos)

        for path in photos:
            rel = file_relpath(photo_dir, path, root)
            if rel in uploaded_relpaths:
                stats.skipped_uploaded += 1
                continue
            if api is None:
                api = MsiHolesClient(
                    client_id=MSI_HOLES_CLIENT_ID,
                    client_secret=MSI_HOLES_CLIENT_SECRET,
                    base_url=MSI_HOLES_BASE_URL,
                    token_endpoint=MSI_HOLES_TOKEN_ENDPOINT,
                    timeout=120.0,
                    verify=MSI_HOLES_VERIFY_SSL,
                )
            try:
                logger.info("Uploading %s (oid=%s)", rel, row.oid)
                response = _upload_photo(api, path)
                uuid = response.get("uuid")
                uuid_text = str(uuid) if uuid is not None else None
                _upsert_log(
                    source_oid=row.oid,
                    ogno=row.ogno,
                    source_url=row.url,
                    source_relpath=rel,
                    status="uploaded",
                    genplan_uuid=uuid_text,
                )
                uploaded_relpaths.add(rel)
                stats.uploaded += 1
            except (httpx.HTTPError, ValueError, OSError) as exc:
                stats.failed += 1
                stats.errors.append(f"{rel}: {exc}")
                logger.warning("Failed to upload %s: %s", rel, exc)
                _upsert_log(
                    source_oid=row.oid,
                    ogno=row.ogno,
                    source_url=row.url,
                    source_relpath=rel,
                    status="failed",
                    error_message=str(exc),
                )
    if api is not None:
        api.close()
