"""Pydantic models for genplan M2M API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class PhotoMetaPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    uuid: Optional[str] = None
    status: Optional[str] = None
    start_at: Optional[str] = None
    date: Optional[str] = None
    disruption: Optional[bool] = None
    legal: Optional[bool] = None
    image_name: Optional[str] = None
    lat: float
    lng: float
    azimuth_deg: Optional[float] = None
    order_id: Optional[str] = None


class PhotoMetaResponse(BaseModel):
    uuid: str
    result: Literal["created", "updated"]


class FieldPhotoUploadResponse(BaseModel):
    saved_as: str
    size_bytes: int
    content_type: str
