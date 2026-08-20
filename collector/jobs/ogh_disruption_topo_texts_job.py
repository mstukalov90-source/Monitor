"""22:15 job — copy matching t500.topo_texts labels into odh_export.ogh-disruption.

Read-only SELECT from mggt. Reprojection MSK-77 (SRID 980077) → EPSG:4326
happens on the local PostGIS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from psycopg2 import sql

from collector.config import (
    OGH_ANALIZ_SOURCE_SRID,
    OGH_DISRUPTION_TOPOTEXT_SQL,
)
from collector.db import (
    execute_sql_file,
    local_connection,
    log_job_run,
    mggt_connection,
)

logger = logging.getLogger(__name__)

JOB_NAME = "ogh_disruption_topo_texts"
BOOTSTRAP_LIMIT = 50
SOURCE_SRID = OGH_ANALIZ_SOURCE_SRID
FILTER_PASS = "topo_texts"
QUALIFIED_TABLE = 'odh_export."ogh-disruption"'
REMOTE_SCHEMA = "t500"
REMOTE_TABLE = "topo_texts"
FETCH_SIZE = 250

LABEL_VALUES: tuple[str, ...] = (
    "РАЗР",
    "НАВАЛ",
    "РАЗР.",
    "НАВ.",
    "ЗАВАЛ",
    "ЗАВАЛЕНО",
    "ЗАВ.",
    "М.С.",
    "ЗЕМЛ.РАБ.",
    "ИЗРЫТО",
    "РЕКОНСТРУКЦИЯ",
    "РЕКОНСТР.",
    "РЕК-ЦИЯ",
    "ЯМА",
)


@dataclass(frozen=True)
class SyncResult:
    fetched: int
    loaded: int
    skipped: int
    last_fid: int
    mode: str


def is_bootstrap(last_fid: int) -> bool:
    return last_fid <= 0


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def row_is_complete(label_text: str | None, source_json: str | None, geom_ewkb: Any) -> bool:
    return bool(label_text and source_json and geom_ewkb)


def _ensure_local_table(local_conn) -> None:
    if not OGH_DISRUPTION_TOPOTEXT_SQL.exists():
        raise FileNotFoundError(f"SQL migration not found: {OGH_DISRUPTION_TOPOTEXT_SQL}")
    execute_sql_file(local_conn, OGH_DISRUPTION_TOPOTEXT_SQL)
    with local_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (SOURCE_SRID,))
        if cur.fetchone() is None:
            raise RuntimeError(
                f"spatial_ref_sys srid={SOURCE_SRID} is missing; "
                "apply sql/36_odh_export_ogh_analiz.sql"
            )


def _last_source_fid(cur) -> int:
    cur.execute(
        f"SELECT COALESCE(MAX(source_fid), 0) FROM {QUALIFIED_TABLE} WHERE filter_pass = %s",
        (FILTER_PASS,),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def remote_order_clause(*, limit: int | None) -> sql.SQL:
    if limit is None:
        return sql.SQL(" ORDER BY fid ASC")
    return sql.SQL(" ORDER BY fid DESC LIMIT %s")


def remote_select_sql(*, last_fid: int, limit: int | None) -> sql.Composed:
    query = sql.SQL(
        """
        SELECT fid, {label}, {base_name}, ST_AsEWKB({geom})
        FROM {schema}.{table}
        WHERE {label} IS NOT NULL
          AND btrim({label}) <> ''
          AND {geom} IS NOT NULL
          AND {base_name} IS NOT NULL
          AND btrim({base_name}::text) <> ''
          AND btrim({label}) = ANY(%s)
          AND fid > %s
        """
    ).format(
        label=sql.Identifier("label"),
        base_name=sql.Identifier("base_name"),
        geom=sql.Identifier("geom"),
        schema=sql.Identifier(REMOTE_SCHEMA),
        table=sql.Identifier(REMOTE_TABLE),
    )
    return query + remote_order_clause(limit=limit)


def _fetch_remote_rows(
    remote_conn,
    *,
    last_fid: int,
    limit: int | None,
) -> list[tuple[Any, ...]]:
    select_sql = remote_select_sql(last_fid=last_fid, limit=limit)
    params: list[Any] = [list(LABEL_VALUES), last_fid]
    if limit is not None:
        params.append(limit)
    rows: list[tuple[Any, ...]] = []
    with remote_conn.cursor(name="ogh_disruption_topo_texts") as cur:
        cur.itersize = FETCH_SIZE
        cur.execute(select_sql, params)
        while True:
            batch = cur.fetchmany(FETCH_SIZE)
            if not batch:
                break
            rows.extend(batch)
    return rows


def _upsert_row(cur, *, label_text: str, source_json: str, source_fid: int, geom_ewkb: Any) -> bool:
    cur.execute(
        f"""
        INSERT INTO {QUALIFIED_TABLE}
            (label_text, filter_pass, source_json, lon, lat, geometry, source_fid)
        SELECT
            %(label_text)s,
            %(filter_pass)s,
            %(source_json)s,
            ST_X(g.geom),
            ST_Y(g.geom),
            g.geom,
            %(source_fid)s
        FROM (
            SELECT ST_Force2D(
                ST_PointOnSurface(
                    ST_Transform(
                        ST_SetSRID(ST_GeomFromEWKB(%(ewkb)s), {SOURCE_SRID}),
                        4326
                    )
                )
            ) AS geom
        ) g
        WHERE g.geom IS NOT NULL
          AND NOT ST_IsEmpty(g.geom)
          AND GeometryType(g.geom) = 'POINT'
        ON CONFLICT (source_json, lon, lat) DO UPDATE SET
            label_text = EXCLUDED.label_text,
            filter_pass = EXCLUDED.filter_pass,
            geometry = EXCLUDED.geometry,
            source_fid = EXCLUDED.source_fid,
            loaded_at = NOW()
        """,
        {
            "label_text": label_text,
            "filter_pass": FILTER_PASS,
            "source_json": source_json,
            "source_fid": source_fid,
            "ewkb": geom_ewkb,
        },
    )
    return cur.rowcount > 0


def sync_topo_texts() -> SyncResult:
    with local_connection() as local_conn:
        _ensure_local_table(local_conn)
        with local_conn.cursor() as cur:
            last_fid = _last_source_fid(cur)

    mode = "bootstrap" if is_bootstrap(last_fid) else "incremental"
    limit = BOOTSTRAP_LIMIT if mode == "bootstrap" else None
    logger.info(
        "%s: mode=%s last_fid=%s limit=%s",
        JOB_NAME,
        mode,
        last_fid,
        limit,
    )

    with mggt_connection() as remote_conn:
        rows = _fetch_remote_rows(remote_conn, last_fid=last_fid, limit=limit)

    loaded = 0
    skipped = 0
    with local_connection() as local_conn:
        with local_conn.cursor() as cur:
            for fid, label, base_name, geom_ewkb in rows:
                label_text = normalize_text(label)
                source_json = normalize_text(base_name)
                if not row_is_complete(label_text, source_json, geom_ewkb):
                    skipped += 1
                    continue
                try:
                    inserted = _upsert_row(
                        cur,
                        label_text=label_text or "",
                        source_json=source_json or "",
                        source_fid=int(fid),
                        geom_ewkb=geom_ewkb,
                    )
                except Exception:
                    logger.warning(
                        "%s: skip fid=%s (transform/upsert failed)",
                        JOB_NAME,
                        fid,
                        exc_info=True,
                    )
                    skipped += 1
                    continue
                if inserted:
                    loaded += 1
                else:
                    skipped += 1
            new_last_fid = _last_source_fid(cur)

    return SyncResult(
        fetched=len(rows),
        loaded=loaded,
        skipped=skipped,
        last_fid=new_last_fid,
        mode=mode,
    )


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"Read-only {REMOTE_SCHEMA}.{REMOTE_TABLE} → {QUALIFIED_TABLE}",
        )

    try:
        result = sync_topo_texts()
        message = (
            f"{result.mode}: fetched={result.fetched}, loaded={result.loaded}, "
            f"skipped={result.skipped}, last_fid={result.last_fid}"
        )
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=result.loaded,
                run_id=run_id,
            )
        logger.info("%s finished: %s", JOB_NAME, message)
    except Exception as exc:
        logger.exception("%s failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
