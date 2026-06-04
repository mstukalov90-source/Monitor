"""Dynamic PostgreSQL schema for genplan JSON imports."""

from __future__ import annotations

from typing import Any, Optional

from psycopg2.extensions import cursor as Cursor

from collector.data_mos_schema import (
    _scalar_value,
    ensure_columns,
    infer_column_type,
    prepare_value,
    to_column_name,
)
from collector.genplan_detect import GenplanKind, TABLE_BY_KIND

_RESERVED_BASE = frozenset({"id", "geom", "loaded_at", "file_name", "uuid"})
_EXCLUDE_BY_KIND: dict[GenplanKind, frozenset[str]] = {
    "order": frozenset({"wkt"}),
    "photo_meta": frozenset(),
    "upload": frozenset(),
    "uuid_area": frozenset({"uuids"}),
}


def qualified_table(kind: GenplanKind) -> str:
    table = TABLE_BY_KIND[kind]
    if table == "order":
        return 'genplan."order"'
    return f"genplan.{table}"


def extract_genplan_properties(
    payload: dict,
    *,
    kind: GenplanKind,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Map JSON keys to column names; skip reserved and geometry source keys."""
    exclude_keys = _EXCLUDE_BY_KIND[kind]
    props: dict[str, Any] = {}

    for key, raw in payload.items():
        if key in exclude_keys:
            continue
        col = to_column_name(str(key))
        if col is None or col in _RESERVED_BASE:
            continue
        props[col] = _scalar_value(raw)

    if extra:
        for key, val in extra.items():
            if key == "uuid":
                props["uuid"] = _scalar_value(val)
                continue
            col = to_column_name(str(key))
            if col is None or col in _RESERVED_BASE:
                continue
            props[col] = _scalar_value(val)

    return props


def collect_schema_from_properties(props: dict[str, Any]) -> dict[str, str]:
    """Build column name -> PostgreSQL type from one property dict."""
    schema: dict[str, str] = {}
    for col, val in props.items():
        schema[col] = infer_column_type([val])
    return schema


def merge_schema(existing: dict[str, str], props: dict[str, Any]) -> dict[str, str]:
    """Merge new property samples into schema map."""
    merged = dict(existing)
    for col, val in props.items():
        if col not in merged:
            merged[col] = infer_column_type([val])
        else:
            merged[col] = infer_column_type(
                [_placeholder_for_type(merged[col]), val]
            )
    return merged


def _placeholder_for_type(pg_type: str) -> Any:
    if pg_type == "JSONB":
        return {}
    if pg_type == "BOOLEAN":
        return False
    if pg_type == "BIGINT":
        return 0
    if pg_type == "DOUBLE PRECISION":
        return 0.0
    return ""


def ensure_genplan_table(cur: Cursor, kind: GenplanKind) -> None:
    """Create minimal table shell if it does not exist."""
    q = qualified_table(kind)
    if kind == "order":
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {q} (
                id          BIGSERIAL PRIMARY KEY,
                file_name   TEXT NOT NULL,
                geom        GEOMETRY(Geometry, 4326),
                loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            f'CREATE INDEX IF NOT EXISTS idx_genplan_order_geom ON {q} USING GIST (geom)'
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_order_file_name ON {q} (file_name)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_order_loaded_at ON {q} (loaded_at DESC)"
        )
    elif kind == "photo_meta":
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {q} (
                id          BIGSERIAL PRIMARY KEY,
                file_name   TEXT NOT NULL,
                geom        GEOMETRY(Point, 4326),
                loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_photo_meta_geom ON {q} USING GIST (geom)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_photo_meta_file_name ON {q} (file_name)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_photo_meta_loaded_at ON {q} (loaded_at DESC)"
        )
    elif kind == "upload":
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {q} (
                id          BIGSERIAL PRIMARY KEY,
                file_name   TEXT NOT NULL,
                loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_upload_file_name ON {q} (file_name)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_upload_loaded_at ON {q} (loaded_at DESC)"
        )
    else:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {q} (
                id          BIGSERIAL PRIMARY KEY,
                file_name   TEXT NOT NULL,
                uuid        TEXT,
                loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_uuid_area_uuid ON {q} (uuid)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_uuid_area_file_name ON {q} (file_name)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_genplan_uuid_area_loaded_at ON {q} (loaded_at DESC)"
        )


def insert_genplan_row(
    cur: Cursor,
    kind: GenplanKind,
    schema: dict[str, str],
    file_name: str,
    props: dict[str, Any],
    *,
    wkt: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> None:
    """Insert one row with dynamic property columns and optional geometry."""
    q = qualified_table(kind)
    dyn_cols = sorted(schema.keys())
    values: dict[str, Any] = {
        "file_name": file_name,
        **{col: prepare_value(props.get(col), schema[col]) for col in dyn_cols},
    }

    col_parts = ['"file_name"'] + [f'"{c}"' for c in dyn_cols]
    ph_parts = ["%(file_name)s"] + [f"%({c})s" for c in dyn_cols]

    if kind == "order" and wkt:
        col_parts.append("geom")
        ph_parts.append("ST_SetSRID(ST_GeomFromText(%(wkt)s), 4326)")
        values["wkt"] = wkt
    elif kind == "photo_meta" and lat is not None and lng is not None:
        col_parts.append("geom")
        ph_parts.append("ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)")
        values["lat"] = lat
        values["lng"] = lng

    col_list = ", ".join(col_parts)
    placeholders = ", ".join(ph_parts)
    cur.execute(
        f"INSERT INTO {q} ({col_list}) VALUES ({placeholders})",
        values,
    )
