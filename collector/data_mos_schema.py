"""Dynamic PostgreSQL schema from data.mos.ru GeoJSON properties."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import geopandas as gpd
import pandas as pd
from psycopg2.extensions import cursor as Cursor
from psycopg2.extras import Json

from collector.flatten import _parse_maybe_dict

_RESERVED_COLUMNS = frozenset({"id", "geom", "loaded_at"})
_GEOMETRY_KEYS = frozenset({
    "geometry", "geom", "geodata", "geodata_center",
    "coordinates", "wkt", "geo_data", "geocenter",
})
_COLUMN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_COLUMN_LEN = 63


def _scalar_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, dict, str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    # Multi-element numpy/pandas values (e.g. coordinate arrays in Cells)
    shape = getattr(value, "shape", None)
    if shape is not None and shape != ():
        if hasattr(value, "tolist"):
            return value.tolist()
        return str(value)
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            if hasattr(value, "tolist"):
                return value.tolist()
            return str(value)
    if pd.api.types.is_scalar(value):
        try:
            if pd.isna(value):
                return None
        except (ValueError, TypeError):
            pass
    elif hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


def to_column_name(key: str) -> Optional[str]:
    """Convert JSON key to a safe PostgreSQL column name (snake_case)."""
    if not key or not isinstance(key, str):
        return None
    key = key.strip()
    if not key:
        return None

    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", normalized)

    parts: list[str] = []
    for part in re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").split("_"):
        if not part:
            continue
        parts.append(part.lower())

    if not parts:
        return None

    name = "_".join(parts)
    if name[0].isdigit():
        name = f"field_{name}"
    name = name[:_MAX_COLUMN_LEN]

    if name in _RESERVED_COLUMNS or not _COLUMN_NAME_RE.match(name):
        return None
    return name


def extract_feature_properties(row: pd.Series) -> dict[str, Any]:
    """Merge flat GeoJSON properties and nested attributes into one dict."""
    props: dict[str, Any] = {}

    attrs_raw = row.get("attributes") if "attributes" in row.index else None
    parsed_attrs = _parse_maybe_dict(_scalar_value(attrs_raw))

    for key, raw in row.items():
        if key in ("geometry", "attributes"):
            continue
        col = to_column_name(str(key))
        if col is None:
            continue
        val = _scalar_value(raw)
        if col in _GEOMETRY_KEYS:
            continue
        props[col] = val

    if parsed_attrs:
        for key, raw in parsed_attrs.items():
            col = to_column_name(str(key))
            if col is None:
                continue
            val = _scalar_value(raw)
            if col in _GEOMETRY_KEYS:
                continue
            props[col] = val

    return props


def infer_column_type(values: list[Any]) -> str:
    """Infer PostgreSQL type from a sample of non-null values."""
    has_float = False
    has_int = False
    has_bool = False
    has_json = False
    has_other = False

    for val in values:
        if val is None:
            continue
        if isinstance(val, bool):
            has_bool = True
        elif isinstance(val, int) and not isinstance(val, bool):
            has_int = True
        elif isinstance(val, float):
            has_float = True
        elif isinstance(val, (list, dict)):
            has_json = True
        else:
            has_other = True

    if has_json:
        return "JSONB"
    if has_float or (has_int and has_other):
        return "DOUBLE PRECISION"
    if has_int and not has_other and not has_bool:
        return "BIGINT"
    if has_bool and not has_int and not has_float and not has_other:
        return "BOOLEAN"
    return "TEXT"


def collect_schema(gdf: gpd.GeoDataFrame) -> dict[str, str]:
    """Build column name -> PostgreSQL type map from all features."""
    samples: dict[str, list[Any]] = {}

    for _, row in gdf.iterrows():
        props = extract_feature_properties(row)
        for col, val in props.items():
            samples.setdefault(col, []).append(val)

    schema: dict[str, str] = {}
    for col, vals in samples.items():
        schema[col] = infer_column_type(vals)
    return schema


def ensure_base_table(cur: Cursor, qualified_table: str) -> None:
    """Create minimal table shell if it does not exist."""
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table} (
            id         BIGSERIAL PRIMARY KEY,
            geom       GEOMETRY(Geometry, 4326),
            loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    suffix = qualified_table.split(".")[-1]
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{suffix}_geom "
        f"ON {qualified_table} USING GIST (geom)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{suffix}_loaded_at "
        f"ON {qualified_table} (loaded_at DESC)"
    )


def ensure_columns(cur: Cursor, qualified_table: str, schema: dict[str, str]) -> None:
    """Add dynamic columns that are not yet present."""
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        tuple(qualified_table.split(".", 1)),
    )
    existing = {r[0] for r in cur.fetchall()}

    for col, pg_type in sorted(schema.items()):
        if col in existing:
            continue
        cur.execute(
            f"ALTER TABLE {qualified_table} ADD COLUMN IF NOT EXISTS "
            f'"{col}" {pg_type}'
        )


def prepare_value(val: Any, pg_type: str) -> Any:
    if val is None:
        return None
    if pg_type == "JSONB":
        if isinstance(val, (list, dict)):
            return Json(val)
        if isinstance(val, str):
            parsed = _parse_maybe_dict(val)
            return Json(parsed if parsed is not None else val)
        return Json(val)
    if pg_type == "BOOLEAN":
        return bool(val)
    if pg_type == "BIGINT":
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
    if pg_type == "DOUBLE PRECISION":
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    return str(val) if not isinstance(val, (str, int, float, bool)) else val


def insert_feature(
    cur: Cursor,
    qualified_table: str,
    schema: dict[str, str],
    props: dict[str, Any],
    geom_json: Optional[str],
) -> None:
    """Insert one row with dynamic property columns."""
    cols = sorted(schema.keys())
    values = {col: prepare_value(props.get(col), schema[col]) for col in cols}

    if geom_json:
        col_list = ", ".join(f'"{c}"' for c in cols) + ", geom"
        placeholders = ", ".join(f"%({c})s" for c in cols) + ", ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)"
        cur.execute(
            f"INSERT INTO {qualified_table} ({col_list}) VALUES ({placeholders})",
            {**values, "geom": geom_json},
        )
    elif cols:
        col_list = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f"%({c})s" for c in cols)
        cur.execute(
            f"INSERT INTO {qualified_table} ({col_list}) VALUES ({placeholders})",
            values,
        )
    else:
        cur.execute(f"INSERT INTO {qualified_table} DEFAULT VALUES")
