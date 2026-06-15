"""05:00 job — import jsons_genplan/*.json into typed genplan tables."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from collector.config import GENPLAN_JSON_DIR, GENPLAN_SAMPLE_FILES
from collector.db import local_connection, log_job_run
from collector.genplan_detect import classify_genplan_payload
from collector.genplan_ingest import insert_photo_meta
from collector.genplan_schema import (
    collect_schema_from_properties,
    ensure_columns,
    ensure_genplan_table,
    extract_genplan_properties,
    insert_genplan_row,
    merge_schema,
    qualified_table,
)

logger = logging.getLogger(__name__)

JOB_NAME = "genplan"


def process_file(file_path: Path) -> int:
    """Import one JSON file; return number of rows inserted."""
    with open(file_path, encoding="utf-8") as f:
        payload = json.load(f)

    kind = classify_genplan_payload(payload)
    if kind is None:
        raise ValueError(f"Unrecognized JSON structure: {file_path.name}")

    file_name = file_path.name

    if kind == "photo_meta":
        insert_photo_meta(payload, file_name=file_name)
        return 1

    rows = 0

    with local_connection() as conn:
        with conn.cursor() as cur:
            ensure_genplan_table(cur, kind)

            if kind == "uuid_area":
                uuids = payload.get("uuids") or []
                if not isinstance(uuids, list):
                    raise ValueError(f"uuids must be a list: {file_path.name}")

                schema: dict[str, str] = {}
                row_props: list[dict] = []
                for item in uuids:
                    props = extract_genplan_properties(
                        payload, kind=kind, extra={"uuid": item}
                    )
                    schema = merge_schema(schema, props)
                    row_props.append(props)

                ensure_columns(cur, qualified_table(kind), schema)
                for props in row_props:
                    insert_genplan_row(cur, kind, schema, file_name, props)
                    rows += 1
                return rows

            props = extract_genplan_properties(payload, kind=kind)
            schema = collect_schema_from_properties(props)
            ensure_columns(cur, qualified_table(kind), schema)

            wkt: str | None = None
            lat: float | None = None
            lng: float | None = None

            if kind == "order":
                wkt_val = payload.get("wkt")
                if not isinstance(wkt_val, str) or not wkt_val.strip():
                    raise ValueError(f"Missing wkt: {file_path.name}")
                wkt = wkt_val.strip()

            insert_genplan_row(
                cur,
                kind,
                schema,
                file_name,
                props,
                wkt=wkt,
                lat=lat,
                lng=lng,
            )
            rows = 1

    return rows


def run() -> None:
    run_id = None
    genplan_dir = GENPLAN_JSON_DIR
    if not genplan_dir.is_dir():
        genplan_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(genplan_dir.glob("*.json"))

    with local_connection() as conn:
        run_id = log_job_run(
            conn, JOB_NAME, "running",
            f"Found {len(files)} JSON file(s) in {genplan_dir.name}",
        )

    if not files:
        with local_connection() as conn:
            log_job_run(
                conn, JOB_NAME, "success",
                f"No JSON files in {genplan_dir.name}",
                rows_affected=0,
                run_id=run_id,
            )
        logger.info("genplan job: no files to process")
        return

    processed_files = 0
    total_rows = 0
    errors: list[str] = []

    for file_path in files:
        try:
            logger.info("Processing %s", file_path.name)
            row_count = process_file(file_path)
            total_rows += row_count
            processed_files += 1

            if file_path.name not in GENPLAN_SAMPLE_FILES:
                file_path.unlink()
                logger.info("Imported and deleted %s (%s row(s))", file_path.name, row_count)
            else:
                logger.info(
                    "Imported %s (%s row(s)); sample file kept",
                    file_path.name,
                    row_count,
                )
        except Exception as exc:
            logger.warning("Skipped %s: %s", file_path.name, exc)
            errors.append(f"{file_path.name}: {exc}")

    job_status = "failed" if errors and not processed_files else "success"
    message_parts = [f"Processed {processed_files} file(s), {total_rows} row(s)"]
    if errors:
        message_parts.append(f"{len(errors)} error(s): " + "; ".join(errors[:5]))
        if len(errors) > 5:
            message_parts.append("...")

    with local_connection() as conn:
        log_job_run(
            conn,
            JOB_NAME,
            job_status,
            "; ".join(message_parts),
            rows_affected=total_rows,
            run_id=run_id,
        )

    if errors and not processed_files:
        raise RuntimeError("; ".join(errors))

    logger.info("genplan job finished: %s file(s), %s row(s)", processed_files, total_rows)
