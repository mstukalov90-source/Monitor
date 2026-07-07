"""Parent items_* tasked flag helpers."""

from __future__ import annotations

from typing import Any

from collector.data_mos_geom_split import SPLIT_SOURCE_TABLES

PARENT_TABLES = SPLIT_SOURCE_TABLES


def ensure_tasked_column(cur: Any, qualified_parent: str) -> None:
    cur.execute(
        f"ALTER TABLE {qualified_parent} "
        f"ADD COLUMN IF NOT EXISTS tasked BOOLEAN NOT NULL DEFAULT false"
    )


def is_parent_tasked(cur: Any, qualified_parent: str, row_id: int) -> bool:
    cur.execute(
        f"SELECT tasked FROM {qualified_parent} WHERE id = %s",
        (row_id,),
    )
    row = cur.fetchone()
    return bool(row[0]) if row else False


def set_parent_tasked(cur: Any, qualified_parent: str, parent_id: int, tasked: bool) -> None:
    cur.execute(
        f"UPDATE {qualified_parent} SET tasked = %s WHERE id = %s",
        (tasked, parent_id),
    )


def refresh_parent_tasked(cur: Any, qualified_parent: str, parent_id: int) -> None:
    """Set tasked=true if any split child for parent_id has task_key."""
    schema, table = qualified_parent.split(".", 1)
    tasked = False
    for suffix in ("_points", "_lines", "_polygons"):
        split_q = f"{schema}.{table}{suffix}"
        cur.execute(
            f"""
            SELECT 1 FROM {split_q}
            WHERE source_id = %s AND task_key IS NOT NULL
            LIMIT 1
            """,
            (parent_id,),
        )
        if cur.fetchone():
            tasked = True
            break
    set_parent_tasked(cur, qualified_parent, parent_id, tasked)


def refresh_all_tasked_parents(cur: Any, qualified_parent: str) -> int:
    schema, table = qualified_parent.split(".", 1)
    conditions = " OR ".join(
        f"""
        EXISTS (
            SELECT 1 FROM {schema}.{table}{suffix} c
            WHERE c.source_id = p.id AND c.task_key IS NOT NULL
        )
        """.strip()
        for suffix in ("_points", "_lines", "_polygons")
    )
    cur.execute(
        f"""
        UPDATE {qualified_parent} p
        SET tasked = ({conditions})
        """
    )
    return cur.rowcount


def tasked_child_delete_guard(qualified_parent: str, split_alias: str = "target") -> str:
    return f"""
        AND NOT EXISTS (
            SELECT 1 FROM {qualified_parent} p
            WHERE p.id = {split_alias}.source_id AND p.tasked IS TRUE
        )
    """
