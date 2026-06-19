"""Tests for POST /api/mggtfield/photos."""

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


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color="green").save(buf, format="JPEG")
    return buf.getvalue()


class MggtfieldPhotosApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._keys_patch = patch(
            "collector.api.auth.MONITOR_API_KEYS",
            frozenset({_TEST_API_KEY}),
        )
        self._keys_patch.start()
        self.client = TestClient(app)
        self._tmpdir = tempfile.TemporaryDirectory()
        self._upload_dir = Path(self._tmpdir.name)
        self._dir_patch = patch(
            "collector.api.field_photo_storage.MGGT_FIELD_PHOTO_DIR",
            self._upload_dir,
        )
        self._dir_patch.start()

    def tearDown(self) -> None:
        self._dir_patch.stop()
        self._tmpdir.cleanup()
        self._keys_patch.stop()

    def test_upload_requires_auth(self) -> None:
        response = self.client.post(
            "/api/mggtfield/photos",
            files={"file": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 401)

    def test_upload_saves_photo(self) -> None:
        response = self.client.post(
            "/api/mggtfield/photos",
            headers={"Authorization": f"Bearer {_TEST_API_KEY}"},
            files={"file": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["saved_as"], "photo.jpg")
        self.assertGreater(body["size_bytes"], 0)
        self.assertEqual(body["content_type"], "image/jpeg")
        self.assertTrue((self._upload_dir / "photo.jpg").is_file())

    def test_upload_rejects_invalid_extension(self) -> None:
        response = self.client.post(
            "/api/mggtfield/photos",
            headers={"Authorization": f"Bearer {_TEST_API_KEY}"},
            files={"file": ("photo.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
