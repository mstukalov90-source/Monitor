"""Tests for genplan coordinate parsing and geom helpers."""

import unittest

from collector.genplan_geom import parse_coordinates, sync_coordinate_columns


class TestGenplanGeom(unittest.TestCase):
    def test_parse_lat_lng(self) -> None:
        lat, lng = parse_coordinates({"lat": 55.75, "lng": 37.62})
        self.assertEqual(lat, 55.75)
        self.assertEqual(lng, 37.62)

    def test_parse_latitude_longitude(self) -> None:
        lat, lng = parse_coordinates({"latitude": 55.1, "longitude": 37.2})
        self.assertEqual(lat, 55.1)
        self.assertEqual(lng, 37.2)

    def test_parse_requires_coordinates(self) -> None:
        with self.assertRaises(ValueError):
            parse_coordinates({"status": "done"})

    def test_sync_coordinate_columns(self) -> None:
        props = sync_coordinate_columns({"status": "done"}, lat=55.0, lng=37.0)
        self.assertEqual(props["lat"], 55.0)
        self.assertEqual(props["lng"], 37.0)


if __name__ == "__main__":
    unittest.main()
