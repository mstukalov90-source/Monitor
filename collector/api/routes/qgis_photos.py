"""QGIS pull routes for downloading genplan and field photos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from collector.api.auth import require_api_key
from collector.api.photo_download import (
    PhotoNotFoundError,
    resolve_field_photo,
    resolve_genplan_photo,
)

router = APIRouter(prefix="/api/qgis", tags=["qgis"])


@router.get(
    "/photos/genplan/{uuid}",
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}},
        400: {"description": "Invalid uuid"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Photo not found"},
        503: {"description": "API key authentication is not configured"},
    },
)
def get_genplan_photo(
    uuid: str,
    _: None = Depends(require_api_key),
) -> FileResponse:
    try:
        photo = resolve_genplan_photo(uuid)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PhotoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return FileResponse(
        path=photo.path,
        media_type=photo.content_type,
        filename=photo.filename,
    )


@router.get(
    "/photos/field/{filename}",
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}},
        400: {"description": "Invalid filename"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Photo not found"},
        503: {"description": "API key authentication is not configured"},
    },
)
def get_field_photo(
    filename: str,
    _: None = Depends(require_api_key),
) -> FileResponse:
    try:
        photo = resolve_field_photo(filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PhotoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return FileResponse(
        path=photo.path,
        media_type=photo.content_type,
        filename=photo.filename,
    )
