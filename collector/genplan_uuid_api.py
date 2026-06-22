"""Persist colleague-submitted photo UUIDs into genplan.uuid_api."""

from __future__ import annotations

from collector.db import local_connection

UUID_API_TABLE = "genplan.uuid_api"


class UuidAlreadyExistsError(Exception):
    """Raised when uuid is already present in genplan.uuid_api."""


def normalize_uuid(raw: str) -> str:
    """Return trimmed uuid or raise ValueError."""
    uuid = str(raw).strip()
    if not uuid:
        raise ValueError("uuid is required")
    return uuid


def insert_uuid_api(uuid: str) -> None:
    """Insert one uuid row; raise UuidAlreadyExistsError if duplicate."""
    normalized = normalize_uuid(uuid)
    file_name = f"api:{normalized}"

    with local_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT 1 FROM {UUID_API_TABLE}
                WHERE uuid = %(uuid)s
                LIMIT 1
                """,
                {"uuid": normalized},
            )
            if cur.fetchone():
                raise UuidAlreadyExistsError(normalized)

            cur.execute(
                f"""
                INSERT INTO {UUID_API_TABLE} (file_name, uuid)
                VALUES (%(file_name)s, %(uuid)s)
                """,
                {"file_name": file_name, "uuid": normalized},
            )
