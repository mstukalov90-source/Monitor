"""Tests for CRM photo task sync (genplan + lens)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collector.crm_photo_task_sync import (
    AI_PHOTO_SYNC,
    LENS_PHOTO_SYNC,
    _anchor_photo_tasks,
    _insert_photo_tasks,
    sync_ai_photo_tasks,
    sync_lens_photo_tasks,
)


class CrmPhotoTaskSyncSqlTests(unittest.TestCase):
    def test_ai_photo_insert_has_not_exists_and_disruption_filter(self) -> None:
        cur = MagicMock()
        cur.rowcount = 5
        inserted = _insert_photo_tasks(cur, AI_PHOTO_SYNC)
        self.assertEqual(inserted, 5)
        sql = cur.execute.call_args[0][0]
        self.assertNotIn("DISTINCT ON", sql)
        self.assertNotIn("ON CONFLICT", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn('ct."photo_uuid"', sql)
        self.assertIn("t.disruption IS TRUE", sql)
        self.assertIn("NULLIF(TRIM(t.\"uuid\"::text), '')", sql)
        self.assertIn("user_created", sql)

    def test_lens_insert_has_not_exists_and_external_report_id(self) -> None:
        cur = MagicMock()
        cur.rowcount = 12
        inserted = _insert_photo_tasks(cur, LENS_PHOTO_SYNC)
        self.assertEqual(inserted, 12)
        sql = cur.execute.call_args[0][0]
        self.assertNotIn("DISTINCT ON", sql)
        self.assertNotIn("ON CONFLICT", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn('ct."photo_lens"', sql)
        self.assertIn("external_report_id", sql)
        self.assertNotIn("disruption", sql)

    def test_anchor_updates_source_table(self) -> None:
        cur = MagicMock()
        cur.rowcount = 3
        anchored = _anchor_photo_tasks(cur, LENS_PHOTO_SYNC)
        self.assertEqual(anchored, 3)
        sql = cur.execute.call_args[0][0]
        self.assertIn("source_table", sql)
        self.assertIn("source_row_id", sql)
        self.assertIn("source_geom_hash", sql)
        self.assertEqual(cur.execute.call_args[0][1], ["lens.reports"])

    def test_sync_ai_photo_runs_insert_and_anchor(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        result = sync_ai_photo_tasks(cur)
        self.assertEqual(cur.execute.call_count, 2)
        self.assertGreaterEqual(result.inserted, 0)

    def test_sync_lens_photo_runs_insert_and_anchor(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        result = sync_lens_photo_tasks(cur)
        self.assertEqual(cur.execute.call_count, 2)
        self.assertGreaterEqual(result.inserted, 0)


if __name__ == "__main__":
    unittest.main()
