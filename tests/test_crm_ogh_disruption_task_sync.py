"""Tests for CRM task sync from odh_export.ogh-disruption."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collector.crm_ogh_disruption_task_sync import (
    SOURCE_TABLE_NAME,
    SOURCE_TABLE_SQL,
    _anchor_ogh_disruption_tasks,
    _insert_ogh_disruption_tasks,
    sync_ogh_disruption_tasks,
)
from collector.crm_photo_task_sync import CRM_GROUP_DISRUPTIONS


class CrmOghDisruptionTaskSyncSqlTests(unittest.TestCase):
    def test_insert_has_not_exists_and_quoted_table(self) -> None:
        cur = MagicMock()
        cur.rowcount = 7
        inserted = _insert_ogh_disruption_tasks(cur)
        self.assertEqual(inserted, 7)
        sql = cur.execute.call_args[0][0]
        params = cur.execute.call_args[0][1]
        self.assertNotIn("DISTINCT ON", sql)
        self.assertNotIn("ON CONFLICT", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn('ct."ogh_id"', sql)
        self.assertIn(SOURCE_TABLE_SQL, sql)
        self.assertIn('t."geometry"', sql)
        self.assertIn("NULLIF(TRIM(t.\"id\"::text), '')", sql)
        self.assertIn("user_created", sql)
        self.assertEqual(params[0], CRM_GROUP_DISRUPTIONS)

    def test_anchor_stores_unquoted_source_table(self) -> None:
        cur = MagicMock()
        cur.rowcount = 4
        anchored = _anchor_ogh_disruption_tasks(cur)
        self.assertEqual(anchored, 4)
        sql = cur.execute.call_args[0][0]
        self.assertIn("source_table", sql)
        self.assertIn("source_row_id", sql)
        self.assertIn("source_geom_hash", sql)
        self.assertIn(SOURCE_TABLE_SQL, sql)
        self.assertEqual(cur.execute.call_args[0][1], [SOURCE_TABLE_NAME])

    def test_sync_runs_insert_anchor_and_refresh(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchone.return_value = (1,)
        result = sync_ogh_disruption_tasks(cur)
        self.assertEqual(cur.execute.call_count, 4)
        self.assertEqual(
            cur.execute.call_args_list[-1][0][0],
            "CALL crm.refresh_task_area_keys()",
        )
        self.assertGreaterEqual(result.inserted, 0)
        self.assertGreaterEqual(result.linked, 0)

    def test_sync_skips_refresh_when_procedure_missing(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchone.return_value = None
        result = sync_ogh_disruption_tasks(cur)
        self.assertEqual(cur.execute.call_count, 3)
        sqls = [call.args[0] for call in cur.execute.call_args_list]
        self.assertNotIn("CALL crm.refresh_task_area_keys()", sqls)
        self.assertGreaterEqual(result.inserted, 0)


if __name__ == "__main__":
    unittest.main()
