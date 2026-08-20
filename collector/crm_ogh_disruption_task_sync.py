"""Auto-create crm.tasks from odh_export.ogh-disruption."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from collector.crm_photo_task_sync import CRM_GROUP_DISRUPTIONS
from collector.crm_task_sync import CrmTaskSyncResult
from collector.crm_task_sync_config import ETL_SYNC_LOGIN, TASK_ID_COLUMNS

logger = logging.getLogger(__name__)

SOURCE_TABLE_SQL = 'odh_export."ogh-disruption"'
SOURCE_TABLE_NAME = "odh_export.ogh-disruption"
TASK_COLUMN = "ogh_id"
GEOM_COLUMN = "geometry"


def _business_id_expr() -> str:
    return "NULLIF(TRIM(t.\"id\"::text), '')"


def _id_values_for_insert() -> str:
    business_id = _business_id_expr()
    return ", ".join(
        business_id if col == TASK_COLUMN else "NULL"
        for col in TASK_ID_COLUMNS
    )


def _geom_hash_expr(geom_col: str) -> str:
    return f"md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid({geom_col}), 4326)))"


def _etl_audit() -> list[str]:
    stamp = datetime.now(timezone.utc).isoformat()
    return [ETL_SYNC_LOGIN, stamp]


def _refresh_task_area_keys(cur: Any) -> None:
    cur.execute(
        """
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'crm' AND p.proname = 'refresh_task_area_keys'
        """
    )
    if cur.fetchone() is None:
        logger.info("crm.refresh_task_area_keys() missing, skip area_key refresh")
        return
    cur.execute("CALL crm.refresh_task_area_keys()")


def _insert_ogh_disruption_tasks(cur: Any) -> int:
    business_id = _business_id_expr()
    id_values = _id_values_for_insert()
    audit = _etl_audit()
    insert_columns = ["type"] + list(TASK_ID_COLUMNS) + ["user_created", "user_last_edit"]
    col_list = ", ".join(f'"{col}"' for col in insert_columns)

    where = " AND ".join(
        [
            f't."{GEOM_COLUMN}" IS NOT NULL',
            f"{business_id} IS NOT NULL",
            f"""NOT EXISTS (
                SELECT 1 FROM crm.tasks ct
                WHERE ct."{TASK_COLUMN}" = {business_id}
            )""",
        ]
    )
    query = f"""
        INSERT INTO crm.tasks ({col_list})
        SELECT %s, {id_values}, %s::text[], %s::text[]
        FROM {SOURCE_TABLE_SQL} t
        WHERE {where}
    """
    cur.execute(query, [CRM_GROUP_DISRUPTIONS, audit, audit])
    return cur.rowcount


def _anchor_ogh_disruption_tasks(cur: Any) -> int:
    business_id = _business_id_expr()
    geom_col = f't."{GEOM_COLUMN}"'
    query = f"""
        UPDATE crm.tasks ct
        SET source_table = %s,
            source_row_id = t.id,
            source_geom_hash = {_geom_hash_expr(geom_col)}
        FROM {SOURCE_TABLE_SQL} t
        WHERE ct.source_row_id IS NULL
          AND ct."{TASK_COLUMN}" = {business_id}
    """
    cur.execute(query, [SOURCE_TABLE_NAME])
    return cur.rowcount


def sync_ogh_disruption_tasks(cur: Any) -> CrmTaskSyncResult:
    """Insert missing crm.tasks for odh_export.ogh-disruption rows."""
    result = CrmTaskSyncResult()
    result.inserted = _insert_ogh_disruption_tasks(cur)
    anchored = _anchor_ogh_disruption_tasks(cur)
    result.linked = anchored
    _refresh_task_area_keys(cur)

    logger.info(
        "crm_ogh_disruption_task_sync %s: inserted=%s anchored=%s",
        SOURCE_TABLE_NAME,
        result.inserted,
        anchored,
    )
    return result
