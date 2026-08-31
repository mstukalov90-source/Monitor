"""Select CRM snapshot photos and send confirm true/false to genplan (PATCH)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

from collector.msi_holes_client import MsiHolesClient

TRUE_SNAPSHOT_TABLES: tuple[str, ...] = (
    "crm.tasks_field",
    "crm.tasks_delay",
    "crm.tasks_done_legal",
    "crm.tasks_done_illegal",
)
FALSE_SNAPSHOT_TABLE = "crm.tasks_clear"

PHOTO_UUID_SQL = (
    "NULLIF(TRIM(COALESCE(NULLIF(TRIM(s.photo_uuid), ''), t.photo_uuid)), '')"
)
CAM_ID_SQL = "NULLIF(btrim(pm.cam_id::text), '')"

STATUS_SENT = "sent"
STATUS_ERROR = "error"
STATUS_SKIPPED_CAM = "skipped_cam"


def _snapshot_union_sql(tables: tuple[str, ...]) -> str:
    return " UNION ALL ".join(
        f"SELECT photo_uuid, task_key FROM {table}" for table in tables
    )


_TRUE_UNION_SQL = _snapshot_union_sql(TRUE_SNAPSHOT_TABLES)

_TRUE_ROWS_CTE = f"""
true_rows AS (
    SELECT DISTINCT
        {PHOTO_UUID_SQL} AS photo_uuid,
        {CAM_ID_SQL} AS cam_id
    FROM (
        {_TRUE_UNION_SQL}
    ) s
    JOIN crm.tasks t ON t.key = s.task_key
    JOIN genplan.photo_meta pm ON pm.uuid::text = {PHOTO_UUID_SQL}
    WHERE {PHOTO_UUID_SQL} IS NOT NULL
      AND {CAM_ID_SQL} IS NOT NULL
)
"""

TRUE_CANDIDATES_SQL = f"""
WITH {_TRUE_ROWS_CTE}
SELECT photo_uuid, cam_id
FROM true_rows
ORDER BY photo_uuid
"""

FALSE_CANDIDATES_SQL = f"""
WITH {_TRUE_ROWS_CTE},
clear_rows AS (
    SELECT DISTINCT
        {PHOTO_UUID_SQL} AS photo_uuid,
        {CAM_ID_SQL} AS cam_id
    FROM {FALSE_SNAPSHOT_TABLE} s
    JOIN crm.tasks t ON t.key = s.task_key
    JOIN genplan.photo_meta pm ON pm.uuid::text = {PHOTO_UUID_SQL}
    WHERE {PHOTO_UUID_SQL} IS NOT NULL
      AND {CAM_ID_SQL} IS NOT NULL
)
SELECT c.photo_uuid, c.cam_id
FROM clear_rows c
WHERE NOT EXISTS (
        SELECT 1 FROM true_rows tr WHERE tr.photo_uuid = c.photo_uuid
    )
  AND NOT EXISTS (
        SELECT 1 FROM true_rows tr WHERE tr.cam_id = c.cam_id
    )
ORDER BY c.photo_uuid
"""

COUNT_SKIPPED_NULL_CAM_SQL = f"""
SELECT count(*) FROM (
    SELECT DISTINCT {PHOTO_UUID_SQL} AS photo_uuid
    FROM (
        {_TRUE_UNION_SQL}
        UNION ALL
        SELECT photo_uuid, task_key FROM {FALSE_SNAPSHOT_TABLE}
    ) s
    JOIN crm.tasks t ON t.key = s.task_key
    WHERE {PHOTO_UUID_SQL} IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM genplan.photo_meta pm
          WHERE pm.uuid::text = {PHOTO_UUID_SQL}
            AND {CAM_ID_SQL} IS NOT NULL
      )
) q
"""

COUNT_SKIPPED_CAM_SQL = f"""
WITH {_TRUE_ROWS_CTE},
clear_rows AS (
    SELECT DISTINCT
        {PHOTO_UUID_SQL} AS photo_uuid,
        {CAM_ID_SQL} AS cam_id
    FROM {FALSE_SNAPSHOT_TABLE} s
    JOIN crm.tasks t ON t.key = s.task_key
    JOIN genplan.photo_meta pm ON pm.uuid::text = {PHOTO_UUID_SQL}
    WHERE {PHOTO_UUID_SQL} IS NOT NULL
      AND {CAM_ID_SQL} IS NOT NULL
)
SELECT count(*)
FROM clear_rows c
WHERE NOT EXISTS (
        SELECT 1 FROM true_rows tr WHERE tr.photo_uuid = c.photo_uuid
    )
  AND EXISTS (
        SELECT 1 FROM true_rows tr WHERE tr.cam_id = c.cam_id
    )
"""

SENT_CONFIRMS_SQL = """
SELECT photo_uuid, confirm
FROM genplan.photo_confirm_log
WHERE status = 'sent'
"""

UPSERT_CONFIRM_LOG_SQL = """
INSERT INTO genplan.photo_confirm_log (
    photo_uuid, confirm, status, http_status, error_message
) VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (photo_uuid) DO UPDATE SET
    confirm = EXCLUDED.confirm,
    status = EXCLUDED.status,
    http_status = EXCLUDED.http_status,
    error_message = EXCLUDED.error_message,
    sent_at = NOW()
"""


@dataclass(frozen=True)
class ConfirmCandidate:
    photo_uuid: str
    cam_id: str
    confirm: bool


@dataclass
class SendResult:
    sent_true: int = 0
    sent_false: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


def apply_limit(rows: list[ConfirmCandidate], limit: int) -> list[ConfirmCandidate]:
    if limit <= 0:
        return rows
    return rows[:limit]


def exclude_already_sent(
    candidates: Iterable[ConfirmCandidate],
    sent: dict[str, bool],
) -> tuple[list[ConfirmCandidate], int]:
    pending: list[ConfirmCandidate] = []
    skipped = 0
    for candidate in candidates:
        if sent.get(candidate.photo_uuid) is candidate.confirm:
            skipped += 1
        else:
            pending.append(candidate)
    return pending, skipped


def _rows_to_candidates(rows: Iterable[Any], *, confirm: bool) -> list[ConfirmCandidate]:
    result: list[ConfirmCandidate] = []
    for row in rows:
        uuid = str(row[0]).strip()
        cam_id = str(row[1]).strip()
        if not uuid or not cam_id:
            continue
        result.append(ConfirmCandidate(photo_uuid=uuid, cam_id=cam_id, confirm=confirm))
    return result


def load_true_candidates(cur: Any) -> list[ConfirmCandidate]:
    cur.execute(TRUE_CANDIDATES_SQL)
    return _rows_to_candidates(cur.fetchall(), confirm=True)


def load_false_candidates(cur: Any) -> list[ConfirmCandidate]:
    cur.execute(FALSE_CANDIDATES_SQL)
    return _rows_to_candidates(cur.fetchall(), confirm=False)


def load_sent_confirms(cur: Any) -> dict[str, bool]:
    cur.execute(SENT_CONFIRMS_SQL)
    return {str(row[0]): bool(row[1]) for row in cur.fetchall()}


def count_skipped_null_cam(cur: Any) -> int:
    cur.execute(COUNT_SKIPPED_NULL_CAM_SQL)
    row = cur.fetchone()
    return int(row[0] if row else 0)


def count_skipped_cam(cur: Any) -> int:
    cur.execute(COUNT_SKIPPED_CAM_SQL)
    row = cur.fetchone()
    return int(row[0] if row else 0)


def upsert_confirm_log(
    cur: Any,
    *,
    photo_uuid: str,
    confirm: bool,
    status: str,
    http_status: int | None = None,
    error_message: str | None = None,
) -> None:
    cur.execute(
        UPSERT_CONFIRM_LOG_SQL,
        (photo_uuid, confirm, status, http_status, error_message),
    )


def send_confirms(
    api: MsiHolesClient,
    conn: Any,
    candidates: Iterable[ConfirmCandidate],
) -> SendResult:
    result = SendResult()
    for candidate in candidates:
        try:
            resp = api.confirm_photo(candidate.photo_uuid, candidate.confirm)
            resp.raise_for_status()
            with conn.cursor() as cur:
                upsert_confirm_log(
                    cur,
                    photo_uuid=candidate.photo_uuid,
                    confirm=candidate.confirm,
                    status=STATUS_SENT,
                    http_status=resp.status_code,
                )
            conn.commit()
            if candidate.confirm:
                result.sent_true += 1
            else:
                result.sent_false += 1
        except httpx.HTTPStatusError as exc:
            result.errors += 1
            result.error_details.append(f"{candidate.photo_uuid}: {exc}")
            with conn.cursor() as cur:
                upsert_confirm_log(
                    cur,
                    photo_uuid=candidate.photo_uuid,
                    confirm=candidate.confirm,
                    status=STATUS_ERROR,
                    http_status=exc.response.status_code,
                    error_message=str(exc)[:1000],
                )
            conn.commit()
        except (httpx.HTTPError, ValueError) as exc:
            result.errors += 1
            result.error_details.append(f"{candidate.photo_uuid}: {exc}")
            with conn.cursor() as cur:
                upsert_confirm_log(
                    cur,
                    photo_uuid=candidate.photo_uuid,
                    confirm=candidate.confirm,
                    status=STATUS_ERROR,
                    error_message=str(exc)[:1000],
                )
            conn.commit()
    return result
