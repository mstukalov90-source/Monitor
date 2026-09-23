"""Load known genplan photo UUIDs from the local database."""

from __future__ import annotations

from psycopg2.extensions import cursor as Cursor


def _table_exists(cur: Cursor, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


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


def _uploaded_photo_has_uuid_column(cur: Cursor) -> bool:
    return (
        _table_has_column(cur, "genplan", "uploaded_photo", "uuid")
        or _table_has_column(cur, "genplan", "uploaded_photo", "photo_uuid")
    )


def _uploaded_photo_uuid_expr(cur: Cursor, alias: str = "up") -> str:
    """Effective MSI Holes photo id: uuid column, else photo_uuid."""
    has_uuid = _table_has_column(cur, "genplan", "uploaded_photo", "uuid")
    has_photo_uuid = _table_has_column(cur, "genplan", "uploaded_photo", "photo_uuid")
    if has_uuid and has_photo_uuid:
        return (
            f"COALESCE(NULLIF(btrim({alias}.uuid), ''), "
            f"NULLIF(btrim({alias}.photo_uuid), ''))"
        )
    if has_photo_uuid:
        return f"NULLIF(btrim({alias}.photo_uuid), '')"
    if has_uuid:
        return f"NULLIF(btrim({alias}.uuid), '')"
    return "NULL"


def load_genplan_uuids_with_meta(cur: Cursor) -> set[str]:
    """UUIDs that already have photo_meta or uploaded_photo — skip meta re-fetch."""
    known: set[str] = set()

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

    if _table_has_column(cur, "genplan", "uploaded_photo", "photo_uuid"):
        cur.execute(
            """
            SELECT photo_uuid FROM genplan.uploaded_photo
            WHERE photo_uuid IS NOT NULL AND btrim(photo_uuid) <> ''
            """
        )
        known.update(row[0] for row in cur.fetchall())

    return known


def load_genplan_uuid_area_uuids(cur: Cursor) -> set[str]:
    """UUIDs already recorded in genplan.uuid_area."""
    cur.execute(
        """
        SELECT uuid FROM genplan.uuid_area
        WHERE uuid IS NOT NULL AND btrim(uuid) <> ''
        """
    )
    return {row[0] for row in cur.fetchall()}


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

    if _table_exists(cur, "genplan", "uuid_api"):
        cur.execute(
            """
            SELECT uuid FROM genplan.uuid_api
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

    if _table_has_column(cur, "genplan", "uploaded_photo", "photo_uuid"):
        cur.execute(
            """
            SELECT photo_uuid FROM genplan.uploaded_photo
            WHERE photo_uuid IS NOT NULL AND btrim(photo_uuid) <> ''
            """
        )
        known.update(row[0] for row in cur.fetchall())

    return known


def load_uploaded_photo_uuids(cur: Cursor) -> list[str]:
    """Return all non-empty UUIDs from genplan.uploaded_photo, oldest first."""
    if not _uploaded_photo_has_uuid_column(cur):
        return []

    expr = _uploaded_photo_uuid_expr(cur, "up")
    cur.execute(
        f"""
        SELECT {expr}
        FROM genplan.uploaded_photo up
        WHERE {expr} IS NOT NULL
        ORDER BY up.loaded_at
        """
    )
    return [row[0] for row in cur.fetchall()]


def load_uploaded_uuids_pending_meta(cur: Cursor) -> list[str]:
    """Return uploaded_photo UUIDs missing from photo_meta or not yet done."""
    if not _uploaded_photo_has_uuid_column(cur):
        return []

    expr = _uploaded_photo_uuid_expr(cur, "up")
    has_status = _table_has_column(cur, "genplan", "photo_meta", "status")
    has_pm_uuid = _table_has_column(cur, "genplan", "photo_meta", "uuid")

    if has_pm_uuid and has_status:
        cur.execute(
            f"""
            SELECT {expr}
            FROM genplan.uploaded_photo up
            LEFT JOIN genplan.photo_meta pm ON pm.uuid = {expr}
            WHERE {expr} IS NOT NULL
              AND (pm.uuid IS NULL OR pm.status IS DISTINCT FROM 'done')
            ORDER BY up.loaded_at
            """
        )
    elif has_pm_uuid:
        cur.execute(
            f"""
            SELECT {expr}
            FROM genplan.uploaded_photo up
            LEFT JOIN genplan.photo_meta pm ON pm.uuid = {expr}
            WHERE {expr} IS NOT NULL
              AND pm.uuid IS NULL
            ORDER BY up.loaded_at
            """
        )
    else:
        cur.execute(
            f"""
            SELECT {expr}
            FROM genplan.uploaded_photo up
            WHERE {expr} IS NOT NULL
            ORDER BY up.loaded_at
            """
        )

    return [row[0] for row in cur.fetchall()]


def load_uuid_api_uuids_pending_meta(
    cur: Cursor,
    *,
    max_pending_days: int = 0,
) -> list[str]:
    """Return uuid_api UUIDs missing from photo_meta or not yet done.

    max_pending_days > 0 excludes UUIDs older than that many days: meta that
    never appears (permanent 404) stops being retried every night.
    """
    if not _table_exists(cur, "genplan", "uuid_api"):
        return []

    has_status = _table_has_column(cur, "genplan", "photo_meta", "status")
    has_pm_uuid = _table_has_column(cur, "genplan", "photo_meta", "uuid")
    age_filter = ""
    params: list = []
    if max_pending_days > 0:
        age_filter = "AND ua.loaded_at >= NOW() - (%s::int * INTERVAL '1 day')"
        params.append(max_pending_days)

    if has_pm_uuid and has_status:
        cur.execute(
            f"""
            SELECT ua.uuid
            FROM genplan.uuid_api ua
            LEFT JOIN genplan.photo_meta pm ON pm.uuid = ua.uuid
            WHERE ua.uuid IS NOT NULL AND btrim(ua.uuid) <> ''
              AND (pm.uuid IS NULL OR pm.status IS DISTINCT FROM 'done')
              {age_filter}
            ORDER BY ua.loaded_at
            """,
            params,
        )
    elif has_pm_uuid:
        cur.execute(
            f"""
            SELECT ua.uuid
            FROM genplan.uuid_api ua
            LEFT JOIN genplan.photo_meta pm ON pm.uuid = ua.uuid
            WHERE ua.uuid IS NOT NULL AND btrim(ua.uuid) <> ''
              AND pm.uuid IS NULL
              {age_filter}
            ORDER BY ua.loaded_at
            """,
            params,
        )
    else:
        cur.execute(
            f"""
            SELECT ua.uuid
            FROM genplan.uuid_api ua
            WHERE ua.uuid IS NOT NULL AND btrim(ua.uuid) <> ''
            {age_filter}
            ORDER BY ua.loaded_at
            """,
            params,
        )

    return [row[0] for row in cur.fetchall()]
