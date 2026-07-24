"""Tests for CRM task sync after data_mos ETL."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from collector.crm_task_sync import (
    _insert_new_tasks,
    _link_split_rows,
    _sync_tasks_to_field,
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
        self.assertIn("occupied.task_key = ct.key", link_sql)
        self.assertIn("source_geom_hash", anchor_sql)
        self.assertIn("source_table", anchor_sql)

    def test_sync_to_field_skips_observed_and_closed(self) -> None:
        cur = MagicMock()
        cur.rowcount = 5
        cfg = SERVICE_TASK_SYNC["items_62501"]
        sent = _sync_tasks_to_field(cur, cfg)
        self.assertEqual(sent, 5)
        self.assertEqual(cur.execute.call_count, 4)
        insert_sql = cur.execute.call_args_list[0][0][0]
        rayon_sql = cur.execute.call_args_list[2][0][0]
        self.assertIn("INSERT INTO crm.tasks_field", insert_sql)
        self.assertIn("field_observed IS NOT TRUE", insert_sql)
        self.assertIn("NOT EXISTS", insert_sql)
        self.assertIn("crm.tasks_field", insert_sql)
        self.assertIn("crm.tasks_done_legal", insert_sql)
        self.assertIn("crm.tasks_done_illegal", insert_sql)
        self.assertIn("crm.tasks_clear", insert_sql)
        self.assertIn("ON CONFLICT (task_key) DO NOTHING", insert_sql)
        self.assertIn('ct."earthwork_id" IS NOT NULL', insert_sql)
        self.assertIn("odh_export.hood", rayon_sql)
        self.assertIn("UPDATE crm.tasks_field", rayon_sql)
        self.assertIn("data_mos.items_62501_points", rayon_sql)
        self.assertIn("data_mos.items_62501_lines", rayon_sql)
        self.assertIn("data_mos.items_62501_polygons", rayon_sql)
        self.assertIn("SAVEPOINT crm_task_field_rayon", cur.execute.call_args_list[1][0][0])

    def test_sync_runs_for_known_service(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        result = sync_crm_tasks_after_etl(cur, "items_2855")
        # 3 layers * (insert + link+anchor) + tasked + field insert + savepoint/rayon/release
        self.assertGreaterEqual(cur.execute.call_count, 10)
        self.assertEqual(result.sent_to_field, 1)
        field_sqls = [
            call.args[0]
            for call in cur.execute.call_args_list
            if isinstance(call.args[0], str) and "INSERT INTO crm.tasks_field" in call.args[0]
        ]
        self.assertEqual(len(field_sqls), 1)

    def test_sync_skips_unknown_service(self) -> None:
        cur = MagicMock()
        result = sync_crm_tasks_after_etl(cur, "items_99999")
        cur.execute.assert_not_called()
        self.assertEqual(result.inserted, 0)
        self.assertEqual(result.sent_to_field, 0)

    def test_sync_refreshes_tasked_bidirectionally(self) -> None:
        cur = MagicMock()
        cur.rowcount = 1
        with patch(
            "collector.crm_task_sync._sync_tasks_to_field", return_value=0
        ) as mock_field:
            sync_crm_tasks_after_etl(cur, "items_2855")
            mock_field.assert_called_once()
        tasked_sql = cur.execute.call_args_list[-1][0][0]
        self.assertIn("SET tasked = (", tasked_sql)
        self.assertNotIn("IS NOT TRUE", tasked_sql)


if __name__ == "__main__":
    unittest.main()
