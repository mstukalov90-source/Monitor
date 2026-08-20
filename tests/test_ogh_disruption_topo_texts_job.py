"""Tests for ogh_disruption_topo_texts job helpers."""

from __future__ import annotations

import unittest

from psycopg2 import sql

from collector.jobs import ogh_disruption_topo_texts_job as job


def _sql_text(obj) -> str:
    if isinstance(obj, sql.Composed):
        return "".join(_sql_text(part) for part in obj)
    if isinstance(obj, sql.SQL):
        return obj.string
    if isinstance(obj, sql.Identifier):
        return ".".join(obj.strings)
    return str(obj)


class LabelFilterTests(unittest.TestCase):
    def test_exact_label_list(self) -> None:
        expected = (
            "РАЗР",
            "НАВАЛ",
            "РАЗР.",
            "НАВ.",
            "ЗАВАЛ",
            "ЗАВАЛЕНО",
            "ЗАВ.",
            "М.С.",
            "ЗЕМЛ.РАБ.",
            "ИЗРЫТО",
            "РЕКОНСТРУКЦИЯ",
            "РЕКОНСТР.",
            "РЕК-ЦИЯ",
            "ЯМА",
        )
        self.assertEqual(job.LABEL_VALUES, expected)

    def test_remote_sql_uses_exact_match_not_ilike(self) -> None:
        compiled = job.remote_select_sql(last_fid=0, limit=50)
        text = _sql_text(compiled)
        self.assertIn("btrim", text)
        self.assertIn("= ANY(%s)", text)
        self.assertNotIn("ILIKE", text)


class WatermarkModeTests(unittest.TestCase):
    def test_bootstrap_when_no_fid(self) -> None:
        self.assertTrue(job.is_bootstrap(0))
        self.assertTrue(job.is_bootstrap(-1))
        self.assertEqual(job.BOOTSTRAP_LIMIT, 50)
        self.assertEqual(job.FILTER_PASS, "topo_texts")

    def test_incremental_when_fid_present(self) -> None:
        self.assertFalse(job.is_bootstrap(1))
        self.assertFalse(job.is_bootstrap(104673))

    def test_remote_sql_bootstrap_orders_desc_with_limit(self) -> None:
        clause = job.remote_order_clause(limit=50)
        self.assertIn("ORDER BY fid DESC", clause.string)
        self.assertIn("LIMIT %s", clause.string)
        self.assertNotIn("ORDER BY fid ASC", clause.string)

    def test_remote_sql_incremental_orders_asc_no_limit(self) -> None:
        clause = job.remote_order_clause(limit=None)
        self.assertIn("ORDER BY fid ASC", clause.string)
        self.assertNotIn("LIMIT", clause.string)

    def test_remote_sql_targets_t500_topo_texts(self) -> None:
        compiled = job.remote_select_sql(last_fid=0, limit=50)
        text = _sql_text(compiled)
        self.assertIn("t500", text)
        self.assertIn("topo_texts", text)
        self.assertIn("label", text)
        self.assertIn("base_name", text)
        self.assertIn("geom", text)
        self.assertNotIn("topopassport", text)


class SkipRulesTests(unittest.TestCase):
    def test_normalize_text_strips_and_rejects_blank(self) -> None:
        self.assertEqual(job.normalize_text("  12/ОГХ-26/1  "), "12/ОГХ-26/1")
        self.assertEqual(job.normalize_text("   М.С."), "М.С.")
        self.assertIsNone(job.normalize_text("  "))
        self.assertIsNone(job.normalize_text(""))
        self.assertIsNone(job.normalize_text(None))

    def test_row_is_complete_requires_all_fields(self) -> None:
        self.assertTrue(job.row_is_complete("М.С.", "12/ОГХ-26/1", b"ewkb"))
        self.assertFalse(job.row_is_complete(None, "12/ОГХ-26/1", b"ewkb"))
        self.assertFalse(job.row_is_complete("М.С.", None, b"ewkb"))
        self.assertFalse(job.row_is_complete("М.С.", "12/ОГХ-26/1", None))
        self.assertFalse(job.row_is_complete("М.С.", "12/ОГХ-26/1", b""))


if __name__ == "__main__":
    unittest.main()
