"""Load known genplan photo UUIDs from the local database."""

from __future__ import annotations

from psycopg2.extensions import cursor as Cursor


def _table_has_column(cur: Cursor, schema: str, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (schema, table, column),
    )
    return cur.fetchone() is not None


def load_known_genplan_uuids(cur: Cursor) -> set[str]:
    """Return UUIDs already stored in genplan uuid/photo tables."""
    known: set[str] = set()

    cur.execute(
        """
        SELECT uuid FROM genplan.uuid_area
        WHERE uuid IS NOT NULL AND btrim(uuid) <> ''
        """
    )
    known.update(row[0] for row in cur.fetchall())

    if _table_has_column(cur, "genplan", "photo_meta", "uuid"):
        cur.execute(
            """
            SELECT uuid FROM genplan.photo_meta
            WHERE uuid IS NOT NULL AND btrim(uuid) <> ''
            """
        )
        known.update(row[0] for row in cur.fetchall())

    if _table_has_column(cur, "genplan", "uploaded_photo", "uuid"):
        cur.execute(
            """
            SELECT uuid FROM genplan.uploaded_photo
            WHERE uuid IS NOT NULL AND btrim(uuid) <> ''
            """
        )
        known.update(row[0] for row in cur.fetchall())

    return known
