"""Rebuild per-service points / lines / polygons tables from data_mos items_* sources."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Services that run derive_polygons_from_lines + geom_split after load.
SPLIT_SOURCE_TABLES = frozenset({
    "items_2855",
    "items_62441",
    "items_62461",
    "items_62501",
})

_POINT_TYPES = ("ST_Point", "ST_MultiPoint")
_LINE_TYPES = ("ST_LineString", "ST_MultiLineString")
_POLYGON_TYPES = ("ST_Polygon", "ST_MultiPolygon")
_ALL_ROUTED_TYPES = _POINT_TYPES + _LINE_TYPES + _POLYGON_TYPES
_GEOMETRY_COLLECTION_TYPE = "ST_GeometryCollection"


@dataclass(frozen=True)
class GeomSplitResult:
    points: int = 0
    lines: int = 0
    polygons: int = 0
    derived_polygons: int = 0
    skipped: int = 0
    collection_rows: int = 0
    collection_parts: int = 0


def _table_name(qualified_table: str) -> str:
    return qualified_table.split(".", 1)[-1]


def qualified_split_names(qualified_source: str) -> tuple[str, str, str]:
    """Return (points, lines, polygons) qualified table names for a source table."""
    schema, table = qualified_source.split(".", 1)
    return (
        f"{schema}.{table}_points",
        f"{schema}.{table}_lines",
        f"{schema}.{table}_polygons",
    )


def _valid_geom_expr(geom_col: str = "geom") -> str:
    return f"ST_SetSRID(ST_MakeValid({geom_col}), 4326)"


def _valid_geom_expr_for(geom_col: str) -> str:
    return f"ST_SetSRID(ST_MakeValid({geom_col}), 4326)"


def _collection_parts_lateral_sql(geom_col: str) -> str:
    """LATERAL subquery flattening one-level and nested GeometryCollection parts."""
    valid = _valid_geom_expr_for(geom_col)
    return f"""
        SELECT (d).geom AS part_geom
        FROM ST_Dump({valid}) AS d
        WHERE ST_GeometryType({valid}) = '{_GEOMETRY_COLLECTION_TYPE}'
          AND ST_GeometryType(ST_MakeValid((d).geom)) <> '{_GEOMETRY_COLLECTION_TYPE}'
        UNION ALL
        SELECT (d2).geom AS part_geom
        FROM ST_Dump({valid}) AS d
        CROSS JOIN LATERAL ST_Dump(ST_MakeValid((d).geom)) AS d2
        WHERE ST_GeometryType({valid}) = '{_GEOMETRY_COLLECTION_TYPE}'
          AND ST_GeometryType(ST_MakeValid((d).geom)) = '{_GEOMETRY_COLLECTION_TYPE}'
    """


def collection_insert_sql_fragment() -> str:
    """Return markers used in tests/docs for collection routing SQL."""
    return "ST_Dump"


def _valid_geom_filter(geom_col: str = "geom") -> str:
    valid = _valid_geom_expr(geom_col)
    return (
        f"{geom_col} IS NOT NULL "
        f"AND NOT ST_IsEmpty({valid})"
    )


def _ensure_split_table(
    cur: Any,
    source_qualified: str,
    target_qualified: str,
    *,
    with_derived_from_id: bool,
) -> None:
    schema, table = target_qualified.split(".", 1)
    source_schema, source_table = source_qualified.split(".", 1)
    from collector.data_mos_line_to_polygon import attribute_columns

    suffix = table

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {target_qualified} (
            id         BIGSERIAL PRIMARY KEY,
            geom       GEOMETRY(Geometry, 4326),
            loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source_id  BIGINT
        )
        """
    )
    cur.execute(
        f"ALTER TABLE {target_qualified} "
        f"ADD COLUMN IF NOT EXISTS source_id BIGINT"
    )
    if with_derived_from_id:
        cur.execute(
            f"ALTER TABLE {target_qualified} "
            f"ADD COLUMN IF NOT EXISTS derived_from_id BIGINT"
        )

    attr_cols, col_types = attribute_columns(cur, source_schema, source_table)
    for col in attr_cols:
        pg_type = col_types[col]
        cur.execute(
            f'ALTER TABLE {target_qualified} ADD COLUMN IF NOT EXISTS "{col}" {pg_type}'
        )

    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{suffix}_geom "
        f"ON {target_qualified} USING GIST (geom)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{suffix}_source_id "
        f"ON {target_qualified} (source_id)"
    )
    if with_derived_from_id:
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{suffix}_derived_from_id "
            f"ON {target_qualified} (derived_from_id) "
            f"WHERE derived_from_id IS NOT NULL"
        )


def _quoted_attr_list(attr_cols: list[str]) -> str:
    return ", ".join(f'"{col}"' for col in attr_cols)


def _insert_routed(
    cur: Any,
    source_qualified: str,
    target_qualified: str,
    attr_cols: list[str],
    geom_types: tuple[str, ...],
    *,
    with_derived_from_id: bool = False,
) -> int:
    valid_geom = _valid_geom_expr()
    geom_filter = _valid_geom_filter()
    type_list = ", ".join(f"'{t}'" for t in geom_types)

    quoted_attrs = _quoted_attr_list(attr_cols)
    insert_attrs = f"{quoted_attrs}, " if attr_cols else ""
    select_attrs = f"{quoted_attrs}, " if attr_cols else ""

    geom_select = valid_geom
    if with_derived_from_id:
        extra_insert = "derived_from_id, source_id, "
        extra_select = "derived_from_id, id AS source_id, "
    else:
        extra_insert = "source_id, "
        extra_select = "id AS source_id, "

    where_clause = (
        f"{geom_filter} AND ST_GeometryType({valid_geom}) IN ({type_list})"
    )

    cur.execute(
        f"""
        INSERT INTO {target_qualified} ({insert_attrs}geom, {extra_insert}loaded_at)
        SELECT {select_attrs}{geom_select}, {extra_select}loaded_at
        FROM {source_qualified}
        WHERE {where_clause}
        """
    )
    return cur.rowcount


def _insert_routed_from_collection(
    cur: Any,
    source_qualified: str,
    target_qualified: str,
    attr_cols: list[str],
    geom_types: tuple[str, ...],
    *,
    with_derived_from_id: bool = False,
) -> int:
    type_list = ", ".join(f"'{t}'" for t in geom_types)
    quoted_attrs = _quoted_attr_list(attr_cols)
    insert_attrs = f"{quoted_attrs}, " if attr_cols else ""
    select_attrs = f"{quoted_attrs}, " if attr_cols else ""

    part_geom = _valid_geom_expr_for("flat.part_geom")
    if with_derived_from_id:
        extra_insert = "derived_from_id, source_id, "
        extra_select = "NULL::bigint AS derived_from_id, src.id AS source_id, "
    else:
        extra_insert = "source_id, "
        extra_select = "src.id AS source_id, "

    lateral = _collection_parts_lateral_sql("src.geom")
    cur.execute(
        f"""
        INSERT INTO {target_qualified} ({insert_attrs}geom, {extra_insert}loaded_at)
        SELECT {select_attrs}{part_geom}, {extra_select}src.loaded_at
        FROM {source_qualified} AS src
        CROSS JOIN LATERAL ({lateral}) AS flat
        WHERE {_valid_geom_filter("src.geom")}
          AND ST_GeometryType({_valid_geom_expr_for("src.geom")}) = '{_GEOMETRY_COLLECTION_TYPE}'
          AND NOT ST_IsEmpty({part_geom})
          AND ST_GeometryType({part_geom}) IN ({type_list})
        """
    )
    return cur.rowcount


def _count_collection_rows(cur: Any, source_qualified: str) -> int:
    valid = _valid_geom_expr()
    cur.execute(
        f"""
        SELECT count(*) FROM {source_qualified}
        WHERE geom IS NOT NULL
          AND ST_GeometryType({valid}) = '{_GEOMETRY_COLLECTION_TYPE}'
        """
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _count_collection_parts_routed(cur: Any, source_qualified: str) -> int:
    valid_src = _valid_geom_expr_for("src.geom")
    part = _valid_geom_expr_for("flat.part_geom")
    type_list = ", ".join(f"'{t}'" for t in _ALL_ROUTED_TYPES)
    lateral = _collection_parts_lateral_sql("src.geom")
    cur.execute(
        f"""
        SELECT count(*)
        FROM {source_qualified} AS src
        CROSS JOIN LATERAL ({lateral}) AS flat
        WHERE {_valid_geom_filter("src.geom")}
          AND ST_GeometryType({valid_src}) = '{_GEOMETRY_COLLECTION_TYPE}'
          AND NOT ST_IsEmpty({part})
          AND ST_GeometryType({part}) IN ({type_list})
        """
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _count_derived_in_split(cur: Any, polygons_qualified: str) -> int:
    cur.execute(
        f"""
        SELECT count(*) FROM {polygons_qualified}
        WHERE derived_from_id IS NOT NULL
        """
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _count_skipped(cur: Any, source_qualified: str) -> int:
    valid = _valid_geom_expr()
    valid_src = _valid_geom_expr_for("src.geom")
    type_list = ", ".join(f"'{t}'" for t in _ALL_ROUTED_TYPES)
    routed_types = f"{type_list}, '{_GEOMETRY_COLLECTION_TYPE}'"
    part = _valid_geom_expr_for("flat.part_geom")
    lateral = _collection_parts_lateral_sql("src.geom")
    cur.execute(
        f"""
        SELECT count(*)
        FROM {source_qualified} AS src
        WHERE src.geom IS NOT NULL
          AND (
              ST_IsEmpty({valid_src})
              OR (
                  ST_GeometryType({valid_src}) NOT IN ({routed_types})
              )
              OR (
                  ST_GeometryType({valid_src}) = '{_GEOMETRY_COLLECTION_TYPE}'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ({lateral}) AS flat
                      WHERE NOT ST_IsEmpty({part})
                        AND ST_GeometryType({part}) IN ({type_list})
                  )
              )
          )
        """
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def rebuild_geom_split(cur: Any, qualified_source: str) -> Optional[GeomSplitResult]:
    """
    Rebuild *_points, *_lines, *_polygons from items_* after derive_polygons_from_lines.

    Only routes geometries (ST_MakeValid on insert). Line-to-polygon is not repeated here.
    """
    table = _table_name(qualified_source)
    if table not in SPLIT_SOURCE_TABLES:
        return None

    from collector.data_mos_line_to_polygon import attribute_columns

    points_q, lines_q, polygons_q = qualified_split_names(qualified_source)
    source_schema, _ = qualified_source.split(".", 1)

    _ensure_split_table(cur, qualified_source, points_q, with_derived_from_id=False)
    _ensure_split_table(cur, qualified_source, lines_q, with_derived_from_id=False)
    _ensure_split_table(cur, qualified_source, polygons_q, with_derived_from_id=True)

    attr_cols, _ = attribute_columns(cur, source_schema, table)

    for target in (points_q, lines_q, polygons_q):
        cur.execute(f"TRUNCATE TABLE {target} RESTART IDENTITY")

    points = _insert_routed(
        cur, qualified_source, points_q, attr_cols, _POINT_TYPES,
    )
    points += _insert_routed_from_collection(
        cur, qualified_source, points_q, attr_cols, _POINT_TYPES,
    )
    lines = _insert_routed(
        cur, qualified_source, lines_q, attr_cols, _LINE_TYPES,
    )
    lines += _insert_routed_from_collection(
        cur, qualified_source, lines_q, attr_cols, _LINE_TYPES,
    )
    polygons = _insert_routed(
        cur,
        qualified_source,
        polygons_q,
        attr_cols,
        _POLYGON_TYPES,
        with_derived_from_id=True,
    )
    polygons += _insert_routed_from_collection(
        cur,
        qualified_source,
        polygons_q,
        attr_cols,
        _POLYGON_TYPES,
        with_derived_from_id=True,
    )
    derived_polygons = _count_derived_in_split(cur, polygons_q)
    collection_rows = _count_collection_rows(cur, qualified_source)
    collection_parts = _count_collection_parts_routed(cur, qualified_source)
    skipped = _count_skipped(cur, qualified_source)

    if skipped:
        logger.warning(
            "Geom split %s: skipped %s rows (invalid, empty, or no routable parts)",
            qualified_source,
            skipped,
        )

    logger.info(
        "Geom split %s -> points=%s lines=%s polygons=%s (derived=%s) "
        "collections=%s rows / %s parts routed, skipped=%s",
        qualified_source,
        points,
        lines,
        polygons,
        derived_polygons,
        collection_rows,
        collection_parts,
        skipped,
    )

    return GeomSplitResult(
        points=points,
        lines=lines,
        polygons=polygons,
        derived_polygons=derived_polygons,
        skipped=skipped,
        collection_rows=collection_rows,
        collection_parts=collection_parts,
    )
