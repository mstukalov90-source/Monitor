"""Persist MSI Holes photo upload responses into genplan.uploaded_photo."""

from __future__ import annotations

from typing import Any

from collector.db import local_connection
from collector.genplan_photo_exif import PhotoUploadMeta
from collector.genplan_geom import sync_coordinate_columns, try_parse_coordinates
from collector.genplan_detect import GenplanKind
from collector.genplan_schema import (
    collect_schema_from_properties,
    ensure_columns,
    ensure_genplan_table,
    extract_genplan_properties,
    insert_genplan_row,
    qualified_table,
)

UPLOADED_PHOTO_KIND: GenplanKind = "uploaded_photo"

UPLOADED_PHOTO_TABLE = qualified_table(UPLOADED_PHOTO_KIND)


def _merged_payload(
    response: dict[str, Any],
    request_meta: PhotoUploadMeta,
) -> dict[str, Any]:
    payload = dict(response)
    for key, value in request_meta.as_db_payload().items():
        if value is not None and key not in payload:
            payload[key] = value
    return payload


def insert_uploaded_photo(
    response: dict[str, Any],
    *,
    file_name: str,
    request_meta: PhotoUploadMeta,
) -> None:
    """Insert one upload response row with request metadata."""
    payload = _merged_payload(response, request_meta)
    coords = try_parse_coordinates(payload)
    lat, lng = coords if coords is not None else (None, None)

    with local_connection() as conn:
        with conn.cursor() as cur:
            ensure_genplan_table(cur, UPLOADED_PHOTO_KIND)
            props = extract_genplan_properties(
                payload,
                kind=UPLOADED_PHOTO_KIND,
                extra={"uuid": payload.get("uuid")},
            )
            if coords is not None:
                props = sync_coordinate_columns(props, lat=coords[0], lng=coords[1])
            schema = collect_schema_from_properties(props)
            ensure_columns(cur, UPLOADED_PHOTO_TABLE, schema)
            insert_genplan_row(
                cur,
                UPLOADED_PHOTO_KIND,
                schema,
                file_name,
                props,
                lat=lat,
                lng=lng,
            )


def load_uploaded_file_names() -> set[str]:
    """Return source photo file names already stored in genplan.uploaded_photo."""
    with local_connection() as conn:
        with conn.cursor() as cur:
            ensure_genplan_table(cur, UPLOADED_PHOTO_KIND)
            cur.execute(
                f"""
                SELECT DISTINCT file_name FROM {UPLOADED_PHOTO_TABLE}
                WHERE file_name IS NOT NULL AND btrim(file_name) <> ''
                """
            )
            return {row[0] for row in cur.fetchall()}
