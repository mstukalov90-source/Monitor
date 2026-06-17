"""Tests for genplan UUID selection helpers."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from collector import genplan_uuids
from collector.genplan_uuids import (
    load_uploaded_photo_uuids,
    load_uploaded_uuids_pending_meta,
)


class TestGenplanUuids(unittest.TestCase):
    def test_load_uploaded_photo_uuids_empty_without_uuid_column(self) -> None:
        cur = MagicMock()
        with patch.object(genplan_uuids, "_table_has_column", return_value=False):
            self.assertEqual(load_uploaded_photo_uuids(cur), [])
        cur.execute.assert_not_called()

    def test_load_uploaded_photo_uuids_returns_ordered_uuids(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("uuid-a",), ("uuid-b",)]
        with patch.object(genplan_uuids, "_table_has_column", return_value=True):
            result = load_uploaded_photo_uuids(cur)
        self.assertEqual(result, ["uuid-a", "uuid-b"])
        sql = " ".join(cur.execute.call_args[0][0].split())
        self.assertIn("ORDER BY up.loaded_at", sql)

    def test_load_uploaded_photo_uuids_from_photo_uuid_column(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("photo-uuid-1",)]

        def has_column(_cur: Any, schema: str, table: str, column: str) -> bool:
            return table == "uploaded_photo" and column == "photo_uuid"

        with patch.object(genplan_uuids, "_table_has_column", side_effect=has_column):
            result = load_uploaded_photo_uuids(cur)

        self.assertEqual(result, ["photo-uuid-1"])
        sql = " ".join(cur.execute.call_args[0][0].split())
        self.assertIn("photo_uuid", sql)

    def test_pending_meta_uses_status_join_when_columns_exist(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("pending-uuid",)]

        def has_column(_cur: Any, schema: str, table: str, column: str) -> bool:
            if table == "uploaded_photo" and column in ("uuid", "photo_uuid"):
                return True
            if table == "photo_meta" and column in ("uuid", "status"):
                return True
            return False

        with patch.object(genplan_uuids, "_table_has_column", side_effect=has_column):
            result = load_uploaded_uuids_pending_meta(cur)

        self.assertEqual(result, ["pending-uuid"])
        sql = " ".join(cur.execute.call_args[0][0].split())
        self.assertIn("LEFT JOIN genplan.photo_meta pm", sql)
        self.assertIn("pm.status IS DISTINCT FROM 'done'", sql)

    def test_pending_meta_without_status_column(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("new-uuid",)]

        def has_column(_cur: Any, schema: str, table: str, column: str) -> bool:
            if table == "uploaded_photo" and column == "uuid":
                return True
            if table == "photo_meta" and column == "uuid":
                return True
            return False

        with patch.object(genplan_uuids, "_table_has_column", side_effect=has_column):
            result = load_uploaded_uuids_pending_meta(cur)

        self.assertEqual(result, ["new-uuid"])
        sql = " ".join(cur.execute.call_args[0][0].split())
        self.assertIn("pm.uuid IS NULL", sql)
        self.assertNotIn("status IS DISTINCT", sql)

    def test_pending_meta_without_photo_meta_uuid_column(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("all-uuid",)]

        def has_column(_cur: Any, schema: str, table: str, column: str) -> bool:
            return table == "uploaded_photo" and column == "uuid"

        with patch.object(genplan_uuids, "_table_has_column", side_effect=has_column):
            result = load_uploaded_uuids_pending_meta(cur)

        self.assertEqual(result, ["all-uuid"])
        sql = " ".join(cur.execute.call_args[0][0].split())
        self.assertNotIn("LEFT JOIN", sql)

    def test_pending_meta_empty_without_uploaded_uuid_column(self) -> None:
        cur = MagicMock()
        with patch.object(genplan_uuids, "_table_has_column", return_value=False):
            self.assertEqual(load_uploaded_uuids_pending_meta(cur), [])
        cur.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
