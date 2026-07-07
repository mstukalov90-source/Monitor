"""Tests for CRM task sync after data_mos ETL."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collector.crm_task_sync import (
    _insert_new_tasks,
    _link_split_rows,
    sync_crm_tasks_after_etl,
)
from collector.crm_task_sync_config import SERVICE_TASK_SYNC


class CrmTaskSyncSqlTests(unittest.TestCase):
    def test_insert_uses_distinct_on_scoped_business_id(self) -> None:
        cur = MagicMock()
        cur.rowcount = 3
        cfg = SERVICE_TASK_SYNC["items_2855"]
        layer = cfg.split_layers[0]
        inserted = _insert_new_tasks(cur, cfg, layer)
        self.assertEqual(inserted, 3)
        sql = cur.execute.call_args[0][0]
        self.assertIn("DISTINCT ON", sql)
        self.assertIn("CONCAT('point:', t.id::text)", sql)
        self.assertIn("t.task_key IS NULL", sql)
        self.assertIn('ON CONFLICT ("oati_id")', sql)
        self.assertIn("user_created", sql)

    def test_link_updates_split_and_anchor(self) -> None:
        cur = MagicMock()
        cur.rowcount = 2
        cfg = SERVICE_TASK_SYNC["items_62501"]
        layer = cfg.split_layers[1]
        linked = _link_split_rows(cur, cfg, layer)
        self.assertEqual(linked, 2)
        self.assertEqual(cur.execute.call_count, 2)
        link_sql = cur.execute.call_args_list[0][0][0]
        anchor_sql = cur.execute.call_args_list[1][0][0]
        self.assertIn("SET task_key = ct.key", link_sql)
        self.assertIn("CONCAT('line:', t.id::text)", link_sql)
        self.assertIn("source_geom_hash", anchor_sql)
        self.assertIn("source_table", anchor_sql)

    def test_sync_runs_for_known_service(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        result = sync_crm_tasks_after_etl(cur, "items_2855")
        self.assertGreaterEqual(cur.execute.call_count, 7)
        self.assertGreaterEqual(result.inserted, 0)

    def test_sync_skips_unknown_service(self) -> None:
        cur = MagicMock()
        result = sync_crm_tasks_after_etl(cur, "items_99999")
        cur.execute.assert_not_called()
        self.assertEqual(result.inserted, 0)


if __name__ == "__main__":
    unittest.main()
