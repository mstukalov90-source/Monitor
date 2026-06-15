"""Photo metadata ingest routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from collector.api.auth import require_api_key
from collector.api.schemas import PhotoMetaPayload, PhotoMetaResponse
from collector.genplan_ingest import upsert_photo_meta

router = APIRouter(prefix="/api/photos", tags=["photos"])


@router.put(
    "/meta/{uuid}",
    response_model=PhotoMetaResponse,
    responses={
        400: {"description": "Invalid payload or uuid mismatch"},
        401: {"description": "Missing or invalid API key"},
    },
)
def put_photo_meta(
    uuid: str,
    payload: PhotoMetaPayload,
    response: Response,
    _: None = Depends(require_api_key),
) -> PhotoMetaResponse:
    path_uuid = uuid.strip()
    if not path_uuid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uuid path parameter is required",
        )

    body = payload.model_dump(mode="json", exclude_none=False)
    body_uuid = body.get("uuid")
    if body_uuid is not None and str(body_uuid).strip() and str(body_uuid).strip() != path_uuid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uuid in body must match uuid in path",
        )
    body["uuid"] = path_uuid

    try:
        result = upsert_photo_meta(body, source=f"api:{path_uuid}")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    response.status_code = (
        status.HTTP_201_CREATED if result == "created" else status.HTTP_200_OK
    )
    return PhotoMetaResponse(uuid=path_uuid, result=result)
