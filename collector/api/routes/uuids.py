"""UUID ingest routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from collector.api.auth import require_api_key
from collector.api.schemas import UuidApiResponse
from collector.genplan_uuid_api import UuidAlreadyExistsError, insert_uuid_api, normalize_uuid

router = APIRouter(prefix="/api/uuids", tags=["uuids"])


@router.put(
    "/{uuid}",
    response_model=UuidApiResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid uuid"},
        401: {"description": "Missing or invalid API key"},
        409: {"description": "uuid already exists"},
    },
)
def put_uuid(
    uuid: str,
    _: None = Depends(require_api_key),
) -> UuidApiResponse:
    try:
        normalized = normalize_uuid(uuid)
        insert_uuid_api(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except UuidAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="uuid already exists",
        ) from exc

    return UuidApiResponse(uuid=normalized, result="created")
