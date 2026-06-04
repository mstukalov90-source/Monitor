"""Load mggt_dgn/mggt_dgn.geojson into odh_export.ogh-disruption (upsert by source_json + lon/lat)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import geopandas as gpd

from collector.config import OGH_DISRUPTION_GEOJSON
from collector.data_mos_schema import extract_feature_properties, prepare_value
from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

JOB_NAME = "ogh_disruption"
QUALIFIED_TABLE = 'odh_export."ogh-disruption"'
_COORD_PRECISION = 9


@dataclass(frozen=True)
class PointCoords:
    lon: float
    lat: float


@dataclass(frozen=True)
class LoadResult:
    loaded: int
    skipped: int


def _load_geojson() -> gpd.GeoDataFrame:
    if not OGH_DISRUPTION_GEOJSON.exists():
        raise FileNotFoundError(f"GeoJSON not found: {OGH_DISRUPTION_GEOJSON}")

    gdf = gpd.read_file(OGH_DISRUPTION_GEOJSON)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def _point_coords(row) -> PointCoords | None:
    geom = row.geometry
    if geom is None or geom.is_empty:
        return None
    geom_type = getattr(geom, "geom_type", None)
    if geom_type != "Point":
        return None
    return PointCoords(
        lon=round(float(geom.x), _COORD_PRECISION),
        lat=round(float(geom.y), _COORD_PRECISION),
    )


def _upsert_feature(
    cur,
    label_text: str | None,
    filter_pass: str | None,
    source_json: str,
    coords: PointCoords,
    geom_json: str,
) -> None:
    cur.execute(
        f"""
        INSERT INTO {QUALIFIED_TABLE}
            (label_text, filter_pass, source_json, lon, lat, geometry)
        VALUES (
            %(label_text)s,
            %(filter_pass)s,
            %(source_json)s,
            %(lon)s,
            %(lat)s,
            ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)
        )
        ON CONFLICT (source_json, lon, lat) DO UPDATE SET
            label_text = EXCLUDED.label_text,
            filter_pass = EXCLUDED.filter_pass,
            geometry = EXCLUDED.geometry,
            loaded_at = NOW()
        """,
        {
            "label_text": label_text,
            "filter_pass": filter_pass,
            "source_json": source_json,
            "lon": coords.lon,
            "lat": coords.lat,
            "geom": geom_json,
        },
    )


def load_geojson_to_db() -> LoadResult:
    gdf = _load_geojson()
    loaded = 0
    skipped = 0

    with local_connection() as conn:
        with conn.cursor() as cur:
            for _, row in gdf.iterrows():
                props = extract_feature_properties(row)
                source_json = props.get("source_json")
                if source_json is None or str(source_json).strip() == "":
                    skipped += 1
                    continue

                coords = _point_coords(row)
                if coords is None:
                    skipped += 1
                    continue

                geom_json = json.dumps(row.geometry.__geo_interface__)
                label_text = prepare_value(props.get("label_text"), "TEXT")
                filter_pass = prepare_value(props.get("filter_pass"), "TEXT")
                source_json_val = str(source_json).strip()

                _upsert_feature(
                    cur,
                    label_text,
                    filter_pass,
                    source_json_val,
                    coords,
                    geom_json,
                )
                loaded += 1

    return LoadResult(loaded=loaded, skipped=skipped)


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"Source file: {OGH_DISRUPTION_GEOJSON.name}",
        )

    if not OGH_DISRUPTION_GEOJSON.exists():
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                f"No file to process: {OGH_DISRUPTION_GEOJSON.name}",
                rows_affected=0,
                run_id=run_id,
            )
        logger.info(
            "%s: %s not found, skipping",
            JOB_NAME,
            OGH_DISRUPTION_GEOJSON,
        )
        return

    try:
        result = load_geojson_to_db()
        OGH_DISRUPTION_GEOJSON.unlink()
        logger.info("Deleted source file %s", OGH_DISRUPTION_GEOJSON)

        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                (
                    f"Upserted {result.loaded} feature(s) into {QUALIFIED_TABLE}; "
                    f"skipped {result.skipped} feature(s) without source_json or point coordinates"
                ),
                rows_affected=result.loaded,
                run_id=run_id,
            )
        logger.info(
            "%s finished: %s upserted, %s skipped",
            JOB_NAME,
            result.loaded,
            result.skipped,
        )
    except Exception as exc:
        logger.exception("%s failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
