"""Upload situation photos from mview_mon_op_files.fnm to MSI Holes genplan API.

Reads public.mview_mon_op_prod / mview_mon_op_files (SELECT only) and the CIFS
share (read-only). Does not move or delete files.
Incremental state lives in genplan.situation_photo_log.
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
    SITUATION_DIR,
    SITUATION_PHOTO_LOG_SQL,
)
from collector.db import execute_sql_file, local_connection, log_job_run
from collector.genplan_photo_exif import extract_photo_upload_meta, photo_mime_type
from collector.genplan_upload import insert_uploaded_photo
from collector.msi_holes_client import MsiHolesClient
from collector.situation_photo_paths import (
    SituationPathError,
    file_relpath,
    photos_for_fnm,
    relpath_from_fnm,
)

logger = logging.getLogger(__name__)

JOB_NAME = "situation_photo_upload"
JOB_NAME_DRY = "situation_photo_upload_dry"
API_UPLOAD = "/api/upload"

ONO_LIKE = "12/ОГХ-%"
OPERNM = "Проверка результатов съемки"

_SELECT_FILES_SQL = """
SELECT p.oid, p.ono, p.ogno, p.edf, f.fnm
FROM public.mview_mon_op_prod p
JOIN public.mview_mon_op_files f ON f.oid = p.oid
WHERE (p.ono IS NULL OR p.ono NOT LIKE %s)
  AND p.opernm = %s
  AND p.edf > %s
ORDER BY p.edf, p.oid, f.fnm
"""

_COUNT_PROD_SQL = """
SELECT count(*) AS prod_rows,
       count(DISTINCT p.oid) AS prod_oids
FROM public.mview_mon_op_prod p
WHERE (p.ono IS NULL OR p.ono NOT LIKE %s)
  AND p.opernm = %s
  AND p.edf > %s
"""


@dataclass
class FileRow:
    oid: Any
    ono: str | None
    fnm: str | None
    edf: date | None


@dataclass
class RunStats:
    prod_rows: int = 0
    file_rows: int = 0
    photos_found: int = 0
    uploaded: int = 0
    skipped_uploaded: int = 0
    missing: int = 0
    bad_fnm: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _require_credentials() -> None:
    if not MSI_HOLES_CLIENT_ID or not MSI_HOLES_CLIENT_SECRET:
        raise ValueError(
            "MSI Holes credentials missing: set MSI_HOLES_CLIENT_ID and "
            f"MSI_HOLES_CLIENT_SECRET in .env or provide {MSI_HOLES_CREDENTIALS_FILE}"
        )


def _ensure_log_table(conn) -> None:
    if not SITUATION_PHOTO_LOG_SQL.exists():
        raise FileNotFoundError(f"SQL migration not found: {SITUATION_PHOTO_LOG_SQL}")
    execute_sql_file(conn, SITUATION_PHOTO_LOG_SQL)


def _load_file_rows() -> tuple[list[FileRow], int, int]:
    params = (ONO_LIKE, OPERNM, OGH_ORDER_PHOTO_EDF_AFTER)
    with local_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_COUNT_PROD_SQL, params)
            counts = cur.fetchone() or {}
            cur.execute(_SELECT_FILES_SQL, params)
            rows = [
                FileRow(
                    oid=row["oid"],
                    ono=row["ono"],
                    fnm=row["fnm"],
                    edf=row["edf"],
                )
                for row in cur.fetchall()
            ]
    return rows, int(counts.get("prod_rows") or 0), int(counts.get("prod_oids") or 0)


def _load_uploaded_relpaths() -> set[str]:
    with local_connection() as conn:
        _ensure_log_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_relpath
                FROM genplan.situation_photo_log
                WHERE status = 'uploaded'
                """
            )
            return {row[0] for row in cur.fetchall()}


def _upsert_log(
    *,
    source_oid: Any,
    ono: str | None,
    source_fnm: str | None,
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
                INSERT INTO genplan.situation_photo_log (
                    source_oid, ono, source_fnm, source_relpath,
                    status, genplan_uuid, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_relpath) DO UPDATE SET
                    source_oid = EXCLUDED.source_oid,
                    ono = EXCLUDED.ono,
                    source_fnm = EXCLUDED.source_fnm,
                    status = EXCLUDED.status,
                    genplan_uuid = COALESCE(
                        EXCLUDED.genplan_uuid,
                        genplan.situation_photo_log.genplan_uuid
                    ),
                    error_message = EXCLUDED.error_message,
                    processed_at = NOW()
                WHERE genplan.situation_photo_log.status IS DISTINCT FROM 'uploaded'
                """,
                (
                    source_oid,
                    ono,
                    source_fnm,
                    source_relpath,
                    status,
                    genplan_uuid,
                    error_message,
                ),
            )


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


def run_dry() -> None:
    run(dry_run=True)


def run(*, dry_run: bool = False) -> None:
    job_name = JOB_NAME_DRY if dry_run else JOB_NAME
    if not dry_run:
        _require_credentials()

    root = SITUATION_DIR
    rows, prod_rows, prod_oids = _load_file_rows()
    stats = RunStats(prod_rows=prod_rows, file_rows=len(rows))
    run_id = None

    with local_connection() as conn:
        _ensure_log_table(conn)
        run_id = log_job_run(
            conn,
            job_name,
            "running",
            (
                f"{prod_rows} prod row(s), {prod_oids} oid(s), "
                f"{len(rows)} file row(s), root={root}, dry_run={dry_run}"
            ),
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
            log_job_run(
                conn,
                job_name,
                "failed",
                str(exc),
                rows_affected=stats.uploaded,
                run_id=run_id,
            )
        raise

    message = (
        f"prod_rows={stats.prod_rows} file_rows={stats.file_rows} "
        f"photos={stats.photos_found} uploaded={stats.uploaded} "
        f"skipped={stats.skipped_uploaded} missing={stats.missing} "
        f"bad_fnm={stats.bad_fnm} failed={stats.failed}"
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


def _run_dry(rows: list[FileRow], root: Path, stats: RunStats) -> None:
    photos_by_oid: dict[tuple[Any, str | None], int] = {}
    for row in rows:
        try:
            photos = photos_for_fnm(row.fnm, root)
        except SituationPathError as exc:
            stats.bad_fnm += 1
            logger.warning("dry oid=%s ono=%s bad_fnm=%r (%s)", row.oid, row.ono, row.fnm, exc)
            continue
        if not photos:
            stats.missing += 1
            logger.warning("dry oid=%s ono=%s missing %r", row.oid, row.ono, row.fnm)
            continue
        stats.photos_found += len(photos)
        key = (row.oid, row.ono)
        photos_by_oid[key] = photos_by_oid.get(key, 0) + len(photos)
    for (oid, ono), count in photos_by_oid.items():
        logger.info("dry oid=%s ono=%s photos=%s", oid, ono, count)


def _run_upload(
    rows: list[FileRow],
    root: Path,
    stats: RunStats,
    uploaded_relpaths: set[str],
) -> None:
    api: MsiHolesClient | None = None
    for row in rows:
        try:
            photos = photos_for_fnm(row.fnm, root)
            rel_hint = relpath_from_fnm(row.fnm)
        except SituationPathError as exc:
            stats.bad_fnm += 1
            _upsert_log(
                source_oid=row.oid,
                ono=row.ono,
                source_fnm=row.fnm,
                source_relpath=f"bad-fnm/{row.oid}:{row.fnm}",
                status="skipped_missing",
                error_message=str(exc),
            )
            logger.warning("oid=%s ono=%s skip=%s fnm=%r", row.oid, row.ono, exc, row.fnm)
            continue

        if not photos:
            stats.missing += 1
            _upsert_log(
                source_oid=row.oid,
                ono=row.ono,
                source_fnm=row.fnm,
                source_relpath=rel_hint,
                status="skipped_missing",
                error_message="missing",
            )
            logger.warning("oid=%s ono=%s missing fnm=%r", row.oid, row.ono, row.fnm)
            continue

        stats.photos_found += len(photos)
        for path in photos:
            rel = file_relpath(path, root)
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
                    ono=row.ono,
                    source_fnm=row.fnm,
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
                    ono=row.ono,
                    source_fnm=row.fnm,
                    source_relpath=rel,
                    status="failed",
                    error_message=str(exc),
                )
    if api is not None:
        api.close()
