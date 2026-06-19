"""Field photo upload routes for the Android app."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from collector.api.auth import require_api_key
from collector.api.field_photo_storage import (
    FieldPhotoTooLargeError,
    save_field_photo,
)
from collector.api.schemas import FieldPhotoUploadResponse
from collector.config import MGGT_FIELD_PHOTO_MAX_BYTES

router = APIRouter(prefix="/api/mggtfield", tags=["mggtfield"])


async def _read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"file exceeds maximum size of {max_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/photos",
    response_model=FieldPhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid file or filename"},
        401: {"description": "Missing or invalid API key"},
        413: {"description": "File too large"},
        503: {"description": "Upload directory unavailable"},
    },
)
async def upload_field_photo(
    file: UploadFile = File(...),
    _: None = Depends(require_api_key),
) -> FieldPhotoUploadResponse:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename is required",
        )

    content = await _read_upload_limited(file, MGGT_FIELD_PHOTO_MAX_BYTES)

    try:
        saved = save_field_photo(content, filename)
    except FieldPhotoTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return FieldPhotoUploadResponse(
        saved_as=saved.saved_as,
        size_bytes=saved.size_bytes,
        content_type=saved.content_type,
    )
