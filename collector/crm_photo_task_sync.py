"""Auto-create crm.tasks from genplan.photo_meta and lens.reports."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from collector.crm_task_sync import CrmTaskSyncResult, refresh_task_area_keys
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


def _etl_login_sql() -> str:
    return "'" + ETL_SYNC_LOGIN.replace("'", "''") + "'"


def _eligible_cam_task_exists_sql(cam_id_expr: str) -> str:
    """True when an ETL-owned, unobserved crm.tasks row already covers this camera."""
    return f"""EXISTS (
            SELECT 1
            FROM crm.tasks ct
            JOIN genplan.photo_meta pm ON pm.uuid = ct.photo_uuid
            WHERE pm.cam_id IS NOT NULL
              AND pm.cam_id = {cam_id_expr}
              AND ct.field_observed IS NOT TRUE
              AND {_etl_login_sql()} = ANY(ct.user_last_edit)
        )"""


def _reuse_ai_photo_tasks(cur: Any) -> int:
    """Point the latest eligible ETL task per camera at the newest photo_meta uuid."""
    audit = _etl_audit()
    geom_hash = _geom_hash_expr("src.geom")
    query = f"""
        UPDATE crm.tasks ct
        SET photo_uuid = src.uuid,
            source_table = %s,
            source_row_id = src.id,
            source_geom_hash = {geom_hash},
            user_last_edit = %s::text[]
        FROM (
            SELECT DISTINCT ON (t.cam_id)
                t.id,
                NULLIF(TRIM(t.uuid::text), '') AS uuid,
                t.cam_id,
                t.geom
            FROM genplan.photo_meta t
            WHERE t.disruption IS TRUE
              AND t.geom IS NOT NULL
              AND t.cam_id IS NOT NULL
              AND NULLIF(TRIM(t.uuid::text), '') IS NOT NULL
            ORDER BY t.cam_id, t.id DESC
        ) src
        JOIN LATERAL (
            SELECT ct2.key
            FROM crm.tasks ct2
            JOIN genplan.photo_meta old_pm ON old_pm.uuid = ct2.photo_uuid
            WHERE old_pm.cam_id IS NOT NULL
              AND old_pm.cam_id = src.cam_id
              AND ct2.field_observed IS NOT TRUE
              AND {_etl_login_sql()} = ANY(ct2.user_last_edit)
            ORDER BY ct2.key DESC
            LIMIT 1
        ) existing ON TRUE
        WHERE ct.key = existing.key
          AND ct.photo_uuid IS DISTINCT FROM src.uuid
    """
    cur.execute(query, [AI_PHOTO_SYNC.source_table, audit])
    return cur.rowcount


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
    if cfg == AI_PHOTO_SYNC:
        filters.append(
            f"""(
                t.cam_id IS NULL
                OR NOT {_eligible_cam_task_exists_sql("t.cam_id")}
            )"""
        )

    where = " AND ".join(filters)
    if cfg == AI_PHOTO_SYNC:
        distinct_key = f"COALESCE(t.cam_id::text, {business_id})"
        query = f"""
            INSERT INTO crm.tasks ({col_list})
            SELECT %s, {id_values}, %s::text[], %s::text[]
            FROM (
                SELECT DISTINCT ON ({distinct_key})
                    t.*
                FROM {cfg.source_table} t
                WHERE {where}
                ORDER BY {distinct_key}, t.id DESC
            ) t
        """
    else:
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
    """Insert missing crm.tasks for one photo layer; reuse AI tasks per camera."""
    result = CrmTaskSyncResult()
    if cfg == AI_PHOTO_SYNC:
        result.updated = _reuse_ai_photo_tasks(cur)
    result.inserted = _insert_photo_tasks(cur, cfg)
    anchored = _anchor_photo_tasks(cur, cfg)
    result.linked = anchored
    refresh_task_area_keys(cur)

    logger.info(
        "crm_photo_task_sync %s: inserted=%s updated=%s anchored=%s",
        cfg.source_table,
        result.inserted,
        result.updated,
        anchored,
    )
    return result


def sync_ai_photo_tasks(cur: Any) -> CrmTaskSyncResult:
    return sync_photo_layer_tasks(cur, AI_PHOTO_SYNC)


def sync_lens_photo_tasks(cur: Any) -> CrmTaskSyncResult:
    return sync_photo_layer_tasks(cur, LENS_PHOTO_SYNC)
