"""Tests for field photo filename sanitization and storage."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from collector.api.field_photo_storage import (
    FieldPhotoTooLargeError,
    sanitize_filename,
    save_field_photo,
)


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buf, format="PNG")
    return buf.getvalue()


class SanitizeFilenameTests(unittest.TestCase):
    def test_accepts_simple_jpg_name(self) -> None:
        self.assertEqual(sanitize_filename("photo.jpg"), "photo.jpg")

    def test_strips_directory_components(self) -> None:
        self.assertEqual(sanitize_filename("../../etc/passwd.jpg"), "passwd.jpg")

    def test_rejects_unsafe_extension(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_filename("photo.exe")

    def test_sanitizes_special_characters(self) -> None:
        self.assertEqual(
            sanitize_filename("my photo (1).jpg"),
            "my_photo_1_.jpg",
        )


class SaveFieldPhotoTests(unittest.TestCase):
    def test_saves_jpeg_with_client_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            with patch(
                "collector.api.field_photo_storage.MGGT_FIELD_PHOTO_DIR",
                upload_dir,
            ):
                saved = save_field_photo(_jpeg_bytes(), "field_2026-06-19.jpg")

            self.assertEqual(saved.saved_as, "field_2026-06-19.jpg")
            self.assertEqual(saved.content_type, "image/jpeg")
            self.assertTrue((upload_dir / "field_2026-06-19.jpg").is_file())

    def test_overwrites_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            with patch(
                "collector.api.field_photo_storage.MGGT_FIELD_PHOTO_DIR",
                upload_dir,
            ):
                save_field_photo(_jpeg_bytes(), "dup.jpg")
                save_field_photo(_png_bytes(), "dup.jpg")

            self.assertEqual((upload_dir / "dup.jpg").read_bytes(), _png_bytes())

    def test_rejects_oversized_content(self) -> None:
        with patch(
            "collector.api.field_photo_storage.MGGT_FIELD_PHOTO_MAX_BYTES",
            10,
        ):
            with self.assertRaises(FieldPhotoTooLargeError):
                save_field_photo(_jpeg_bytes(), "big.jpg")


if __name__ == "__main__":
    unittest.main()
