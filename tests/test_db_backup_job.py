"""Tests for the db_backup job (pg_dump invocation, naming, retention)."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from collector.jobs import db_backup_job


class FakeCompleted:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr


def _make_dump(path: Path, mtime: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dump")
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


class TakeBackupTests(unittest.TestCase):
    @patch.object(db_backup_job.subprocess, "run")
    def test_pg_dump_command_and_env(self, mock_run: MagicMock) -> None:
        def fake_run(cmd, env=None, **kwargs):
            Path(cmd[cmd.index("-f") + 1]).write_bytes(b"dump")
            return FakeCompleted()

        mock_run.side_effect = fake_run
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = db_backup_job.take_backup(
                db_backup_job.DAILY, Path(tmp), now=datetime(2026, 9, 23, 6, 30)
            )
        self.assertEqual(target.name, "monitor_20260923_0630.daily.dump")
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], "pg_dump")
        self.assertIn("-Fc", cmd)
        self.assertIn(str(target), cmd)
        env = mock_run.call_args.kwargs["env"]
        self.assertIn("PGPASSWORD", env)
        # password travels via env only, never as an argv element
        self.assertFalse(any("PGPASSWORD" in part for part in cmd))

    @patch.object(db_backup_job.subprocess, "run")
    def test_pg_dump_failure_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = FakeCompleted(returncode=1, stderr="boom")
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError) as ctx:
                db_backup_job.take_backup(
                    db_backup_job.DAILY, Path(tmp), now=datetime(2026, 9, 23, 6, 30)
                )
        self.assertIn("boom", str(ctx.exception))


class PruneBackupsTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_daily_prunes_older_than_one_day(self) -> None:
        now = datetime(2026, 9, 23, 6, 30)
        fresh = self.tmp / "monitor_20260923_0630.daily.dump"
        stale = self.tmp / "monitor_20260922_0630.daily.dump"
        _make_dump(fresh, now)
        _make_dump(stale, now - timedelta(days=1, hours=1))
        weekly = self.tmp / "monitor_20260918_0630.weekly.dump"
        _make_dump(weekly, now - timedelta(days=6))

        deleted = db_backup_job.prune_backups("daily", 1, self.tmp, now=now)

        self.assertEqual([p.name for p in deleted], [stale.name])
        self.assertTrue(fresh.exists())
        self.assertTrue(weekly.exists())  # other kind untouched

    def test_weekly_keeps_seven_days(self) -> None:
        now = datetime(2026, 9, 25, 6, 30)
        last_week = self.tmp / "monitor_20260918_0630.weekly.dump"
        this_week = self.tmp / "monitor_20260925_0630.weekly.dump"
        _make_dump(last_week, now - timedelta(days=7, hours=1))
        _make_dump(this_week, now)

        deleted = db_backup_job.prune_backups("weekly", 7, self.tmp, now=now)

        self.assertEqual([p.name for p in deleted], [last_week.name])
        self.assertTrue(this_week.exists())


class FridayLogicTests(unittest.TestCase):
    def test_friday_detection(self) -> None:
        # 2026-09-25 is a Friday; 2026-09-23 is a Wednesday.
        self.assertEqual(datetime(2026, 9, 25).weekday(), db_backup_job.FRIDAY)
        self.assertNotEqual(datetime(2026, 9, 23).weekday(), db_backup_job.FRIDAY)


if __name__ == "__main__":
    unittest.main()
