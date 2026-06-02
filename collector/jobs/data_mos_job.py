"""data.mos.ru export jobs — one pipeline per service ID."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass

import geopandas as gpd

from collector.config import (
    DATA_MOS_EXPORTS,
    DataMosExportConfig,
    PROJECT_DIR,
)
from collector.data_mos_schema import (
    collect_schema,
    ensure_base_table,
    ensure_columns,
    extract_feature_properties,
    insert_feature,
)
from collector.data_mos_line_to_polygon import derive_polygons_from_lines
from collector.data_mos_purge import purge_archived
from collector.db import local_connection, log_job_run

logger = logging.getLogger(__name__)

_TABLE_NAME_RE = re.compile(r"^items_\d+$")


@dataclass(frozen=True)
class LoadResult:
    loaded: int
    purged: int
    derived_polygons: int = 0


def _validate_table_name(table: str) -> str:
    if not _TABLE_NAME_RE.match(table):
        raise ValueError(f"Invalid data_mos table name: {table}")
    return table


def run_export(config: DataMosExportConfig) -> None:
    """Run data_mos_export_<id>.py in project directory."""
    if not config.script.exists():
        raise FileNotFoundError(f"Export script not found: {config.script}")

    env = os.environ.copy()
    api_key = os.getenv("DATA_MOS_API_KEY")
    if api_key:
        env["DATA_MOS_API_KEY"] = api_key

    logger.info("Running %s", config.script)
    result = subprocess.run(
        [sys.executable, str(config.script)],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0:
        logger.error("stdout: %s", result.stdout[-2000:] if result.stdout else "")
        logger.error("stderr: %s", result.stderr[-2000:] if result.stderr else "")
        raise RuntimeError(
            f"{config.script.name} failed with code {result.returncode}"
        )

    logger.info("Export completed successfully for service %s", config.service_id)


def load_geojson_to_db(config: DataMosExportConfig) -> LoadResult:
    """Load GeoJSON into data_mos.<table> with dynamic columns from JSON keys."""
    table = _validate_table_name(config.table)
    qualified = f"data_mos.{table}"

    if not config.geojson.exists():
        raise FileNotFoundError(f"GeoJSON not found: {config.geojson}")

    gdf = gpd.read_file(config.geojson)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    schema = collect_schema(gdf)
    logger.info(
        "Service %s: %s dynamic columns for %s",
        config.service_id, len(schema), qualified,
    )

    with local_connection() as conn:
        with conn.cursor() as cur:
            ensure_base_table(cur, qualified)
            ensure_columns(cur, qualified, schema)
            cur.execute(f"TRUNCATE TABLE {qualified} RESTART IDENTITY")
            count = 0
            for _, row in gdf.iterrows():
                props = extract_feature_properties(row)
                geom_json = None
                if row.geometry is not None and not row.geometry.is_empty:
                    geom_json = json.dumps(row.geometry.__geo_interface__)
                insert_feature(cur, qualified, schema, props, geom_json)
                count += 1

            purged = 0
            if config.purge_rule is not None:
                purged = purge_archived(cur, qualified, config.purge_rule)

            derived = derive_polygons_from_lines(cur, qualified)

    return LoadResult(loaded=count, purged=purged, derived_polygons=derived)


def cleanup_export_files(config: DataMosExportConfig) -> None:
    for path in (config.geojson, config.gpkg):
        if path.exists():
            path.unlink()
            logger.info("Deleted %s", path)


def run_for(config: DataMosExportConfig) -> None:
    """Execute full export + load pipeline for one service."""
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(
            conn, config.job_name, "running",
            f"Started data_mos job (service {config.service_id})",
        )

    try:
        run_export(config)
        result = load_geojson_to_db(config)
        cleanup_export_files(config)
        with local_connection() as conn:
            log_job_run(
                conn, config.job_name, "success",
                (
                    f"Loaded {result.loaded} features, purged {result.purged} archived rows, "
                    f"derived {result.derived_polygons} polygons"
                ),
                rows_affected=result.loaded,
                run_id=run_id,
            )
        logger.info(
            "%s finished: %s rows loaded, %s archived rows purged, "
            "%s derived polygons in data_mos.%s",
            config.job_name, result.loaded, result.purged,
            result.derived_polygons, config.table,
        )
    except Exception as exc:
        logger.exception("%s failed", config.job_name)
        with local_connection() as conn:
            log_job_run(
                conn, config.job_name, "failed", str(exc),
                run_id=run_id,
            )
        raise


def run_all_data_mos() -> None:
    """Run all data.mos.ru export pipelines sequentially (see DATA_MOS_EXPORTS)."""
    for config in DATA_MOS_EXPORTS:
        run_for(config)
