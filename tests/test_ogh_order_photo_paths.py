"""Tests for Заказы url → photo directory mapping."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collector.ogh_order_photo_paths import (
    ZakazyPathError,
    file_relpath,
    photo_dir_for_url,
    relpath_after_zakazy,
)


class RelpathAfterZakazyTests(unittest.TestCase):
    def test_drive_letter_x_path(self) -> None:
        rel = relpath_after_zakazy(r"X:\Common\ОГХ\Заказы\2026\12OGH-26_66815")
        self.assertEqual(rel, "2026/12OGH-26_66815")

    def test_unc_path(self) -> None:
        rel = relpath_after_zakazy(r"\\mggt\work\Common\ОГХ\Заказы\2026\12OGH-26_47772")
        self.assertEqual(rel, "2026/12OGH-26_47772")

    def test_forward_slashes(self) -> None:
        rel = relpath_after_zakazy("X:/Common/ОГХ/Заказы/2026/12OGH-26_66815")
        self.assertEqual(rel, "2026/12OGH-26_66815")

    def test_nested_after_order_folder(self) -> None:
        rel = relpath_after_zakazy(
            r"X:\Common\ОГХ\Заказы\2026\12OGH-26_49458\12OGH-26_49458_90393_D"
        )
        self.assertEqual(rel, "2026/12OGH-26_49458/12OGH-26_49458_90393_D")

    def test_empty_url(self) -> None:
        with self.assertRaises(ZakazyPathError):
            relpath_after_zakazy("")
        with self.assertRaises(ZakazyPathError):
            relpath_after_zakazy(None)

    def test_garbage_url(self) -> None:
        with self.assertRaises(ZakazyPathError):
            relpath_after_zakazy("П")

    def test_traversal_rejected(self) -> None:
        with self.assertRaises(ZakazyPathError):
            relpath_after_zakazy(r"X:\Common\ОГХ\Заказы\..\secret")


class PhotoDirForUrlTests(unittest.TestCase):
    def test_appends_field_photo_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo_dir = photo_dir_for_url(
                r"X:\Common\ОГХ\Заказы\2026\12OGH-26_66815",
                root,
            )
            self.assertEqual(
                photo_dir,
                root / "2026" / "12OGH-26_66815" / "02_Поле" / "Фото",
            )

    def test_file_relpath(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "2026" / "12OGH-26_66815" / "02_Поле" / "Фото" / "1.jpg"
            photo.parent.mkdir(parents=True)
            photo.write_bytes(b"x")
            self.assertEqual(
                file_relpath(photo.parent, photo, root),
                "2026/12OGH-26_66815/02_Поле/Фото/1.jpg",
            )


if __name__ == "__main__":
    unittest.main()
