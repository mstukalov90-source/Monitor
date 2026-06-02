"""Derive polygon rows from nearly-closed lines in data_mos items tables."""

from __future__ import annotations

import json
import logging

from psycopg2.extensions import cursor as Cursor
from shapely import from_wkb

from collector.data_mos_schema import prepare_value
from collector.geom_line_to_polygon import try_line_to_polygon

logger = logging.getLogger(__name__)

TARGET_TABLES = frozenset({"items_2855", "items_62461", "items_62501"})
_SKIP_COLUMNS = frozenset({"id", "geom", "loaded_at", "derived_from_id"})
_UDT_TO_PG = {
    "jsonb": "JSONB",
    "int8": "BIGINT",
    "float8": "DOUBLE PRECISION",
    "bool": "BOOLEAN",
    "text": "TEXT",
}


def _table_name(qualified_table: str) -> str:
    return qualified_table.split(".", 1)[-1]


def ensure_derived_from_id(cur: Cursor, qualified_table: str) -> None:
    cur.execute(
        f"ALTER TABLE {qualified_table} "
        f"ADD COLUMN IF NOT EXISTS derived_from_id BIGINT"
    )


def _attribute_columns(cur: Cursor, schema: str, table: str) -> tuple[list[str], dict[str, str]]:
    cur.execute(
        """
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    attr_cols: list[str] = []
    col_types: dict[str, str] = {}
    for column_name, udt_name in cur.fetchall():
        if column_name in _SKIP_COLUMNS:
            continue
        attr_cols.append(column_name)
        col_types[column_name] = _UDT_TO_PG.get(udt_name, "TEXT")
    return attr_cols, col_types


def _prepare_attr_values(
    attr_cols: list[str],
    col_types: dict[str, str],
    attr_values: tuple,
) -> list:
    return [
        prepare_value(value, col_types[column])
        for column, value in zip(attr_cols, attr_values)
    ]


def derive_polygons_from_lines(
    cur: Cursor,
    qualified_table: str,
    threshold: float = 0.1,
) -> int:
    """
    Insert polygon rows copied from eligible line rows.

    Returns the number of polygon rows inserted.
    """
    table = _table_name(qualified_table)
    if table not in TARGET_TABLES:
        return 0

    schema, _ = qualified_table.split(".", 1)
    ensure_derived_from_id(cur, qualified_table)
    attr_cols, col_types = _attribute_columns(cur, schema, table)

    quoted_attrs = ", ".join(f'"{col}"' for col in attr_cols)
    select_attrs = quoted_attrs if attr_cols else ""
    cur.execute(
        f"""
        SELECT id, ST_AsEWKB(geom) AS geom_wkb
               {", " + select_attrs if select_attrs else ""}
        FROM {qualified_table}
        WHERE geom IS NOT NULL
          AND derived_from_id IS NULL
          AND ST_GeometryType(geom) IN ('ST_LineString', 'ST_MultiLineString')
          AND NOT EXISTS (
              SELECT 1
              FROM {qualified_table} derived
              WHERE derived.derived_from_id = {qualified_table}.id
          )
        """
    )
    rows = cur.fetchall()

    inserted = 0
    skipped = 0
    for row in rows:
        source_id = row[0]
        geom_wkb = row[1]
        attr_values = row[2:]

        line_geom = from_wkb(bytes(geom_wkb))
        polygon = try_line_to_polygon(line_geom, threshold=threshold)
        if polygon is None:
            skipped += 1
            continue

        geom_json = json.dumps(polygon.__geo_interface__)
        if attr_cols:
            prepared_attrs = _prepare_attr_values(attr_cols, col_types, attr_values)
            col_list = f"{quoted_attrs}, geom, derived_from_id"
            placeholders = ", ".join(["%s"] * len(attr_cols))
            placeholders += ", ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s"
            cur.execute(
                f"INSERT INTO {qualified_table} ({col_list}) VALUES ({placeholders})",
                [*prepared_attrs, geom_json, source_id],
            )
        else:
            cur.execute(
                f"""
                INSERT INTO {qualified_table} (geom, derived_from_id)
                VALUES (ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)
                """,
                (geom_json, source_id),
            )
        inserted += 1

    logger.info(
        "Derived polygons in %s: %s inserted, %s skipped (of %s line rows)",
        qualified_table,
        inserted,
        skipped,
        len(rows),
    )
    return inserted
