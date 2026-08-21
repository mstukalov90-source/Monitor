"""Tests for CRM photo task sync (genplan + lens)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collector.crm_photo_task_sync import (
    AI_PHOTO_SYNC,
    LENS_PHOTO_SYNC,
    _anchor_photo_tasks,
    _insert_photo_tasks,
    _reuse_ai_photo_tasks,
    sync_ai_photo_tasks,
    sync_lens_photo_tasks,
)


class CrmPhotoTaskSyncSqlTests(unittest.TestCase):
    def test_ai_photo_insert_reuses_camera_and_keeps_null_cam_id(self) -> None:
        cur = MagicMock()
        cur.rowcount = 5
        inserted = _insert_photo_tasks(cur, AI_PHOTO_SYNC)
        self.assertEqual(inserted, 5)
        sql = cur.execute.call_args[0][0]
        self.assertIn("DISTINCT ON", sql)
        self.assertNotIn("ON CONFLICT", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn('ct."photo_uuid"', sql)
        self.assertIn("t.disruption IS TRUE", sql)
        self.assertIn("NULLIF(TRIM(t.\"uuid\"::text), '')", sql)
        self.assertIn("user_created", sql)
        self.assertIn("t.cam_id IS NULL", sql)
        self.assertIn("field_observed IS NOT TRUE", sql)
        self.assertIn("'etl' = ANY(ct.user_last_edit)", sql)

    def test_reuse_ai_photo_updates_uuid_for_eligible_camera_task(self) -> None:
        cur = MagicMock()
        cur.rowcount = 2
        updated = _reuse_ai_photo_tasks(cur)
        self.assertEqual(updated, 2)
        sql = cur.execute.call_args[0][0]
        self.assertIn("UPDATE crm.tasks ct", sql)
        self.assertIn("SET photo_uuid = src.uuid", sql)
        self.assertIn("DISTINCT ON (t.cam_id)", sql)
        self.assertIn("field_observed IS NOT TRUE", sql)
        self.assertIn("'etl' = ANY(ct2.user_last_edit)", sql)
        self.assertIn("ORDER BY ct2.key DESC", sql)
        self.assertIn("ct.photo_uuid IS DISTINCT FROM src.uuid", sql)
        self.assertEqual(cur.execute.call_args[0][1][0], "genplan.photo_meta")

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
        self.assertNotIn("cam_id", sql)

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

    def test_sync_ai_photo_runs_reuse_insert_and_anchor(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchone.return_value = (1,)
        result = sync_ai_photo_tasks(cur)
        self.assertEqual(cur.execute.call_count, 5)
        sqls = [call[0][0] for call in cur.execute.call_args_list]
        self.assertIn("UPDATE crm.tasks ct", sqls[0])
        self.assertIn("INSERT INTO crm.tasks", sqls[1])
        self.assertEqual(sqls[-1], "CALL crm.refresh_task_area_keys()")
        self.assertGreaterEqual(result.inserted, 0)
        self.assertGreaterEqual(result.updated, 0)

    def test_sync_ai_skips_refresh_when_procedure_missing(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchone.return_value = None
        result = sync_ai_photo_tasks(cur)
        sqls = [call[0][0] for call in cur.execute.call_args_list]
        self.assertNotIn("CALL crm.refresh_task_area_keys()", sqls)
        self.assertGreaterEqual(result.inserted, 0)

    def test_sync_lens_photo_runs_insert_and_anchor(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchone.return_value = (1,)
        result = sync_lens_photo_tasks(cur)
        self.assertEqual(cur.execute.call_count, 4)
        self.assertEqual(cur.execute.call_args_list[-1][0][0], "CALL crm.refresh_task_area_keys()")
        self.assertGreaterEqual(result.inserted, 0)
        self.assertEqual(result.updated, 0)


if __name__ == "__main__":
    unittest.main()
