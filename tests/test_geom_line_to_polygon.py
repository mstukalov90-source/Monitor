"""Tests for line-to-polygon geometry conversion."""

from __future__ import annotations

import math
import unittest

from shapely.geometry import LineString, MultiLineString, Polygon

from collector.geom_line_to_polygon import try_line_to_polygon


def _square(side_m: float, gap_m: float = 0.0, closed: bool = True) -> LineString:
    """Build a ~square ring near Moscow; optional open gap on the closing edge."""
    base_lon, base_lat = 37.6, 55.75
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = meters_per_deg_lat * math.cos(math.radians(base_lat))
    d_lon = side_m / meters_per_deg_lon
    d_lat = side_m / meters_per_deg_lat

    bl = (base_lon, base_lat)
    br = (base_lon + d_lon, base_lat)
    tr = (base_lon + d_lon, base_lat + d_lat)
    tl = (base_lon, base_lat + d_lat)
    coords = [bl, br, tr, tl]
    if closed and gap_m <= 0:
        coords.append(bl)
    elif gap_m > 0:
        end_lat = base_lat + gap_m / meters_per_deg_lat
        coords.append((base_lon, end_lat))
    return LineString(coords)


class TryLineToPolygonTests(unittest.TestCase):
    def test_closed_square_becomes_polygon(self) -> None:
        line = _square(side_m=100.0, closed=True)
        result = try_line_to_polygon(line)
        self.assertIsInstance(result, Polygon)
        self.assertGreater(result.area, 0)

    def test_nearly_closed_square_becomes_polygon(self) -> None:
        line = _square(side_m=100.0, gap_m=2.0, closed=False)
        result = try_line_to_polygon(line, threshold=0.1)
        self.assertIsInstance(result, Polygon)

    def test_open_line_is_skipped(self) -> None:
        line = _square(side_m=100.0, gap_m=60.0, closed=False)
        result = try_line_to_polygon(line, threshold=0.1)
        self.assertIsNone(result)

    def test_short_line_is_skipped(self) -> None:
        line = LineString([(37.6, 55.75), (37.6001, 55.75)])
        self.assertIsNone(try_line_to_polygon(line))

    def test_multilinestring_with_small_outer_gap(self) -> None:
        side = 100.0
        base_lon, base_lat = 37.6, 55.75
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = meters_per_deg_lat * math.cos(math.radians(base_lat))
        d_lon = side / meters_per_deg_lon
        d_lat = side / meters_per_deg_lat

        bl = (base_lon, base_lat)
        br = (base_lon + d_lon, base_lat)
        tr = (base_lon + d_lon, base_lat + d_lat)
        tl = (base_lon, base_lat + d_lat)
        near_bl = (base_lon, base_lat + 2.0 / meters_per_deg_lat)

        part1 = LineString([bl, br, tr])
        part2 = LineString([tl, near_bl])
        mls = MultiLineString([part1, part2])
        result = try_line_to_polygon(mls, threshold=0.1)
        self.assertIsInstance(result, Polygon)


if __name__ == "__main__":
    unittest.main()
