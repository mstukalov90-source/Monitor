"""Build PostGIS point geometry from genplan JSON coordinates."""

from __future__ import annotations

from typing import Any

POINT_GEOM_SQL = "ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)"

_COORD_KEYS = (
    ("lat", "lng"),
    ("latitude", "longitude"),
)


def parse_coordinates(payload: dict[str, Any]) -> tuple[float, float]:
    """Return WGS84 (lat, lng) from a JSON object or raise ValueError."""
    for lat_key, lng_key in _COORD_KEYS:
        if lat_key in payload and lng_key in payload:
            try:
                lat = float(payload[lat_key])
                lng = float(payload[lng_key])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{lat_key} and {lng_key} must be numeric coordinates"
                ) from exc
            return lat, lng

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
