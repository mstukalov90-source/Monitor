"""Auto-create crm.tasks after data_mos ETL for scoped geometry subgroups."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from collector.crm_task_sync_config import (
    ETL_SYNC_LOGIN,
    SERVICE_TASK_SYNC,
    SplitLayerSync,
    ServiceTaskSync,
    TASK_ID_COLUMNS,
)
from collector.data_mos_tasked import refresh_all_tasked_parents

logger = logging.getLogger(__name__)


@dataclass
class CrmTaskSyncResult:
    inserted: int = 0
    linked: int = 0
    tasked_parents: int = 0


def _task_id_conflict_clause(task_column: str) -> str:
    return (
        f'ON CONFLICT ("{task_column}") '
        f'WHERE "{task_column}" IS NOT NULL DO NOTHING'
    )


def _geom_hash_expr(geom_col: str = "t.geom") -> str:
    return f"md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid({geom_col}), 4326)))"


def _business_id_expr(geom_type: str) -> str:
    return f"CONCAT('{geom_type}:', t.id::text)"


def _id_values(task_column: str) -> str:
    return ", ".join(
        "src.business_id" if col == task_column else "NULL"
        for col in TASK_ID_COLUMNS
    )


def _etl_audit() -> list[str]:
    stamp = datetime.now(timezone.utc).isoformat()
    return [ETL_SYNC_LOGIN, stamp]


def _insert_new_tasks(
    cur: Any,
    cfg: ServiceTaskSync,
    layer: SplitLayerSync,
) -> int:
    task_column = cfg.task_column
    business_id_expr = _business_id_expr(layer.geom_type)
    id_values = _id_values(task_column)
    audit = _etl_audit()
    insert_columns = ["type"] + list(TASK_ID_COLUMNS) + ["user_created", "user_last_edit"]
    col_list = ", ".join(f'"{col}"' for col in insert_columns)

    query = f"""
        INSERT INTO crm.tasks ({col_list})
        SELECT %s, {id_values}, %s::text[], %s::text[]
        FROM (
            SELECT DISTINCT ON ({business_id_expr})
                {business_id_expr} AS business_id
            FROM {layer.items_table} t
            WHERE t.geom IS NOT NULL
              AND t.task_key IS NULL
              AND {business_id_expr} <> ''
            ORDER BY {business_id_expr}, t.id
        ) src
        {_task_id_conflict_clause(task_column)}
    """
    cur.execute(query, [cfg.group_name, audit, audit])
    return cur.rowcount


def _link_split_rows(cur: Any, cfg: ServiceTaskSync, layer: SplitLayerSync) -> int:
    business_id_expr = _business_id_expr(layer.geom_type)
    task_column = cfg.task_column
    items_table = layer.items_table

    link_query = f"""
        UPDATE {items_table} t
        SET task_key = ct.key
        FROM crm.tasks ct
        WHERE t.task_key IS NULL
          AND t.geom IS NOT NULL
          AND ct."{task_column}" = {business_id_expr}
          AND NOT EXISTS (
              SELECT 1 FROM {items_table} occupied
              WHERE occupied.task_key = ct.key AND occupied.id <> t.id
          )
    """
    cur.execute(link_query)
    linked = cur.rowcount

    anchor_query = f"""
        UPDATE crm.tasks ct
        SET source_table = %s,
            source_row_id = t.id,
            source_global_id = t.global_id,
            source_geom_hash = {_geom_hash_expr("t.geom")}
        FROM {items_table} t
        WHERE ct.key = t.task_key
          AND t.task_key IS NOT NULL
          AND ct.source_row_id IS NULL
          AND ct."{task_column}" = {business_id_expr}
    """
    cur.execute(anchor_query, [items_table])
    return linked


def sync_crm_tasks_after_etl(cur: Any, parent_table_name: str) -> CrmTaskSyncResult:
    """Run after geom split for one data_mos service parent table."""
    cfg = SERVICE_TASK_SYNC.get(parent_table_name)
    if cfg is None:
        return CrmTaskSyncResult()

    result = CrmTaskSyncResult()
    for layer in cfg.split_layers:
        result.inserted += _insert_new_tasks(cur, cfg, layer)
        result.linked += _link_split_rows(cur, cfg, layer)

    result.tasked_parents = refresh_all_tasked_parents(cur, cfg.parent_table)
    refresh_task_area_keys(cur)

    logger.info(
        "crm_task_sync %s: inserted=%s linked=%s tasked_parents=%s",
        parent_table_name,
        result.inserted,
        result.linked,
        result.tasked_parents,
    )
    return result


def refresh_task_area_keys(cur: Any) -> None:
    """Recompute crm.tasks.area_key from geometry ∩ crm.tasks_area."""
    cur.execute("CALL crm.refresh_task_area_keys()")
