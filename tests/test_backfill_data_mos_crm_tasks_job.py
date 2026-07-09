"""Tests for data_mos CRM task backfill job."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from collector.crm_task_sync import CrmTaskSyncResult
from collector.jobs import backfill_data_mos_crm_tasks_job as job


class BackfillDataMosCrmTasksJobTests(unittest.TestCase):
    @patch.object(job, "log_job_run", return_value=1)
    @patch.object(job, "local_connection")
    @patch.object(job, "sync_crm_tasks_after_etl")
    @patch.object(job, "refresh_all_tasked_parents")
    def test_run_syncs_all_services_in_order(
        self,
        mock_refresh: MagicMock,
        mock_sync: MagicMock,
        mock_conn: MagicMock,
        _mock_log: MagicMock,
    ) -> None:
        mock_sync.return_value = CrmTaskSyncResult(inserted=2, linked=2, tasked_parents=1)
        conn = MagicMock()
        mock_conn.return_value.__enter__.return_value = conn
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        job.run()

        self.assertEqual(mock_sync.call_count, 4)
        called_services = [call.args[1] for call in mock_sync.call_args_list]
        self.assertEqual(
            called_services,
            ["items_62501", "items_62441", "items_62461", "items_2855"],
        )
        self.assertEqual(mock_refresh.call_count, 4)


if __name__ == "__main__":
    unittest.main()
