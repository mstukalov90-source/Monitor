"""Tests for GET /api/qgis/photos/* download endpoints."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from collector.api.main import app

_TEST_API_KEY = "test-key-12345678901234567890123456789012"
_UUID = "550e8400-e29b-41d4-a716-446655440000"


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


class QgisPhotosApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._keys_patch = patch(
            "collector.api.auth.MONITOR_API_KEYS",
            frozenset({_TEST_API_KEY}),
        )
        self._keys_patch.start()
        self.client = TestClient(app)

        self._tmpdir = tempfile.TemporaryDirectory()
        base = Path(self._tmpdir.name)
        self._genplan_dir = base / "downloaded_photo"
        self._field_dir = base / "mggtfield_photo"
        self._genplan_dir.mkdir()
        self._field_dir.mkdir()

        self._genplan_dir_patch = patch(
            "collector.api.photo_download.GENPLAN_DOWNLOAD_DIR",
            self._genplan_dir,
        )
        self._field_dir_patch = patch(
            "collector.api.photo_download.MGGT_FIELD_PHOTO_DIR",
            self._field_dir,
        )
        self._genplan_dir_patch.start()
        self._field_dir_patch.start()

    def tearDown(self) -> None:
        self._field_dir_patch.stop()
        self._genplan_dir_patch.stop()
        self._tmpdir.cleanup()
        self._keys_patch.stop()

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {_TEST_API_KEY}"}

    def test_genplan_requires_auth(self) -> None:
        response = self.client.get(f"/api/qgis/photos/genplan/{_UUID}")
        self.assertEqual(response.status_code, 401)

    def test_field_requires_auth(self) -> None:
        response = self.client.get("/api/qgis/photos/field/photo.jpg")
        self.assertEqual(response.status_code, 401)

    def test_genplan_serves_by_uuid_fallback(self) -> None:
        (self._genplan_dir / f"{_UUID}.jpg").write_bytes(_jpeg_bytes())
        with patch(
            "collector.api.photo_download._lookup_genplan_image_name",
            return_value=None,
        ):
            response = self.client.get(
                f"/api/qgis/photos/genplan/{_UUID}",
                headers=self._auth(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertGreater(len(response.content), 0)

    def test_genplan_serves_by_image_name(self) -> None:
        name = "DVN_b_SVAO_201_1_2026-04-16.jpg"
        (self._genplan_dir / name).write_bytes(_jpeg_bytes())
        with patch(
            "collector.api.photo_download._lookup_genplan_image_name",
            return_value=name,
        ):
            response = self.client.get(
                f"/api/qgis/photos/genplan/{_UUID}",
                headers=self._auth(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")

    def test_genplan_not_found(self) -> None:
        with patch(
            "collector.api.photo_download._lookup_genplan_image_name",
            return_value=None,
        ):
            response = self.client.get(
                f"/api/qgis/photos/genplan/{_UUID}",
                headers=self._auth(),
            )
        self.assertEqual(response.status_code, 404)

    def test_field_serves_photo(self) -> None:
        (self._field_dir / "field.jpg").write_bytes(_jpeg_bytes())
        response = self.client.get(
            "/api/qgis/photos/field/field.jpg",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")

    def test_field_not_found(self) -> None:
        response = self.client.get(
            "/api/qgis/photos/field/missing.jpg",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 404)

    def test_field_rejects_path_traversal(self) -> None:
        response = self.client.get(
            "/api/qgis/photos/field/..%2Fsecret.jpg",
            headers=self._auth(),
        )
        self.assertIn(response.status_code, (400, 404))

    def test_field_rejects_invalid_extension(self) -> None:
        response = self.client.get(
            "/api/qgis/photos/field/notes.txt",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
