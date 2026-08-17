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
JOB_NAME_ORDERS = "ogh_analiz_sync_orders"
FETCH_SIZE = 250
SOURCE_SRID = OGH_ANALIZ_SOURCE_SRID

# One-shot filter for --run ogh_analiz_sync_orders (column "OrderName").
# Values look like 12/ОГХ-26/...; in gis.ogh_analiz they live in "OrderName",
# while "order" holds a different identifier.
ONCE_ORDERS: tuple[str, ...] = (
    "12/ОГХ-26/48530",
    "12/ОГХ-26/60947",
    "12/ОГХ-26/68405",
    "12/ОГХ-26/49936",
    "12/ОГХ-26/49950",
    "12/ОГХ-26/49943",
    "12/ОГХ-26/66040",
    "12/ОГХ-26/66021",
    "12/ОГХ-26/50056",
    "12/ОГХ-26/50031",
    "12/ОГХ-26/66052",
    "12/ОГХ-26/49970",
    "12/ОГХ-26/49716",
    "12/ОГХ-26/49754",
    "12/ОГХ-26/49436",
    "12/ОГХ-26/49516",
    "12/ОГХ-26/68753",
    "12/ОГХ-26/49678",
    "12/ОГХ-26/49526",
    "12/ОГХ-26/07078",
    "12/ОГХ-26/50472",
    "12/ОГХ-26/66302",
    "12/ОГХ-26/59525",
    "12/ОГХ-26/59524",
    "12/ОГХ-26/59517",
    "12/ОГХ-26/59504",
    "12/ОГХ-26/59508",
    "12/ОГХ-26/65067",
    "12/ОГХ-26/65074",
    "12/ОГХ-26/65072",
    "12/ОГХ-26/65064",
    "12/ОГХ-26/65073",
    "12/ОГХ-26/57944",
    "12/ОГХ-26/57936",
    "12/ОГХ-26/66273",
    "12/ОГХ-26/48518",
    "12/ОГХ-26/48655",
    "12/ОГХ-26/47172",
    "12/ОГХ-26/46593",
    "12/ОГХ-26/45988",
    "12/ОГХ-26/46158",
    "12/ОГХ-26/47094",
    "12/ОГХ-26/46923",
    "12/ОГХ-26/46891",
    "12/ОГХ-26/48282",
    "12/ОГХ-26/50137",
    "12/ОГХ-26/50140",
    "12/ОГХ-26/50142",
    "12/ОГХ-26/69469",
    "12/ОГХ-26/46812/1",
    "12/ОГХ-26/76936",
    "12/ОГХ-26/76953",
    "12/ОГХ-26/49147",
    "12/ОГХ-26/77017",
    "12/ОГХ-26/51886/1",
    "12/ОГХ-26/77420",
    "12/ОГХ-26/78783",
)

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


def run_orders_once() -> None:
    """Manual one-shot: insert/update rows whose \"OrderName\" is in ONCE_ORDERS. No DELETE."""
    run_id = None
    qualified = f"{OGH_ANALIZ_LOCAL_SCHEMA}.{OGH_ANALIZ_LOCAL_TABLE}"
    with local_connection() as conn:
        run_id = log_job_run(
            conn,
            JOB_NAME_ORDERS,
            "running",
            f"Read-only OrderName filter ({len(ONCE_ORDERS)} values) "
            f"{OGH_ANALIZ_REMOTE_SCHEMA}.{OGH_ANALIZ_REMOTE_TABLE} → {qualified}",
        )

    try:
        result = sync_ogh_analiz(orders=ONCE_ORDERS, delete_missing=False)
        missing = ", ".join(result.missing_orders) if result.missing_orders else "none"
        message = (
            f"Synced {qualified} by OrderName: requested={len(ONCE_ORDERS)}, "
            f"source={result.source_rows}, inserted={result.inserted}, "
            f"updated={result.updated}, deleted={result.deleted}, "
            f"unchanged={result.unchanged}, missing={missing}"
        )
        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME_ORDERS,
                "success",
                message,
                rows_affected=result.source_rows,
                run_id=run_id,
            )
        logger.info("%s finished: %s", JOB_NAME_ORDERS, message)
        if result.missing_orders:
            logger.warning(
                "%s: %s order(s) not found: %s",
                JOB_NAME_ORDERS,
                len(result.missing_orders),
                ", ".join(result.missing_orders),
            )
    except Exception as exc:
        logger.exception("%s failed", JOB_NAME_ORDERS)
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME_ORDERS, "failed", str(exc), run_id=run_id)
        raise
