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
    upsert_feature,
)
from collector.crm_task_sync import sync_crm_tasks_after_etl
from collector.data_mos_geom_split import GeomSplitResult, rebuild_geom_split
from collector.data_mos_line_to_polygon import derive_polygons_from_lines
from collector.data_mos_purge import purge_archived
from collector.data_mos_tasked import ensure_tasked_column
from collector.db import local_connection, log_job_run
from collector.jobs import ogh_disruption_job

logger = logging.getLogger(__name__)

_TABLE_NAME_RE = re.compile(r"^items_\d+$")


@dataclass(frozen=True)
class LoadResult:
    loaded: int
    purged: int
    derived_polygons: int = 0
    split: GeomSplitResult | None = None


def _format_load_success_message(result: LoadResult) -> str:
    parts = [
        f"Loaded {result.loaded} features",
        f"purged {result.purged} archived rows",
    ]
    if result.derived_polygons:
        parts.append(f"derived {result.derived_polygons} polygons in items_*")
    if result.split:
        parts.append(
            f"geom split: {result.split.points} points, {result.split.lines} lines, "
            f"{result.split.polygons} polygons ({result.split.skipped} skipped)"
        )
    return ", ".join(parts)


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


def _count_split_task_keys(cur, table: str) -> int:
    total = 0
    for suffix in ("_points", "_lines", "_polygons"):
        qualified = f"data_mos.{table}{suffix}"
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'data_mos' AND table_name = %s
            """,
            (f"{table}{suffix}",),
        )
        if cur.fetchone() is None:
            continue
        cur.execute(f"SELECT COUNT(*) FROM {qualified} WHERE task_key IS NOT NULL")
        row = cur.fetchone()
        total += int(row[0]) if row else 0
    return total


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
            ensure_tasked_column(cur, qualified)
            linked_before = _count_split_task_keys(cur, table)
            incoming_ids: set[int] = set()
            count = 0
            for _, row in gdf.iterrows():
                props = extract_feature_properties(row)
                geom_json = None
                if row.geometry is not None and not row.geometry.is_empty:
                    geom_json = json.dumps(row.geometry.__geo_interface__)
                row_id = upsert_feature(cur, qualified, schema, props, geom_json)
                if row_id:
                    incoming_ids.add(row_id)
                count += 1

            if incoming_ids:
                cur.execute(
                    f"DELETE FROM {qualified} "
                    f"WHERE id <> ALL(%s) AND tasked IS NOT TRUE",
                    (list(incoming_ids),),
                )
            purged = 0
            if config.purge_rule is not None:
                purged = purge_archived(cur, qualified, config.purge_rule)

            derived = derive_polygons_from_lines(cur, qualified)
            split = rebuild_geom_split(cur, qualified)
            sync_crm_tasks_after_etl(cur, table)

            linked_after = _count_split_task_keys(cur, table)
            if linked_after < linked_before:
                logger.error(
                    "task_key count dropped for %s: %s -> %s",
                    table,
                    linked_before,
                    linked_after,
                )
                raise RuntimeError(
                    f"task_key preservation failed for {table}: "
                    f"{linked_before} -> {linked_after}"
                )
            if linked_before or linked_after:
                logger.info(
                    "task_key links for %s: before=%s after=%s",
                    table,
                    linked_before,
                    linked_after,
                )

    return LoadResult(
        loaded=count,
        purged=purged,
        derived_polygons=derived,
        split=split,
    )


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
                _format_load_success_message(result),
                rows_affected=result.loaded,
                run_id=run_id,
            )
        logger.info("%s finished: %s", config.job_name, _format_load_success_message(result))
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
    ogh_disruption_job.run()
