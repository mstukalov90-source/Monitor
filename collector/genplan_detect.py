"""Classify genplan JSON payloads by structure (not filename)."""

from __future__ import annotations

from typing import Literal, Optional

GenplanKind = Literal["order", "photo_meta", "upload", "uuid_area"]

TABLE_BY_KIND: dict[GenplanKind, str] = {
    "order": "order",
    "photo_meta": "photo_meta",
    "upload": "upload",
    "uuid_area": "uuid_area",
}


def classify_genplan_payload(payload: object) -> Optional[GenplanKind]:
    """Return target table kind or None if structure is unrecognized."""
    if not isinstance(payload, dict):
        return None

    wkt = payload.get("wkt")
    if isinstance(wkt, str) and wkt.strip():
        return "order"

    uuids = payload.get("uuids")
    if isinstance(uuids, list):
        return "uuid_area"

    if "lat" in payload and "lng" in payload:
        return "photo_meta"

    if "wkt" not in payload and "uuids" not in payload and "lat" not in payload and "lng" not in payload:
        return "upload"

    return None
