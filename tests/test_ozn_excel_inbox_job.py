"""Tests for ozn excel inbox job helpers."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from openpyxl import Workbook

from collector.jobs import ozn_excel_inbox_job as job


def _write_xlsx(path: Path, rows: list[tuple]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)


class ListReadyFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _touch(self, name: str, *, age: float) -> Path:
        path = self.tmp / name
        path.write_bytes(b"xlsx-placeholder")
        stamp = 1_700_000_000.0 - age
        os.utime(path, (stamp, stamp))
        return path

    def test_skips_temp_young_and_non_excel(self) -> None:
        ready = self._touch("ready.xlsx", age=10)
        self._touch("~$lock.xlsx", age=10)
        self._touch("upload.xlsx.tmp", age=10)
        self._touch("young.xlsx", age=0.5)
        self._touch("notes.txt", age=10)
        (self.tmp / "subdir").mkdir()

        found = job.list_ready_files(self.tmp, now=1_700_000_000.0)
        self.assertEqual(found, [ready])

    def test_missing_dir_is_empty(self) -> None:
        self.assertEqual(job.list_ready_files(self.tmp / "missing"), [])


class ParseExcelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_parses_rows_skips_bad_and_last_key_wins(self) -> None:
        path = self.tmp / "sample.xlsx"
        _write_xlsx(
            path,
            [
                ("№ Заказа", "Дата", "Исполнитель"),
                ("12/ОГХ-26/1", datetime(2026, 8, 5), "Слапик И. А."),
                ("12/ОГХ-26/2", "07.08.2026", "Жученко А. А."),
                ("12/ОГХ-26/1", datetime(2026, 8, 12), "Чуйкин М. А."),
                (None, datetime(2026, 8, 1), "X"),
                ("12/ОГХ-26/3", "bad-date", "Y"),
                ("12/ОГХ-26/4", datetime(2026, 8, 1), ""),
            ],
        )
        parsed = job.parse_excel(path)
        by_key = {row.order_no: row for row in parsed.rows}
        self.assertEqual(set(by_key), {"12/ОГХ-26/1", "12/ОГХ-26/2"})
        self.assertEqual(by_key["12/ОГХ-26/1"].ozn_date, date(2026, 8, 12))
        self.assertEqual(by_key["12/ОГХ-26/1"].executor, "Чуйкин М. А.")
        self.assertEqual(by_key["12/ОГХ-26/2"].ozn_date, date(2026, 8, 7))
        self.assertEqual(parsed.skipped_rows, 3)


class ProcessFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    @patch.object(job, "local_connection")
    @patch.object(job, "_ensure_tables")
    @patch.object(job, "_insert_log")
    def test_corrupt_file_logs_failed_and_deletes(
        self,
        mock_insert: MagicMock,
        _mock_ensure: MagicMock,
        mock_conn: MagicMock,
    ) -> None:
        path = self.tmp / "bad.xlsx"
        path.write_bytes(b"not-an-excel-file")
        conn = MagicMock()
        mock_conn.return_value.__enter__.return_value = conn
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        result = job.process_file(path)

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.error_message)
        self.assertFalse(path.exists())
        mock_insert.assert_called_once()
        self.assertEqual(mock_insert.call_args.kwargs["result"].status, "failed")


if __name__ == "__main__":
    unittest.main()
