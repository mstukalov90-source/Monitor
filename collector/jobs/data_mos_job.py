"""03:00 job — export data.mos.ru and load into data_mos.items."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Any

import geopandas as gpd
from psycopg2.extras import Json

from collector.config import (
    DATA_MOS_EXPORT_SCRIPT,
    DATA_MOS_GEOJSON,
    DATA_MOS_GPKG,
    PROJECT_DIR,
)
from collector.db import local_connection, log_job_run
from collector.flatten import flatten_data_mos_properties

logger = logging.getLogger(__name__)

JOB_NAME = "data_mos"

DATA_MOS_COLUMNS = [
    "dataset_id", "row_id", "version_number", "release_number",
    "order_number", "order_date", "customer_construction", "customer_construction_inn",
    "general_contractor", "general_contractor_inn",
    "work_type", "order_work", "earthwork_objectives",
    "objectives_temp_fences", "objectives_temp_objects",
    "address_nearby_building", "adm_area", "district", "work_place_description",
    "work_start_date", "work_end_date", "global_id",
]

JSONB_COLUMNS = {
    "work_type", "order_work", "earthwork_objectives",
    "objectives_temp_fences", "objectives_temp_objects",
}


def _clean_row_props(row) -> dict[str, Any]:
    props = {k: v for k, v in row.items() if k != "geometry"}
    clean: dict[str, Any] = {}
    for k, v in props.items():
        if hasattr(v, "item"):
            clean[k] = v.item()
        elif v is None or isinstance(v, (str, int, float, bool, list, dict)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


def _prepare_insert_values(flat: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for col in DATA_MOS_COLUMNS:
        val = flat.get(col)
        if col in JSONB_COLUMNS and val is not None:
            values[col] = Json(val)
        else:
            values[col] = val
    return values


def run_export() -> None:
    """Run data_mos_export.py in project directory."""
    if not DATA_MOS_EXPORT_SCRIPT.exists():
        raise FileNotFoundError(f"Export script not found: {DATA_MOS_EXPORT_SCRIPT}")

    env = os.environ.copy()
    api_key = os.getenv("DATA_MOS_API_KEY")
    if api_key:
        env["DATA_MOS_API_KEY"] = api_key

    logger.info("Running %s", DATA_MOS_EXPORT_SCRIPT)
    result = subprocess.run(
        [sys.executable, str(DATA_MOS_EXPORT_SCRIPT)],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0:
        logger.error("stdout: %s", result.stdout[-2000:] if result.stdout else "")
        logger.error("stderr: %s", result.stderr[-2000:] if result.stderr else "")
        raise RuntimeError(f"data_mos_export.py failed with code {result.returncode}")

    logger.info("Export completed successfully")


def load_geojson_to_db() -> int:
    """Load Data_mos_export.geojson into data_mos.items (full replace)."""
    if not DATA_MOS_GEOJSON.exists():
        raise FileNotFoundError(f"GeoJSON not found: {DATA_MOS_GEOJSON}")

    gdf = gpd.read_file(DATA_MOS_GEOJSON)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    col_list = ", ".join(DATA_MOS_COLUMNS)
    placeholders = ", ".join(f"%({c})s" for c in DATA_MOS_COLUMNS)

    with local_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE data_mos.items RESTART IDENTITY")
            count = 0
            for _, row in gdf.iterrows():
                flat = flatten_data_mos_properties(_clean_row_props(row))
                values = _prepare_insert_values(flat)
                geom_json = None
                if row.geometry is not None and not row.geometry.is_empty:
                    geom_json = json.dumps(row.geometry.__geo_interface__)

                if geom_json:
                    cur.execute(
                        f"""
                        INSERT INTO data_mos.items ({col_list}, geom)
                        VALUES ({placeholders}, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326))
                        """,
                        {**values, "geom": geom_json},
                    )
                else:
                    cur.execute(
                        f"INSERT INTO data_mos.items ({col_list}) VALUES ({placeholders})",
                        values,
                    )
                count += 1

    return count


def cleanup_export_files() -> None:
    for path in (DATA_MOS_GEOJSON, DATA_MOS_GPKG):
        if path.exists():
            path.unlink()
            logger.info("Deleted %s", path)


def run() -> None:
    """Execute full data_mos pipeline."""
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started data_mos job")

    try:
        run_export()
        count = load_geojson_to_db()
        cleanup_export_files()
        with local_connection() as conn:
            log_job_run(
                conn, JOB_NAME, "success",
                f"Loaded {count} features",
                rows_affected=count,
                run_id=run_id,
            )
        logger.info("data_mos job finished: %s rows", count)
    except Exception as exc:
        logger.exception("data_mos job failed")
        with local_connection() as conn:
            log_job_run(
                conn, JOB_NAME, "failed", str(exc),
                run_id=run_id,
            )
        raise
