"""04:00 job — copy remote public schema tables into local lens schema."""

from __future__ import annotations

import logging

from psycopg2 import sql

from collector.db import (
    get_table_columns,
    list_remote_public_tables,
    local_connection,
    log_job_run,
    remote_connection,
)

logger = logging.getLogger(__name__)

JOB_NAME = "lens_sync"


def _ensure_lens_table(local_conn, table_name: str, columns: list[dict]) -> None:
    """Create lens.<table> from column metadata if it does not exist."""
    with local_conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'lens' AND table_name = %s
            )
            """,
            (table_name,),
        )
        if cur.fetchone()[0]:
            return

    col_parts = []
    for c in columns:
        name = c["column_name"]
        pg_type = _postgres_type(c)
        col_parts.append(sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(pg_type)))

    with local_conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE TABLE lens.{} ({})").format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(col_parts),
            )
        )
    logger.info("Created lens.%s", table_name)


def _postgres_type(col: dict) -> str:
    udt = (col.get("udt_name") or "").lower()
    dtype = (col.get("data_type") or "").lower()
    if udt == "geometry":
        return "geometry(Geometry, 4326)"
    mapping = {
        "int4": "integer",
        "int8": "bigint",
        "int2": "smallint",
        "float8": "double precision",
        "float4": "real",
        "bool": "boolean",
        "text": "text",
        "varchar": "character varying",
        "bpchar": "character",
        "json": "json",
        "jsonb": "jsonb",
        "uuid": "uuid",
        "date": "date",
        "timestamp": "timestamp without time zone",
        "timestamptz": "timestamp with time zone",
        "numeric": "numeric",
        "bytea": "bytea",
    }
    if udt in mapping:
        return mapping[udt]
    if dtype == "array":
        return "text[]"
    if dtype == "user-defined" and udt:
        return udt
    return "text"


def sync_table(remote_conn, local_conn, table_name: str) -> int:
    columns = get_table_columns(remote_conn, "public", table_name)
    if not columns:
        return 0

    _ensure_lens_table(local_conn, table_name, columns)
    col_names = [c["column_name"] for c in columns]

    with remote_conn.cursor() as rcur:
        rcur.execute(
            sql.SQL("SELECT {} FROM public.{}").format(
                sql.SQL(", ").join(sql.Identifier(n) for n in col_names),
                sql.Identifier(table_name),
            )
        )
        rows = rcur.fetchall()

    with local_conn.cursor() as lcur:
        lcur.execute(
            sql.SQL("TRUNCATE TABLE lens.{} RESTART IDENTITY CASCADE").format(
                sql.Identifier(table_name)
            )
        )
        if rows:
            insert_sql = sql.SQL("INSERT INTO lens.{} ({}) VALUES ({})").format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(sql.Identifier(n) for n in col_names),
                sql.SQL(", ").join(sql.Placeholder() * len(col_names)),
            )
            for row in rows:
                lcur.execute(insert_sql, row)

    return len(rows)


def run() -> None:
    run_id = None
    with local_connection() as conn:
        run_id = log_job_run(conn, JOB_NAME, "running", "Started lens sync")

    total_rows = 0
    tables_synced = 0

    try:
        with remote_connection() as remote_conn, local_connection() as local_conn:
            tables = list_remote_public_tables(remote_conn)
            if not tables:
                logger.warning("No tables found in remote public schema")

            for table_name in tables:
                try:
                    count = sync_table(remote_conn, local_conn, table_name)
                    total_rows += count
                    tables_synced += 1
                    logger.info("Synced lens.%s: %s rows", table_name, count)
                except Exception as exc:
                    logger.exception("Failed to sync table %s: %s", table_name, exc)
                    raise

        with local_connection() as conn:
            log_job_run(
                conn,
                JOB_NAME,
                "success",
                f"Synced {tables_synced} tables, {total_rows} rows",
                rows_affected=total_rows,
                run_id=run_id,
            )
        logger.info("lens_sync finished: %s tables, %s rows", tables_synced, total_rows)

    except Exception as exc:
        logger.exception("lens_sync job failed")
        with local_connection() as conn:
            log_job_run(conn, JOB_NAME, "failed", str(exc), run_id=run_id)
        raise
