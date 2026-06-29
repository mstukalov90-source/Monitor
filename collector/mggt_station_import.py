"""Import KGS/SPS GeoPackage files into mggt_station tables (WGS84)."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import pandas as pd
from psycopg2.extensions import cursor as Cursor

from collector.db import execute_sql_file, local_connection

logger = logging.getLogger(__name__)

MSK77_PROJ4 = (
    "+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 +x_0=0 +y_0=0 "
    "+ellps=bessel +towgs84=458.475,0.244,603.087,-3.98169,-0.43293,4.43381,1.713 "
    "+units=m +no_defs"
)

SPS_LAYER = "OGH_GPKG"
_POINT_TYPES = frozenset({"Point", "MultiPoint"})
_LINE_TYPES = frozenset({"LineString", "MultiLineString", "LinearRing"})

KGS_TEXT_COLUMNS = ("text", "name", "layer", "ocolor", "olinetype", "angle", "weight", "Number", "color")
SPS_TEXT_COLUMNS = (
    "text",
    "name",
    "layer",
    "ocolor",
    "olinetype",
    "angle",
    "weight",
    "Number",
    "geometry_fme_type",
    "color",
    "svg_name",
    "object_type",
    "new_cell_name",
    "utf8_cell_name",
    "igds_original_justification",
)
SPS_INT_COLUMNS = (
    "font",
    "text_group",
    "igds_style",
    "igds_level",
    "igds_justification",
)

MIGRATION_SQL = Path(__file__).resolve().parents[1] / "sql" / "26_mggt_station_wgs84_attrs.sql"


@dataclass(frozen=True)
class TableLoadResult:
    table: str
    loaded: int


@dataclass(frozen=True)
class ImportResult:
    tables: tuple[TableLoadResult, ...]
    skipped_no_geometry: int


def _is_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_text(value: Any) -> str | None:
    if _is_null(value):
        return None
    return str(value)


def _as_int(value: Any) -> int | None:
    if _is_null(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_values(row: pd.Series, text_columns: Iterable[str], int_columns: Iterable[str] = ()) -> dict[str, Any]:
    values: dict[str, Any] = {"BasePolyUsage": True}
    for col in text_columns:
        values[col] = _as_text(row.get(col))
    for col in int_columns:
        values[col] = _as_int(row.get(col))
    return values


def load_gpkg(path: Path, layer: str | None = None) -> gpd.GeoDataFrame:
    """Read GPKG, drop empty geometries, assign MSK-77 and transform to WGS84."""
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if gdf.empty:
        return gdf.set_crs("EPSG:4326")
    gdf = gdf.set_crs(MSK77_PROJ4, allow_override=True)
    return gdf.to_crs("EPSG:4326")


def split_by_geometry_type(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if gdf.empty:
        empty = gdf.copy()
        return empty, empty

    geom_types = gdf.geometry.geom_type
    points = gdf[geom_types.isin(_POINT_TYPES)].copy()
    lines = gdf[geom_types.isin(_LINE_TYPES)].copy()
    return points, lines


def ensure_schema(conn) -> None:
    """Apply WGS84/attribute migration if tables were created with the old schema."""
    if MIGRATION_SQL.exists():
        execute_sql_file(conn, MIGRATION_SQL)


def truncate_tables(cur: Cursor) -> None:
    cur.execute(
        """
        TRUNCATE TABLE
            mggt_station.kgs_lines,
            mggt_station.kgs_point,
            mggt_station.sps_lines,
            mggt_station.sps_point
        RESTART IDENTITY
        """
    )


def _insert_kgs_rows(cur: Cursor, table: str, gdf: gpd.GeoDataFrame) -> int:
    if gdf.empty:
        return 0

    count = 0
    for _, row in gdf.iterrows():
        values = _row_values(row, KGS_TEXT_COLUMNS)
        geom_json = json.dumps(row.geometry.__geo_interface__)
        cur.execute(
            f"""
            INSERT INTO mggt_station.{table} (
                "text", "name", layer, ocolor, olinetype, angle, weight,
                "Number", color, "BasePolyUsage", "Geometry"
            ) VALUES (
                %(text)s, %(name)s, %(layer)s, %(ocolor)s, %(olinetype)s,
                %(angle)s, %(weight)s, %(Number)s, %(color)s, %(BasePolyUsage)s,
                ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)
            )
            """,
            {**values, "geom": geom_json},
        )
        count += 1
    return count


def _insert_sps_rows(cur: Cursor, table: str, gdf: gpd.GeoDataFrame) -> int:
    if gdf.empty:
        return 0

    count = 0
    for _, row in gdf.iterrows():
        values = _row_values(row, SPS_TEXT_COLUMNS, SPS_INT_COLUMNS)
        geom_json = json.dumps(row.geometry.__geo_interface__)
        cur.execute(
            f"""
            INSERT INTO mggt_station.{table} (
                "text", "name", layer, ocolor, olinetype, angle, weight,
                "Number", geometry_fme_type, color, svg_name, object_type,
                new_cell_name, utf8_cell_name, font, text_group, igds_style,
                igds_level, igds_justification, igds_original_justification,
                "BasePolyUsage", "Geometry"
            ) VALUES (
                %(text)s, %(name)s, %(layer)s, %(ocolor)s, %(olinetype)s,
                %(angle)s, %(weight)s, %(Number)s, %(geometry_fme_type)s,
                %(color)s, %(svg_name)s, %(object_type)s, %(new_cell_name)s,
                %(utf8_cell_name)s, %(font)s, %(text_group)s, %(igds_style)s,
                %(igds_level)s, %(igds_justification)s,
                %(igds_original_justification)s, %(BasePolyUsage)s,
                ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)
            )
            """,
            {**values, "geom": geom_json},
        )
        count += 1
    return count


def import_gpkg_files(
    kgs_path: Path,
    sps_path: Path,
    *,
    truncate: bool = True,
    apply_migration: bool = True,
) -> ImportResult:
    """Load КГС and СПС GeoPackages into mggt_station tables."""
    if not kgs_path.exists():
        raise FileNotFoundError(f"KGS GeoPackage not found: {kgs_path}")
    if not sps_path.exists():
        raise FileNotFoundError(f"SPS GeoPackage not found: {sps_path}")

    kgs_raw = gpd.read_file(kgs_path)
    sps_raw = gpd.read_file(sps_path, layer=SPS_LAYER)
    skipped_no_geometry = int(
        len(kgs_raw) - len(kgs_raw[kgs_raw.geometry.notna() & ~kgs_raw.geometry.is_empty])
        + len(sps_raw) - len(sps_raw[sps_raw.geometry.notna() & ~sps_raw.geometry.is_empty])
    )

    kgs_gdf = load_gpkg(kgs_path)
    sps_gdf = load_gpkg(sps_path, layer=SPS_LAYER)

    kgs_points, kgs_lines = split_by_geometry_type(kgs_gdf)
    sps_points, sps_lines = split_by_geometry_type(sps_gdf)

    results: list[TableLoadResult] = []

    with local_connection() as conn:
        if apply_migration:
            ensure_schema(conn)

        with conn.cursor() as cur:
            if truncate:
                truncate_tables(cur)

            results.append(
                TableLoadResult("kgs_lines", _insert_kgs_rows(cur, "kgs_lines", kgs_lines))
            )
            results.append(
                TableLoadResult("kgs_point", _insert_kgs_rows(cur, "kgs_point", kgs_points))
            )
            results.append(
                TableLoadResult("sps_lines", _insert_sps_rows(cur, "sps_lines", sps_lines))
            )
            results.append(
                TableLoadResult("sps_point", _insert_sps_rows(cur, "sps_point", sps_points))
            )

    for item in results:
        logger.info("Loaded %s rows into mggt_station.%s", item.loaded, item.table)

    return ImportResult(tables=tuple(results), skipped_no_geometry=skipped_no_geometry)
