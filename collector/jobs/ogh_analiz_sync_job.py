"""02:00 job — read-only copy of mggt_asu.gis.ogh_analiz into odh_export.ogh_analiz."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

from psycopg2 import sql
from psycopg2.extras import execute_values

from collector.config import (
    OGH_ANALIZ_LOCAL_SCHEMA,
    OGH_ANALIZ_LOCAL_TABLE,
    OGH_ANALIZ_REMOTE_SCHEMA,
    OGH_ANALIZ_REMOTE_TABLE,
    OGH_ANALIZ_SOURCE_SRID,
    OGH_ANALIZ_SQL,
)
from collector.db import (
    execute_sql_file,
    local_connection,
    log_job_run,
    mggt_asu_connection,
)

logger = logging.getLogger(__name__)

JOB_NAME = "ogh_analiz_sync"
FETCH_SIZE = 250
SOURCE_SRID = OGH_ANALIZ_SOURCE_SRID

ATTR_COLUMNS: tuple[str, ...] = (
    "id",
    "RootId",
    "ObjectId",
    "CustomerLegalPersonId",
    "DepartmentLegalPersonId",
    "CreateType",
    "Name",
    "Landscaping",
    "Link",
    "Type",
    "order",
    "DateSurvey",
    "StartDate",
    "BrId",
    "PassportizationYear",
    "OrderName",
    "OghStatus",
    "DepartmentWork",
    "itp_cr",
    "url",
    "GUID",
)
GEOM_COLUMN = "Geometry"
ALL_COLUMNS: tuple[str, ...] = ATTR_COLUMNS + (GEOM_COLUMN,)
COMPARE_COLUMNS: tuple[str, ...] = tuple(c for c in ALL_COLUMNS if c != "id")


@dataclass(frozen=True)
class SyncResult:
    source_rows: int
    inserted: int
    updated: int
    deleted: int
    missing_orders: tuple[str, ...] = field(default_factory=tuple)

    @property
    def unchanged(self) -> int:
        return max(self.source_rows - self.inserted - self.updated, 0)


def _idents(names: tuple[str, ...]) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(name) for name in names)


def _qualified_table() -> sql.Composed:
    return sql.SQL("{}.{}").format(
        sql.Identifier(OGH_ANALIZ_LOCAL_SCHEMA),
        sql.Identifier(OGH_ANALIZ_LOCAL_TABLE),
    )


def _aliased_idents(alias: str, names: tuple[str, ...]) -> sql.Composed:
    return sql.SQL(", ").join(
        sql.SQL("{}.{}").format(sql.Identifier(alias), sql.Identifier(name))
        for name in names
    )


def _ensure_local_table(local_conn) -> None:
    if not OGH_ANALIZ_SQL.exists():
        raise FileNotFoundError(f"SQL migration not found: {OGH_ANALIZ_SQL}")
    execute_sql_file(local_conn, OGH_ANALIZ_SQL)
    with local_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM spatial_ref_sys WHERE srid = %s", (SOURCE_SRID,))
        if cur.fetchone() is None:
            raise RuntimeError(
                f"spatial_ref_sys srid={SOURCE_SRID} is missing; "
                f"apply {OGH_ANALIZ_SQL.name}"
            )


def _create_staging(cur) -> None:
    cur.execute(
        sql.SQL(
            "CREATE TEMP TABLE ogh_analiz_src (LIKE {}.{} INCLUDING DEFAULTS) "
            "ON COMMIT DROP"
        ).format(
            sql.Identifier(OGH_ANALIZ_LOCAL_SCHEMA),
            sql.Identifier(OGH_ANALIZ_LOCAL_TABLE),
        )
    )
    cur.execute("CREATE INDEX ogh_analiz_src_id_idx ON ogh_analiz_src (id)")


def _remote_select_sql(*, orders: Sequence[str] | None = None) -> sql.Composed:
    query = sql.SQL("SELECT {}, ST_AsEWKB({}) FROM {}.{}").format(
        _idents(ATTR_COLUMNS),
        sql.Identifier(GEOM_COLUMN),
        sql.Identifier(OGH_ANALIZ_REMOTE_SCHEMA),
        sql.Identifier(OGH_ANALIZ_REMOTE_TABLE),
    )
    if orders:
        query += sql.SQL(" WHERE {} = ANY(%s)").format(sql.Identifier("OrderName"))
    return query


def _copy_remote_to_staging(
    remote_conn,
    local_cur,
    *,
    orders: Sequence[str] | None = None,
) -> int:
    insert_sql = (
        sql.SQL("INSERT INTO ogh_analiz_src ({cols}) VALUES %s")
        .format(cols=_idents(ALL_COLUMNS))
        .as_string(local_cur)
    )
    placeholders = ", ".join(["%s"] * len(ATTR_COLUMNS))
    template = (
        f"({placeholders}, "
        f"ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromEWKB(%s), {SOURCE_SRID}), 4326)))"
    )
    copied = 0
    select_sql = _remote_select_sql(orders=orders)
    with remote_conn.cursor(name="ogh_analiz_sync") as rcur:
        rcur.itersize = FETCH_SIZE
        if orders:
            rcur.execute(select_sql, (list(orders),))
        else:
            rcur.execute(select_sql)
        while True:
            batch = rcur.fetchmany(FETCH_SIZE)
            if not batch:
                break
            execute_values(
                local_cur,
                insert_sql,
                batch,
                template=template,
                page_size=FETCH_SIZE,
            )
            copied += len(batch)
            logger.info("%s: staged %s row(s)", JOB_NAME, copied)
    return copied


def _missing_orders(cur, requested: Sequence[str]) -> tuple[str, ...]:
    cur.execute(sql.SQL("SELECT DISTINCT {} FROM ogh_analiz_src").format(sql.Identifier("OrderName")))
    found = {row[0] for row in cur.fetchall() if row[0] is not None}
    return tuple(order for order in requested if order not in found)


def _merge_staging(cur, *, delete_missing: bool = True) -> tuple[int, int, int]:
    target = _qualified_table()
    deleted = 0
    if delete_missing:
        # Delete missing ids first so unique "OrderName" does not collide with updates.
        cur.execute(
            sql.SQL(
                """
                DELETE FROM {target} AS t
                WHERE NOT EXISTS (
                    SELECT 1 FROM ogh_analiz_src s WHERE s.id = t.id
                )
                """
            ).format(target=target)
        )
        deleted = cur.rowcount

    set_clause = sql.SQL(", ").join(
        sql.SQL("{col} = s.{col}").format(col=sql.Identifier(name))
        for name in COMPARE_COLUMNS
    )
    cur.execute(
        sql.SQL(
            """
            UPDATE {target} AS t SET
                {set_clause},
                loaded_at = NOW()
            FROM ogh_analiz_src AS s
            WHERE t.id = s.id
              AND ROW({compare_t}) IS DISTINCT FROM ROW({compare_s})
            """
        ).format(
            target=target,
            set_clause=set_clause,
            compare_t=_aliased_idents("t", COMPARE_COLUMNS),
            compare_s=_aliased_idents("s", COMPARE_COLUMNS),
        )
    )
    updated = cur.rowcount

    cur.execute(
        sql.SQL(
            """
            INSERT INTO {target} ({cols})
            SELECT {cols} FROM ogh_analiz_src s
            WHERE NOT EXISTS (
                SELECT 1 FROM {target} t WHERE t.id = s.id
            )
            """
        ).format(target=target, cols=_idents(ALL_COLUMNS))
    )
    inserted = cur.rowcount
    return inserted, updated, deleted


def sync_ogh_analiz(
    *,
    orders: Sequence[str] | None = None,
    delete_missing: bool = True,
) -> SyncResult:
    missing: tuple[str, ...] = ()
    with mggt_asu_connection() as remote_conn, local_connection() as local_conn:
        _ensure_local_table(local_conn)
        with local_conn.cursor() as cur:
            _create_staging(cur)
            source_rows = _copy_remote_to_staging(remote_conn, cur, orders=orders)
            if orders:
                missing = _missing_orders(cur, orders)
            inserted, updated, deleted = _merge_staging(cur, delete_missing=delete_missing)
    return SyncResult(
        source_rows=source_rows,
        inserted=inserted,
        updated=updated,
        deleted=deleted,
        missing_orders=missing,
    )


def run() -> None:
    run_id = None
    qualified = f"{OGH_ANALIZ_LOCAL_SCHEMA}.{OGH_ANALIZ_LOCAL_TABLE}"
    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME,
            "running",
            f"Read-only sync {OGH_ANALIZ_REMOTE_SCHEMA}.{OGH_ANALIZ_REMOTE_TABLE} "
            f"→ {qualified}",
        )

    try:
        result = sync_ogh_analiz()
        message = (
            f"Synced {qualified}: source={result.source_rows}, "
            f"inserted={result.inserted}, updated={result.updated}, "
            f"deleted={result.deleted}, unchanged={result.unchanged}"
        )
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                message,
                rows_affected=result.source_rows,
                run_id=run_id,
            )
        logger.info("%s finished: %s", JOB_NAME, message)
    except Exception as exc:
        logger.exception("%s failed", JOB_NAME)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise

