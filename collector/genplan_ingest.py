"""Import and upsert genplan photo_meta payloads into PostgreSQL."""

from __future__ import annotations

from typing import Any, Literal, Optional

from psycopg2.extensions import cursor as Cursor

from collector.data_mos_schema import prepare_value
from collector.db import local_connection
from collector.genplan_geom import POINT_GEOM_SQL, parse_coordinates, sync_coordinate_columns
from collector.genplan_schema import (
    collect_schema_from_properties,
    ensure_columns,
    ensure_genplan_table,
    extract_genplan_properties,
    insert_genplan_row,
    qualified_table,
)

PHOTO_META_KIND = "photo_meta"
PHOTO_META_TABLE = qualified_table(PHOTO_META_KIND)


def parse_lat_lng(payload: dict) -> tuple[float, float]:
    """Return lat/lng or raise ValueError."""
    return parse_coordinates(payload)


def _photo_uuid(payload: dict, *, fallback: Optional[str] = None) -> str:
    raw = payload.get("uuid", fallback)
    if raw is None or not str(raw).strip():
        raise ValueError("uuid is required")
    return str(raw).strip()


def _photo_meta_props(payload: dict, *, uuid: str) -> dict[str, Any]:
    return extract_genplan_properties(
        payload,
        kind=PHOTO_META_KIND,
        extra={"uuid": uuid},
    )


def _update_photo_meta_row(
    cur: Cursor,
    schema: dict[str, str],
    *,
    row_id: int,
    file_name: str,
    props: dict[str, Any],
    lat: float,
    lng: float,
) -> None:
    dyn_cols = sorted(schema.keys())
    set_parts = ['"file_name" = %(file_name)s', "loaded_at = NOW()"]
    set_parts.extend(f'"{col}" = %({col})s' for col in dyn_cols)
    set_parts.append(f"geom = {POINT_GEOM_SQL}")

    values: dict[str, Any] = {
        "id": row_id,
        "file_name": file_name,
        "lat": lat,
        "lng": lng,
        **{col: prepare_value(props.get(col), schema[col]) for col in dyn_cols},
    }
    cur.execute(
        f"UPDATE {PHOTO_META_TABLE} SET {', '.join(set_parts)} WHERE id = %(id)s",
        values,
    )


def _save_photo_meta(
    cur: Cursor,
    payload: dict,
    *,
    file_name: str,
    uuid: str,
    upsert: bool,
) -> Literal["created", "updated"]:
    lat, lng = parse_lat_lng(payload)
    ensure_genplan_table(cur, PHOTO_META_KIND)

    props = sync_coordinate_columns(
        _photo_meta_props(payload, uuid=uuid),
        lat=lat,
        lng=lng,
    )
    schema = collect_schema_from_properties(props)
    ensure_columns(cur, PHOTO_META_TABLE, schema)

    if upsert:
        cur.execute(
            f"""
            SELECT id FROM {PHOTO_META_TABLE}
            WHERE uuid = %(uuid)s
            LIMIT 1
            """,
            {"uuid": uuid},
        )
        row = cur.fetchone()
        if row:
            _update_photo_meta_row(
                cur,
                schema,
                row_id=row[0],
                file_name=file_name,
                props=props,
                lat=lat,
                lng=lng,
            )
            return "updated"

    insert_genplan_row(
        cur,
        PHOTO_META_KIND,
        schema,
        file_name,
        props,
        lat=lat,
        lng=lng,
    )
    return "created"


def insert_photo_meta(payload: dict, *, file_name: str) -> None:
    """Insert one photo_meta row from a JSON file import."""
    uuid = _photo_uuid(payload, fallback=file_name.removesuffix(".json"))
    with local_connection() as conn:
        with conn.cursor() as cur:
            _save_photo_meta(
                cur,
                payload,
                file_name=file_name,
                uuid=uuid,
                upsert=False,
            )


def upsert_photo_meta(payload: dict, *, source: str) -> Literal["created", "updated"]:
    """Insert or update photo_meta by uuid (M2M API)."""
    uuid = _photo_uuid(payload)
    with local_connection() as conn:
        with conn.cursor() as cur:
            return _save_photo_meta(
                cur,
                payload,
                file_name=source,
                uuid=uuid,
                upsert=True,
            )
