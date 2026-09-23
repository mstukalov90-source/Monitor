"""Tests for table_sync column alignment (remote schema drift protection)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from psycopg2 import sql

from collector import table_sync


def _col(name: str, udt: str = "text") -> dict:
    return {
        "column_name": name,
        "data_type": "text" if udt != "geometry" else "USER-DEFINED",
        "udt_name": udt,
    }


def _render(composed: sql.Composed) -> str:
    """Render psycopg2 Composed without a live connection."""
    parts = []
    for part in composed.seq:
        if isinstance(part, sql.SQL):
            parts.append(part.string)
        elif isinstance(part, sql.Identifier):
            parts.append(".".join(f'"{s}"' for s in part.strings))
    return "".join(parts)


class AlignColumnsTests(unittest.TestCase):
    def test_adds_missing_remote_columns(self) -> None:
        local_conn = MagicMock()
        with patch.object(table_sync, "get_table_columns", return_value=[_col("id", "int4")]):
            added = table_sync.align_columns(
                local_conn, "stroymonitoring", "boundaries_aip",
                [_col("id", "int4"), _col("aip_inclusion_date"), _col("geom", "geometry")],
            )
        self.assertEqual(added, ["aip_inclusion_date", "geom"])
        cur = local_conn.cursor.return_value.__enter__.return_value
        executed = [_render(call[0][0]) for call in cur.execute.call_args_list]
        self.assertTrue(
            any(
                'ALTER TABLE "stroymonitoring"."boundaries_aip" '
                'ADD COLUMN IF NOT EXISTS "aip_inclusion_date" text' in s
                for s in executed
            ),
            executed,
        )
        self.assertTrue(
            any('ADD COLUMN IF NOT EXISTS "geom" geometry(Geometry, 4326)' in s for s in executed),
            executed,
        )

    def test_noop_when_local_has_all_columns(self) -> None:
        local_conn = MagicMock()
        with patch.object(
            table_sync, "get_table_columns",
            return_value=[_col("id", "int4"), _col("status")],
        ):
            added = table_sync.align_columns(
                local_conn, "s", "t", [_col("id", "int4"), _col("status")]
            )
        self.assertEqual(added, [])
        local_conn.cursor.return_value.__enter__.return_value.execute.assert_not_called()

    def test_sync_table_calls_align_after_ensure(self) -> None:
        remote_conn = MagicMock()
        local_conn = MagicMock()
        remote_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [(1, "x")]
        columns = [_col("id", "int4"), _col("status")]
        with patch.object(table_sync, "get_table_columns", return_value=columns), \
                patch.object(table_sync, "ensure_table") as ensure_mock, \
                patch.object(table_sync, "align_columns", return_value=[]) as align_mock:
            rows = table_sync.sync_table(remote_conn, local_conn, "public", "src", "loc", "dst")
        self.assertEqual(rows, 1)
        ensure_mock.assert_called_once()
        align_mock.assert_called_once_with(local_conn, "loc", "dst", columns)


if __name__ == "__main__":
    unittest.main()
