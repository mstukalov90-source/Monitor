"""Purge archived rows from data_mos.items_* after each successful load."""

from __future__ import annotations

import logging
import re

from psycopg2.extensions import cursor as Cursor

from collector.config import TZ, DataMosPurgeRule

logger = logging.getLogger(__name__)

_COLUMN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_column(column: str) -> str:
    if not _COLUMN_NAME_RE.match(column):
        raise ValueError(f"Invalid purge column name: {column}")
    return column


def column_exists(cur: Cursor, schema: str, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
        """,
        (schema, table, column),
    )
    return cur.fetchone() is not None


def ensure_purge_functions(cur: Cursor) -> None:
    """Create parse helpers if missing (no-op when applied via initdb migration)."""
    cur.execute(
        """
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'data_mos' AND p.proname = 'parse_text_date'
        """
    )
    if cur.fetchone() is not None:
        return

    from collector.config import DATA_MOS_PURGE_FUNCTIONS_SQL
    from collector.db import execute_sql_file

    if not DATA_MOS_PURGE_FUNCTIONS_SQL.exists():
        raise FileNotFoundError(
            f"Purge functions SQL not found: {DATA_MOS_PURGE_FUNCTIONS_SQL}"
        )
    logger.info("Installing data_mos purge SQL functions")
    execute_sql_file(cur.connection, DATA_MOS_PURGE_FUNCTIONS_SQL)


def purge_archived(
    cur: Cursor,
    qualified_table: str,
    rule: DataMosPurgeRule,
    timezone: str = TZ,
) -> int:
    """
    Delete archived rows per service rule. Returns number of deleted rows.
    NULL/empty filter values are kept.
    """
    schema, table = qualified_table.split(".", 1)
    column = _validate_column(rule.column)

    ensure_purge_functions(cur)

    if not column_exists(cur, schema, table, column):
        logger.warning(
            "Purge skipped: column %s not found on %s",
            column, qualified_table,
        )
        return 0

    quoted_col = f'"{column}"'

    if rule.kind == "date_on_or_before_month_ago":
        cur.execute(
            f"""
            DELETE FROM {qualified_table}
            WHERE {quoted_col} IS NOT NULL
              AND btrim({quoted_col}::text) <> ''
              AND data_mos.parse_text_date({quoted_col}::text) IS NOT NULL
              AND data_mos.parse_text_date({quoted_col}::text) <= (
                  (NOW() AT TIME ZONE %s)::date - INTERVAL '1 month'
              )
            """,
            (timezone,),
        )
    elif rule.kind == "year_before_current":
        cur.execute(
            f"""
            DELETE FROM {qualified_table}
            WHERE {quoted_col} IS NOT NULL
              AND btrim({quoted_col}::text) <> ''
              AND data_mos.extract_year({quoted_col}::text) IS NOT NULL
              AND data_mos.extract_year({quoted_col}::text) < (
                  EXTRACT(YEAR FROM (NOW() AT TIME ZONE %s))::integer
              )
            """,
            (timezone,),
        )
    else:
        raise ValueError(f"Unknown purge rule kind: {rule.kind}")

    deleted = cur.rowcount
    logger.info(
        "Purged %s archived rows from %s (%s, %s)",
        deleted, qualified_table, column, rule.kind,
    )
    return deleted
