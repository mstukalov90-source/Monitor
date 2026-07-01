"""Load url_222_wgs.geojson into vector_stroy.url_222 with upsert by orbis_id."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import geopandas as gpd

from collector.config import PROJECT_DIR
from collector.data_mos_schema import (
    collect_schema,
    ensure_base_table,
    ensure_columns,
    extract_feature_properties,
    prepare_value,
)
from collector.db import local_connection, log_job_run
from collector.vector_mka_fetch import fetch_url_221_geojson, read_token

logger = logging.getLogger(__name__)

JOB_NAME = "vector_stroy_url_222"
SCHEMA = "vector_stroy"
TABLE = "url_222"
QUALIFIED_TABLE = f"{SCHEMA}.{TABLE}"
SOURCE_GEOJSON = PROJECT_DIR / "url_222_wgs.geojson"
UPSERT_KEY = "orbis_id"


@dataclass(frozen=True)
class LoadResult:
    loaded: int
    skipped_without_key: int
    purged_expired: int


def _load_geojson() -> gpd.GeoDataFrame:
    if not SOURCE_GEOJSON.exists():
        raise FileNotFoundError(f"GeoJSON not found: {SOURCE_GEOJSON}")

    gdf = gpd.read_file(SOURCE_GEOJSON)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def _upsert_feature(cur, schema: dict[str, str], props: dict[str, object], geom_json: str | None) -> None:
    cols = sorted(schema.keys())
    values = {col: prepare_value(props.get(col), schema[col]) for col in cols}

    if UPSERT_KEY not in values:
        raise ValueError(f"Upsert key '{UPSERT_KEY}' is missing in values")

    values["geom"] = geom_json

    col_list = ", ".join(f'"{c}"' for c in cols) + ", geom"
    placeholders = ", ".join(f"%({c})s" for c in cols) + ", ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)"
    update_cols = [col for col in cols if col != UPSERT_KEY]
    update_assignments = ", ".join(f'"{col}" = EXCLUDED."{col}"' for col in update_cols)
    if update_assignments:
        update_assignments += ", "
    update_assignments += "geom = EXCLUDED.geom, loaded_at = NOW()"

    cur.execute(
        f"""
        INSERT INTO {QUALIFIED_TABLE} ({col_list})
        VALUES ({placeholders})
        ON CONFLICT ("{UPSERT_KEY}") DO UPDATE
        SET {update_assignments}
        """,
        values,
    )


def _purge_expired(cur) -> int:
    cur.execute(
        f"""
        DELETE FROM {QUALIFIED_TABLE}
        WHERE status IS NOT NULL
          AND (
            btrim(status::text) IN ('Истек', 'Срок действия истек')
            OR lower(btrim(status::text)) LIKE '%истек%'
          )
        """
    )
    deleted = cur.rowcount
    logger.info("Purged %s expired rows from %s", deleted, QUALIFIED_TABLE)
    return deleted


def _reset_table(cur) -> None:
    """Drop table so ensure_columns can recreate columns with correct types."""
    cur.execute(f"DROP TABLE IF EXISTS {QUALIFIED_TABLE} CASCADE")
    logger.info("Dropped %s for full reload", QUALIFIED_TABLE)


def load_geojson_to_db() -> LoadResult:
    gdf = _load_geojson()
    schema = collect_schema(gdf)
    if UPSERT_KEY not in schema:
        schema[UPSERT_KEY] = "BIGINT"

    loaded = 0
    skipped_without_key = 0
    purged_expired = 0

    with local_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
            _reset_table(cur)
            ensure_base_table(cur, QUALIFIED_TABLE)
            ensure_columns(cur, QUALIFIED_TABLE, schema)
            cur.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS ux_{TABLE}_{UPSERT_KEY} '
                f'ON {QUALIFIED_TABLE} ("{UPSERT_KEY}")'
            )

            for _, row in gdf.iterrows():
                props = extract_feature_properties(row)
                key_value = props.get(UPSERT_KEY)
                if key_value is None or str(key_value).strip() == "":
                    skipped_without_key += 1
                    continue

                geom_json = None
                if row.geometry is not None and not row.geometry.is_empty:
                    geom_json = json.dumps(row.geometry.__geo_interface__)
                _upsert_feature(cur, schema, props, geom_json)
                loaded += 1
            purged_expired = _purge_expired(cur)

    return LoadResult(
        loaded=loaded,
        skipped_without_key=skipped_without_key,
        purged_expired=purged_expired,
    )


def _fetch_geojson_to_disk() -> bool:
    """Return True if file written, False if skipped (no token / fetch error)."""
    token = read_token()
    if not token:
        logger.warning("No vector.mka token — skipping fetch")
        return False

    try:
        data = fetch_url_221_geojson(token)
        SOURCE_GEOJSON.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Fetched %s from vector.mka", SOURCE_GEOJSON.name)
        return True
    except Exception:
        logger.exception("vector.mka fetch failed — skipping")
        return False


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"Source: vector.mka map221/rs_2022 → {SOURCE_GEOJSON.name}",
        )

    _fetch_geojson_to_disk()

    if not SOURCE_GEOJSON.exists():
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                f"No file to process: {SOURCE_GEOJSON.name}",
                rows_affected=0,
                run_id=run_id,
            )
        logger.info(
            "%s: %s not found in %s, skipping",
            JOB_NAME,
            SOURCE_GEOJSON.name,
            PROJECT_DIR,
        )
        return

    try:
        result = load_geojson_to_db()
        SOURCE_GEOJSON.unlink()
        logger.info("Deleted source file %s", SOURCE_GEOJSON)

        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                (
                    f"Upserted {result.loaded} feature(s) into {QUALIFIED_TABLE}; "
                    f"skipped {result.skipped_without_key} feature(s) without {UPSERT_KEY}; "
                    f"purged {result.purged_expired} expired rows (status contains 'истек')"
                ),
                rows_affected=result.loaded,
                run_id=run_id,
            )
        logger.info(
            "%s finished: %s upserted, %s skipped without %s, %s purged expired",
            JOB_NAME,
            result.loaded,
            result.skipped_without_key,
            UPSERT_KEY,
            result.purged_expired,
        )
    except Exception as exc:
        logger.exception("%s failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
