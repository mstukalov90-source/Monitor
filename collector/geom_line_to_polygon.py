"""Convert nearly-closed LineString / MultiLineString geometries to polygons."""

from __future__ import annotations

from typing import Iterator, Optional

from pyproj import Geod
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

_GEOD = Geod(ellps="WGS84")
_MIN_AREA_SQM = 1.0
_COORD_ROUND = 9


def geodesic_length_line(line: LineString) -> float:
    if line.is_empty or len(line.coords) < 2:
        return 0.0
    lons, lats = zip(*line.coords)
    return abs(_GEOD.line_length(lons, lats))


def geodesic_length(geom: BaseGeometry) -> float:
    if isinstance(geom, LineString):
        return geodesic_length_line(geom)
    if isinstance(geom, MultiLineString):
        return sum(geodesic_length_line(part) for part in geom.geoms)
    return 0.0


def geodesic_distance(p1: Point, p2: Point) -> float:
    _, _, dist = _GEOD.inv(p1.x, p1.y, p2.x, p2.y)
    return abs(dist)


def _coords_almost_equal(c1: tuple[float, ...], c2: tuple[float, ...]) -> bool:
    return abs(c1[0] - c2[0]) < 1e-12 and abs(c1[1] - c2[1]) < 1e-12


def _unique_vertex_count(coords: list[tuple[float, ...]]) -> int:
    rounded = {(round(c[0], _COORD_ROUND), round(c[1], _COORD_ROUND)) for c in coords}
    return len(rounded)


def _append_coords(base: list[tuple[float, ...]], addition: list[tuple[float, ...]]) -> None:
    if not addition:
        return
    if base and _coords_almost_equal(base[-1], addition[0]):
        base.extend(addition[1:])
    else:
        base.extend(addition)


def _build_ring_from_lines(lines: list[LineString]) -> Optional[LineString]:
    coords: list[tuple[float, ...]] = []
    for line in lines:
        if line.is_empty:
            continue
        _append_coords(coords, list(line.coords))
    if len(coords) < 3:
        return None
    return LineString(coords)


def _close_ring(ring: LineString) -> LineString:
    coords = list(ring.coords)
    if not _coords_almost_equal(coords[0], coords[-1]):
        coords.append(coords[0])
    return LineString(coords)


def _polygon_geodesic_area(poly: Polygon) -> float:
    area, _ = _GEOD.geometry_area_perimeter(poly)
    return abs(area)


def _largest_polygon(geom: BaseGeometry) -> Optional[Polygon]:
    if isinstance(geom, Polygon) and not geom.is_empty:
        return geom
    if isinstance(geom, MultiPolygon):
        polys = [part for part in geom.geoms if isinstance(part, Polygon) and not part.is_empty]
        if not polys:
            return None
        return max(polys, key=_polygon_geodesic_area)
    return None


def _ring_to_polygon(ring: LineString) -> Optional[Polygon]:
    closed = _close_ring(ring)
    if len(closed.coords) < 4:
        return None
    try:
        poly = Polygon(closed)
    except (ValueError, TypeError):
        return None
    valid = make_valid(poly)
    result = _largest_polygon(valid)
    if result is None:
        return None
    if _polygon_geodesic_area(result) < _MIN_AREA_SQM:
        return None
    return result


def _linestring_to_polygon(line: LineString, threshold: float) -> Optional[Polygon]:
    if line.is_empty or len(line.coords) < 2:
        return None
    total_len = geodesic_length_line(line)
    if total_len <= 0:
        return None
    gap = geodesic_distance(Point(line.coords[0]), Point(line.coords[-1]))
    if not line.is_closed and gap / total_len >= threshold:
        return None
    if _unique_vertex_count(list(line.coords)) < 3:
        return None
    return _ring_to_polygon(line)


def _multilinestring_to_polygon(mls: MultiLineString, threshold: float) -> Optional[Polygon]:
    lines = list(mls.geoms)
    if not lines:
        return None
    total_len = geodesic_length(mls)
    if total_len <= 0:
        return None
    first, last = lines[0], lines[-1]
    if first.is_empty or last.is_empty:
        return None
    gap = geodesic_distance(Point(first.coords[0]), Point(last.coords[-1]))
    if gap / total_len >= threshold:
        return None
    ring = _build_ring_from_lines(lines)
    if ring is None:
        return None
    if _unique_vertex_count(list(ring.coords)) < 3:
        return None
    return _ring_to_polygon(ring)


def iter_geometry_collection_parts(geom: BaseGeometry) -> Iterator[BaseGeometry]:
    """Yield leaf geometries from a (possibly nested) GeometryCollection."""
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, GeometryCollection):
        for part in geom.geoms:
            yield from iter_geometry_collection_parts(part)
    else:
        yield geom


def iter_line_parts(geom: BaseGeometry) -> Iterator[LineString | MultiLineString]:
    """Yield LineString / MultiLineString parts from any geometry tree."""
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, GeometryCollection):
        for part in geom.geoms:
            yield from iter_line_parts(part)
    elif isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString):
        yield geom


def try_line_to_polygon(geom: BaseGeometry, threshold: float = 0.1) -> Optional[Polygon]:
    """Build a polygon from a line geometry when it is closed or nearly closed."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, LineString):
        return _linestring_to_polygon(geom, threshold)
    if isinstance(geom, MultiLineString):
        return _multilinestring_to_polygon(geom, threshold)
    return None
