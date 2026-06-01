"""Database helpers for local and remote PostgreSQL connections."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from collector.config import LOCAL_DB, REMOTE_DB

logger = logging.getLogger(__name__)


def _conn_params(cfg: dict) -> dict:
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "dbname": cfg["dbname"],
        "user": cfg["user"],
        "password": cfg["password"],
    }


@contextmanager
def local_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(**_conn_params(LOCAL_DB))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def remote_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(**_conn_params(REMOTE_DB))
    try:
        yield conn
    finally:
        conn.close()


def log_job_run(
    conn: psycopg2.extensions.connection,
    job_name: str,
    status: str,
    message: Optional[str] = None,
    rows_affected: int = 0,
    run_id: Optional[int] = None,
) -> int:
    """Insert or update a job run record. Returns run id."""
    with conn.cursor() as cur:
        if run_id is None:
            cur.execute(
                """
                INSERT INTO collector.job_runs (job_name, status, message, rows_affected)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (job_name, status, message, rows_affected),
            )
            return cur.fetchone()[0]
        cur.execute(
            """
            UPDATE collector.job_runs
            SET status = %s, message = %s, rows_affected = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (status, message, rows_affected, run_id),
        )
        return run_id


def list_remote_public_tables(conn: psycopg2.extensions.connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [r[0] for r in cur.fetchall()]


def execute_sql_file(conn: psycopg2.extensions.connection, path: Path) -> None:
    """Run a SQL script (multiple statements) from a file."""
    sql = path.read_text(encoding="utf-8")
    sql = re.sub(r"--[^\n]*", "", sql)
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)


def get_table_columns(conn: psycopg2.extensions.connection, schema: str, table: str) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return list(cur.fetchall())
