"""Build PostGIS point geometry from genplan JSON coordinates."""

from __future__ import annotations

import math
from typing import Any

POINT_GEOM_SQL = "ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)"

_COORD_KEYS = (
    ("lat", "lng"),
    ("latitude", "longitude"),
)


def is_valid_wgs84_pair(lat: float | None, lng: float | None) -> bool:
    """True when both values are finite WGS84 coordinates."""
    if lat is None or lng is None:
        return False
    if not math.isfinite(lat) or not math.isfinite(lng):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def _coord_value(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def try_parse_coordinates(payload: dict[str, Any]) -> tuple[float, float] | None:
    """Return WGS84 (lat, lng) when both fields are present and valid."""
    for lat_key, lng_key in _COORD_KEYS:
        if lat_key not in payload or lng_key not in payload:
            continue
        lat = _coord_value(payload[lat_key])
        lng = _coord_value(payload[lng_key])
        if lat is None or lng is None:
            return None
        if not is_valid_wgs84_pair(lat, lng):
            return None
        return lat, lng
    return None


def parse_coordinates(payload: dict[str, Any]) -> tuple[float, float]:
    """Return WGS84 (lat, lng) from a JSON object or raise ValueError."""
    coords = try_parse_coordinates(payload)
    if coords is not None:
        return coords

    for lat_key, lng_key in _COORD_KEYS:
        if lat_key in payload and lng_key in payload:
            lat_raw, lng_raw = payload[lat_key], payload[lng_key]
            if lat_raw is not None and lng_raw is not None:
                raise ValueError(
                    f"{lat_key} and {lng_key} must be numeric coordinates"
                )

    raise ValueError("lat and lng are required numeric fields")


def sync_coordinate_columns(
    props: dict[str, Any],
    *,
    lat: float,
    lng: float,
) -> dict[str, Any]:
    """Ensure lat/lng attribute columns match the coordinates used for geom."""
    updated = dict(props)
    updated["lat"] = lat
    updated["lng"] = lng
    return updated
