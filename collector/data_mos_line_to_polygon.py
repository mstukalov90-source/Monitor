"""Derive polygon rows from nearly-closed lines in data_mos items_* (Python/Shapely)."""

from __future__ import annotations

import json
import logging

from psycopg2.extensions import cursor as Cursor
from shapely import from_wkb
from shapely.geometry import Polygon
from shapely.validation import make_valid

from collector.data_mos_geom_split import SPLIT_SOURCE_TABLES
from collector.data_mos_schema import prepare_value
from collector.geom_line_to_polygon import iter_line_parts, try_line_to_polygon

logger = logging.getLogger(__name__)

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


def attribute_columns(cur: Cursor, schema: str, table: str) -> tuple[list[str], dict[str, str]]:
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


def _insert_derived_polygon(
    cur: Cursor,
    qualified_table: str,
    source_id: int,
    polygon: Polygon,
    attr_cols: list[str],
    col_types: dict[str, str],
    attr_values: tuple,
) -> None:
    geom_json = json.dumps(polygon.__geo_interface__)
    if attr_cols:
        quoted_attrs = ", ".join(f'"{col}"' for col in attr_cols)
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


def _derive_from_line_rows(
    cur: Cursor,
    qualified_table: str,
    attr_cols: list[str],
    col_types: dict[str, str],
    rows: list,
    threshold: float,
) -> tuple[int, int]:
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

        _insert_derived_polygon(
            cur, qualified_table, source_id, polygon, attr_cols, col_types, attr_values,
        )
        inserted += 1
    return inserted, skipped


def _derive_from_geometry_collections(
    cur: Cursor,
    qualified_table: str,
    attr_cols: list[str],
    col_types: dict[str, str],
    threshold: float,
) -> tuple[int, int]:
    select_attrs = ", ".join(f'"{col}"' for col in attr_cols) if attr_cols else ""
    cur.execute(
        f"""
        SELECT id, ST_AsEWKB(geom) AS geom_wkb
               {", " + select_attrs if select_attrs else ""}
        FROM {qualified_table}
        WHERE geom IS NOT NULL
          AND derived_from_id IS NULL
          AND ST_GeometryType(geom) = 'ST_GeometryCollection'
        """
    )
    rows = cur.fetchall()

    inserted = 0
    skipped = 0
    for row in rows:
        source_id = row[0]
        geom_wkb = row[1]
        attr_values = row[2:]

        root = make_valid(from_wkb(bytes(geom_wkb)))
        for line_part in iter_line_parts(root):
            polygon = try_line_to_polygon(line_part, threshold=threshold)
            if polygon is None:
                skipped += 1
                continue
            _insert_derived_polygon(
                cur,
                qualified_table,
                source_id,
                polygon,
                attr_cols,
                col_types,
                attr_values,
            )
            inserted += 1

    return inserted, skipped


def derive_polygons_from_lines(
    cur: Cursor,
    qualified_table: str,
    threshold: float = 0.1,
) -> int:
    """
    Insert polygon rows from standalone lines and line parts inside GeometryCollection.

    Returns the number of polygon rows inserted.
    """
    table = _table_name(qualified_table)
    if table not in SPLIT_SOURCE_TABLES:
        return 0

    schema, _ = qualified_table.split(".", 1)
    ensure_derived_from_id(cur, qualified_table)
    attr_cols, col_types = attribute_columns(cur, schema, table)

    select_attrs = ", ".join(f'"{col}"' for col in attr_cols) if attr_cols else ""
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
    line_rows = cur.fetchall()

    line_inserted, line_skipped = _derive_from_line_rows(
        cur, qualified_table, attr_cols, col_types, line_rows, threshold,
    )
    gc_inserted, gc_skipped = _derive_from_geometry_collections(
        cur, qualified_table, attr_cols, col_types, threshold,
    )

    inserted = line_inserted + gc_inserted
    logger.info(
        "Derived polygons in %s: %s inserted (%s from lines, %s from collections), "
        "%s skipped (%s lines, %s collection parts)",
        qualified_table,
        inserted,
        line_inserted,
        gc_inserted,
        line_skipped + gc_skipped,
        line_skipped,
        gc_skipped,
    )
    return inserted
