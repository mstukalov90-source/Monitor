"""Persist field photos uploaded from the Android app."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from collector.config import MGGT_FIELD_PHOTO_DIR, MGGT_FIELD_PHOTO_MAX_BYTES
from collector.genplan_photo_exif import _PHOTO_SUFFIXES, photo_mime_type

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LEN = 200


class FieldPhotoTooLargeError(ValueError):
    """Raised when uploaded content exceeds MGGT_FIELD_PHOTO_MAX_BYTES."""


@dataclass(frozen=True)
class SavedPhoto:
    saved_as: str
    size_bytes: int
    content_type: str


def sanitize_filename(name: str) -> str:
    base = Path(name).name.strip()
    if not base or base in (".", ".."):
        raise ValueError("filename is required")

    sanitized = _FILENAME_SAFE.sub("_", base).strip("._")
    if not sanitized:
        raise ValueError("invalid filename")

    path = Path(sanitized)
    if path.suffix.lower() not in _PHOTO_SUFFIXES:
        raise ValueError("allowed extensions: .jpg, .jpeg, .png")

    if len(sanitized) > _MAX_FILENAME_LEN:
        suffix = path.suffix
        max_stem_len = _MAX_FILENAME_LEN - len(suffix)
        sanitized = path.stem[:max_stem_len] + suffix

    return sanitized


def ensure_upload_dir() -> Path:
    try:
        MGGT_FIELD_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"cannot create upload directory: {MGGT_FIELD_PHOTO_DIR}") from exc
    if not MGGT_FIELD_PHOTO_DIR.is_dir():
        raise OSError(f"upload path is not a directory: {MGGT_FIELD_PHOTO_DIR}")
    return MGGT_FIELD_PHOTO_DIR


def _validate_image_content(content: bytes) -> None:
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
        with Image.open(io.BytesIO(content)) as img:
            fmt = (img.format or "").upper()
    except OSError as exc:
        raise ValueError("file is not a valid image") from exc

    if fmt not in ("JPEG", "JPG", "PNG"):
        raise ValueError("allowed image types: JPEG, PNG")


def save_field_photo(content: bytes, original_filename: str) -> SavedPhoto:
    if not content:
        raise ValueError("empty file")
    if len(content) > MGGT_FIELD_PHOTO_MAX_BYTES:
        raise FieldPhotoTooLargeError(
            f"file exceeds maximum size of {MGGT_FIELD_PHOTO_MAX_BYTES} bytes"
        )

    saved_as = sanitize_filename(original_filename)
    _validate_image_content(content)

    dest_dir = ensure_upload_dir()
    dest = dest_dir / saved_as
    tmp = dest_dir / f".{saved_as}.tmp"

    try:
        tmp.write_bytes(content)
        tmp.replace(dest)
    except OSError as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise OSError(f"cannot write photo to {dest}") from exc

    content_type = photo_mime_type(Path(saved_as))
    return SavedPhoto(
        saved_as=saved_as,
        size_bytes=len(content),
        content_type=content_type,
    )
