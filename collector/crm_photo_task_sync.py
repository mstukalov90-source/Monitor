"""Auto-create crm.tasks from genplan.photo_meta and lens.reports."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from collector.crm_task_sync import CrmTaskSyncResult
from collector.crm_task_sync_config import ETL_SYNC_LOGIN, TASK_ID_COLUMNS

logger = logging.getLogger(__name__)

CRM_GROUP_DISRUPTIONS = "Разрытия"


@dataclass(frozen=True)
class PhotoLayerSync:
    source_table: str
    group_name: str
    task_column: str
    source_field: str
    sql_filter: str | None = None
    geom_column: str = "geom"


AI_PHOTO_SYNC = PhotoLayerSync(
    source_table="genplan.photo_meta",
    group_name=CRM_GROUP_DISRUPTIONS,
    task_column="photo_uuid",
    source_field="uuid",
    sql_filter="t.disruption IS TRUE",
)

LENS_PHOTO_SYNC = PhotoLayerSync(
    source_table="lens.reports",
    group_name=CRM_GROUP_DISRUPTIONS,
    task_column="photo_lens",
    source_field="external_report_id",
)


def _business_id_expr(cfg: PhotoLayerSync) -> str:
    return f"NULLIF(TRIM(t.\"{cfg.source_field}\"::text), '')"


def _id_values_for_insert(cfg: PhotoLayerSync) -> str:
    task_column = cfg.task_column
    business_id = _business_id_expr(cfg)
    return ", ".join(
        business_id if col == task_column else "NULL"
        for col in TASK_ID_COLUMNS
    )


def _geom_hash_expr(geom_col: str) -> str:
    return f"md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid({geom_col}), 4326)))"


def _etl_audit() -> list[str]:
    stamp = datetime.now(timezone.utc).isoformat()
    return [ETL_SYNC_LOGIN, stamp]


def _insert_photo_tasks(cur: Any, cfg: PhotoLayerSync) -> int:
    task_column = cfg.task_column
    business_id = _business_id_expr(cfg)
    id_values = _id_values_for_insert(cfg)
    audit = _etl_audit()
    insert_columns = ["type"] + list(TASK_ID_COLUMNS) + ["user_created", "user_last_edit"]
    col_list = ", ".join(f'"{col}"' for col in insert_columns)

    filters = [
        f't."{cfg.geom_column}" IS NOT NULL',
        f"{business_id} IS NOT NULL",
        f"""NOT EXISTS (
            SELECT 1 FROM crm.tasks ct
            WHERE ct."{task_column}" = {business_id}
        )""",
    ]
    if cfg.sql_filter:
        filters.append(cfg.sql_filter)

    where = " AND ".join(filters)
    query = f"""
        INSERT INTO crm.tasks ({col_list})
        SELECT %s, {id_values}, %s::text[], %s::text[]
        FROM {cfg.source_table} t
        WHERE {where}
    """
    cur.execute(query, [cfg.group_name, audit, audit])
    return cur.rowcount


def _anchor_photo_tasks(cur: Any, cfg: PhotoLayerSync) -> int:
    business_id = _business_id_expr(cfg)
    task_column = cfg.task_column
    geom_col = f't."{cfg.geom_column}"'
    query = f"""
        UPDATE crm.tasks ct
        SET source_table = %s,
            source_row_id = t.id,
            source_geom_hash = {_geom_hash_expr(geom_col)}
        FROM {cfg.source_table} t
        WHERE ct.source_row_id IS NULL
          AND ct."{task_column}" = {business_id}
    """
    cur.execute(query, [cfg.source_table])
    return cur.rowcount


def sync_photo_layer_tasks(cur: Any, cfg: PhotoLayerSync) -> CrmTaskSyncResult:
    """Insert missing crm.tasks for one photo layer."""
    result = CrmTaskSyncResult()
    result.inserted = _insert_photo_tasks(cur, cfg)
    anchored = _anchor_photo_tasks(cur, cfg)
    result.linked = anchored

    logger.info(
        "crm_photo_task_sync %s: inserted=%s anchored=%s",
        cfg.source_table,
        result.inserted,
        anchored,
    )
    return result


def sync_ai_photo_tasks(cur: Any) -> CrmTaskSyncResult:
    return sync_photo_layer_tasks(cur, AI_PHOTO_SYNC)


def sync_lens_photo_tasks(cur: Any) -> CrmTaskSyncResult:
    return sync_photo_layer_tasks(cur, LENS_PHOTO_SYNC)
