"""05:00 job — import response_*.json files into genplan.responses."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from psycopg2.extras import Json

from collector.config import PROJECT_DIR
from collector.db import local_connection, log_job_run
from collector.flatten import (
    flatten_genplan_payload,
    order_coord_geojson,
    photo_point_geojson,
)

logger = logging.getLogger(__name__)

JOB_NAME = "genplan"

GENPLAN_COLUMNS = [
    "file_name", "opening", "legal", "description", "image",
    "photo_lat", "photo_lng", "photo_azimuth_deg",
    "order_source", "order_doc_num", "order_work_types",
    "order_date_start", "order_date_end", "order_customer", "order_status",
    "yolo_label", "yolo_votes",
]


def process_file(file_path: Path) -> None:
    with open(file_path, encoding="utf-8") as f:
        payload = json.load(f)

    flat = flatten_genplan_payload(payload, file_path.name)
    values = dict(flat)
    if values.get("yolo_votes") is not None:
        values["yolo_votes"] = Json(values["yolo_votes"])

    geom_json = order_coord_geojson(payload)
    photo_json = photo_point_geojson(payload)

    col_list = ", ".join(GENPLAN_COLUMNS)
    placeholders = ", ".join(f"%({c})s" for c in GENPLAN_COLUMNS)

    extra_cols = []
    extra_vals = []
    params = dict(values)

    if geom_json:
        extra_cols.append("geom")
        extra_vals.append("ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)")
        params["geom"] = geom_json
    if photo_json:
        extra_cols.append("photo_geom")
        extra_vals.append("ST_SetSRID(ST_GeomFromGeoJSON(%(photo_geom)s), 4326)")
        params["photo_geom"] = photo_json

    all_cols = col_list
    all_placeholders = placeholders
    if extra_cols:
        all_cols += ", " + ", ".join(extra_cols)
        all_placeholders += ", " + ", ".join(extra_vals)

    with local_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO genplan.responses ({all_cols}) VALUES ({all_placeholders})",
                params,
            )


def run() -> None:
    run_id = None
    files = sorted(PROJECT_DIR.glob("response_*.json"))

    with local_connection() as conn:
        run_id = log_job_run(
            conn, JOB_NAME, "running",
            f"Found {len(files)} response file(s)",
        )

    if not files:
        with local_connection() as conn:
            log_job_run(
                conn, JOB_NAME, "success",
                "No response_*.json files to process",
                rows_affected=0,
                run_id=run_id,
            )
        logger.info("genplan job: no files to process")
        return

    processed = 0
    try:
        for file_path in files:
            logger.info("Processing %s", file_path.name)
            process_file(file_path)
            file_path.unlink()
            logger.info("Imported and deleted %s", file_path.name)
            processed += 1

        with local_connection() as conn:
            log_job_run(
                conn, JOB_NAME, "success",
                f"Processed {processed} file(s)",
                rows_affected=processed,
                run_id=run_id,
            )
        logger.info("genplan job finished: %s file(s)", processed)

    except Exception as exc:
        logger.exception("genplan job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
