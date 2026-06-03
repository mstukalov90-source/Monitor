"""Tests for GeometryCollection part iteration."""

from __future__ import annotations

import unittest

from shapely.geometry import GeometryCollection, LineString, Point

from collector.geom_line_to_polygon import iter_geometry_collection_parts, iter_line_parts


class GeometryCollectionPartsTests(unittest.TestCase):
    def test_iter_parts_flat_collection(self) -> None:
        point = Point(1, 2)
        line = LineString([(0, 0), (1, 0), (1, 1), (0, 0)])
        collection = GeometryCollection([point, line])
        parts = list(iter_geometry_collection_parts(collection))
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].geom_type, "Point")
        self.assertEqual(parts[1].geom_type, "LineString")

    def test_iter_parts_nested_collection(self) -> None:
        inner = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
        outer = GeometryCollection([inner, Point(2, 2)])
        parts = list(iter_geometry_collection_parts(outer))
        self.assertEqual(len(parts), 3)
        self.assertEqual({p.geom_type for p in parts}, {"Point", "LineString"})

    def test_iter_line_parts_from_collection(self) -> None:
        collection = GeometryCollection([
            Point(1, 1),
            LineString([(0, 0), (1, 0), (1, 1), (0, 0)]),
        ])
        lines = list(iter_line_parts(collection))
        self.assertEqual(len(lines), 1)
        self.assertIsInstance(lines[0], LineString)

    def test_iter_line_parts_standalone(self) -> None:
        line = LineString([(0, 0), (1, 1)])
        self.assertEqual(list(iter_line_parts(line)), [line])


if __name__ == "__main__":
    unittest.main()
