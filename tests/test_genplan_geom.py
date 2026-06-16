"""Tests for genplan coordinate parsing and geom helpers."""

import unittest

from collector.genplan_geom import parse_coordinates, sync_coordinate_columns, try_parse_coordinates
from collector.genplan_photo_exif import PhotoUploadMeta


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

    def test_try_parse_null_coordinates(self) -> None:
        self.assertIsNone(try_parse_coordinates({"lat": None, "lng": None}))

    def test_try_parse_partial_coordinates(self) -> None:
        self.assertIsNone(try_parse_coordinates({"lat": 55.75}))
        self.assertIsNone(try_parse_coordinates({"lat": 55.75, "lng": None}))

    def test_try_parse_empty_string_coordinates(self) -> None:
        self.assertIsNone(try_parse_coordinates({"lat": "", "lng": "37.62"}))

    def test_sync_coordinate_columns(self) -> None:
        props = sync_coordinate_columns({"status": "done"}, lat=55.0, lng=37.0)
        self.assertEqual(props["lat"], 55.0)
        self.assertEqual(props["lng"], 37.0)


class TestPhotoUploadMeta(unittest.TestCase):
    def test_as_form_data_without_coordinates(self) -> None:
        data = PhotoUploadMeta(date="2026-06-02").as_form_data()
        self.assertEqual(data, {"date": "2026-06-02"})
        self.assertNotIn("lat", data)
        self.assertNotIn("lng", data)

    def test_as_form_data_with_coordinates_pair(self) -> None:
        data = PhotoUploadMeta(date="2026-06-02", lat=55.75, lng=37.62).as_form_data()
        self.assertEqual(data["lat"], 55.75)
        self.assertEqual(data["lng"], 37.62)

    def test_as_form_data_omits_partial_coordinates(self) -> None:
        data = PhotoUploadMeta(lat=55.75).as_form_data()
        self.assertNotIn("lat", data)
        self.assertNotIn("lng", data)


if __name__ == "__main__":
    unittest.main()
