"""Copy tables from a remote PostgreSQL database into a local schema."""

from __future__ import annotations

import logging

from psycopg2 import sql

from collector.db import get_table_columns

logger = logging.getLogger(__name__)


def postgres_type(col: dict) -> str:
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


def ensure_table(
    local_conn,
    local_schema: str,
    table_name: str,
    columns: list[dict],
) -> None:
    """Create local schema table from column metadata if it does not exist."""
    with local_conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(local_schema)
            )
        )

    with local_conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
            """,
            (local_schema, table_name),
        )
        if cur.fetchone()[0]:
            return

    col_parts = []
    for c in columns:
        name = c["column_name"]
        pg_type = postgres_type(c)
        col_parts.append(sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(pg_type)))

    with local_conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier(local_schema),
                sql.Identifier(table_name),
                sql.SQL(", ").join(col_parts),
            )
        )
    logger.info("Created %s.%s", local_schema, table_name)


def sync_table(
    remote_conn,
    local_conn,
    remote_schema: str,
    remote_table: str,
    local_schema: str,
    local_table: str,
) -> int:
    """Full replace: TRUNCATE local table and copy all rows from remote."""
    columns = get_table_columns(remote_conn, remote_schema, remote_table)
    if not columns:
        return 0

    ensure_table(local_conn, local_schema, local_table, columns)
    col_names = [c["column_name"] for c in columns]

    with remote_conn.cursor() as rcur:
        rcur.execute(
            sql.SQL("SELECT {} FROM {}.{}").format(
                sql.SQL(", ").join(sql.Identifier(n) for n in col_names),
                sql.Identifier(remote_schema),
                sql.Identifier(remote_table),
            )
        )
        rows = rcur.fetchall()

    with local_conn.cursor() as lcur:
        lcur.execute(
            sql.SQL("TRUNCATE TABLE {}.{} RESTART IDENTITY CASCADE").format(
                sql.Identifier(local_schema),
                sql.Identifier(local_table),
            )
        )
        if rows:
            insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
                sql.Identifier(local_schema),
                sql.Identifier(local_table),
                sql.SQL(", ").join(sql.Identifier(n) for n in col_names),
                sql.SQL(", ").join(sql.Placeholder() * len(col_names)),
            )
            for row in rows:
                lcur.execute(insert_sql, row)

    return len(rows)
