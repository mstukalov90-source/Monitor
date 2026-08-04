"""Resolve on-disk photo paths for QGIS pull API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from collector.api.field_photo_storage import sanitize_filename
from collector.config import GENPLAN_DOWNLOAD_DIR, MGGT_FIELD_PHOTO_DIR
from collector.db import local_connection
from collector.genplan_photo_exif import _PHOTO_SUFFIXES, photo_mime_type

_UUID_FALLBACK_SUFFIXES = (".jpg", ".jpeg", ".png")


class PhotoNotFoundError(LookupError):
    """Raised when the photo file cannot be located."""


@dataclass(frozen=True)
class ResolvedPhoto:
    path: Path
    content_type: str
    filename: str


def _ensure_under_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError("path escapes photo directory")
    return resolved


def _existing_photo_under(root: Path, name: str) -> Path | None:
    candidate = _ensure_under_root(root / name, root)
    if candidate.is_file() and candidate.suffix.lower() in _PHOTO_SUFFIXES:
        return candidate
    return None


def _lookup_genplan_image_name(uuid: str) -> str | None:
    with local_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT image_name
                FROM genplan.photo_meta
                WHERE uuid = %s
                  AND image_name IS NOT NULL
                  AND btrim(image_name) <> ''
                LIMIT 1
                """,
                (uuid,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return str(row[0]).strip() or None


def resolve_genplan_photo(uuid: str) -> ResolvedPhoto:
    cleaned = (uuid or "").strip()
    if not cleaned:
        raise ValueError("uuid is required")

    root = GENPLAN_DOWNLOAD_DIR
    if not root.is_dir():
        raise PhotoNotFoundError(f"genplan photo directory unavailable: {root}")

    image_name = _lookup_genplan_image_name(cleaned)
    if image_name:
        try:
            safe_name = sanitize_filename(image_name)
        except ValueError:
            safe_name = None
        if safe_name:
            found = _existing_photo_under(root, safe_name)
            if found is not None:
                return ResolvedPhoto(
                    path=found,
                    content_type=photo_mime_type(found),
                    filename=found.name,
                )

    for suffix in _UUID_FALLBACK_SUFFIXES:
        found = _existing_photo_under(root, f"{cleaned}{suffix}")
        if found is not None:
            return ResolvedPhoto(
                path=found,
                content_type=photo_mime_type(found),
                filename=found.name,
            )

    raise PhotoNotFoundError(f"genplan photo not found for uuid={cleaned}")


def resolve_field_photo(filename: str) -> ResolvedPhoto:
    safe_name = sanitize_filename(filename)
    root = MGGT_FIELD_PHOTO_DIR
    if not root.is_dir():
        raise PhotoNotFoundError(f"field photo directory unavailable: {root}")

    found = _existing_photo_under(root, safe_name)
    if found is None:
        raise PhotoNotFoundError(f"field photo not found: {safe_name}")

    return ResolvedPhoto(
        path=found,
        content_type=photo_mime_type(found),
        filename=found.name,
    )
