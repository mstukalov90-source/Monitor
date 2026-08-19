"""Tests for situation fnm → share path mapping."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collector.situation_photo_paths import (
    SituationPathError,
    file_relpath,
    path_for_fnm,
    photos_for_fnm,
    relpath_from_fnm,
)


class RelpathFromFnmTests(unittest.TestCase):
    def test_windows_file_path(self) -> None:
        self.assertEqual(
            relpath_from_fnm(r"2026_07\1196522362.jpg"),
            "2026_07/1196522362.jpg",
        )

    def test_forward_slashes(self) -> None:
        self.assertEqual(
            relpath_from_fnm("2026_08/1202369905.jpg"),
            "2026_08/1202369905.jpg",
        )

    def test_empty_fnm(self) -> None:
        with self.assertRaises(SituationPathError):
            relpath_from_fnm("")
        with self.assertRaises(SituationPathError):
            relpath_from_fnm(None)

    def test_traversal_rejected(self) -> None:
        with self.assertRaises(SituationPathError):
            relpath_from_fnm(r"..\secret.jpg")
        with self.assertRaises(SituationPathError):
            relpath_from_fnm(r"2026_07\..\..\etc\passwd")

    def test_absolute_rejected(self) -> None:
        with self.assertRaises(SituationPathError):
            relpath_from_fnm("/mnt/monitor/situation/x.jpg")
        with self.assertRaises(SituationPathError):
            relpath_from_fnm(r"X:\Common\x.jpg")


class PathForFnmTests(unittest.TestCase):
    def test_file_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "2026_07" / "1196522362.jpg"
            photo.parent.mkdir()
            photo.write_bytes(b"x")
            resolved = path_for_fnm(r"2026_07\1196522362.jpg", root)
            self.assertEqual(resolved, photo)
            self.assertEqual(
                file_relpath(resolved, root),
                "2026_07/1196522362.jpg",
            )

    def test_photos_for_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "2026_07" / "a.jpg"
            photo.parent.mkdir()
            photo.write_bytes(b"x")
            found = photos_for_fnm(r"2026_07\a.jpg", root)
            self.assertEqual(found, [photo])

    def test_missing_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(photos_for_fnm(r"2026_07\missing.jpg", root), [])

    def test_photos_for_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "batch"
            folder.mkdir()
            jpg = folder / "1.jpg"
            txt = folder / "note.txt"
            jpg.write_bytes(b"x")
            txt.write_text("no")
            found = photos_for_fnm("batch", root)
            self.assertEqual(found, [jpg])


if __name__ == "__main__":
    unittest.main()
