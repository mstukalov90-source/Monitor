"""Tests for ogh_disruption_topotext job helpers."""

from __future__ import annotations

import inspect
import unittest

from collector.jobs import ogh_disruption_topotext_job as job


class KeywordFilterTests(unittest.TestCase):
    def test_ilike_patterns_wrap_keywords(self) -> None:
        self.assertIn("%РАЗР%", job.ILIKE_PATTERNS)
        self.assertIn("%НАВ.%", job.ILIKE_PATTERNS)
        self.assertIn("%ЯМА%", job.ILIKE_PATTERNS)
        self.assertIn("%РЕК-ЦИЯ%", job.ILIKE_PATTERNS)
        self.assertNotIn("РАЗР", job.ILIKE_PATTERNS)

    def test_razr_covers_abbrev_with_dot(self) -> None:
        self.assertTrue(any("РАЗР." in f"А {kw}" or kw == "РАЗР" for kw in job.TEXT_KEYWORDS))
        self.assertTrue("А РАЗР.".upper().find("РАЗР") >= 0)


class WatermarkModeTests(unittest.TestCase):
    def test_bootstrap_when_no_fid(self) -> None:
        self.assertTrue(job.is_bootstrap(0))
        self.assertTrue(job.is_bootstrap(-1))
        self.assertEqual(job.BOOTSTRAP_LIMIT, 50)

    def test_incremental_when_fid_present(self) -> None:
        self.assertFalse(job.is_bootstrap(1))
        self.assertFalse(job.is_bootstrap(6143287))

    def test_watermark_sql_scopes_to_own_filter_pass(self) -> None:
        self.assertEqual(job.FILTER_PASS, "topotext")
        source = inspect.getsource(job._last_source_fid)
        self.assertIn("WHERE filter_pass = %s", source)
        self.assertIn("FILTER_PASS", source)

    def test_remote_sql_bootstrap_orders_desc_with_limit(self) -> None:
        clause = job.remote_order_clause(limit=50)
        self.assertIn("ORDER BY fid DESC", clause.string)
        self.assertIn("LIMIT %s", clause.string)
        self.assertNotIn("ORDER BY fid ASC", clause.string)

    def test_remote_sql_incremental_orders_asc_no_limit(self) -> None:
        clause = job.remote_order_clause(limit=None)
        self.assertIn("ORDER BY fid ASC", clause.string)
        self.assertNotIn("LIMIT", clause.string)


class SkipRulesTests(unittest.TestCase):
    def test_normalize_number_strips_and_rejects_blank(self) -> None:
        self.assertEqual(job.normalize_number("  12/ОГХ-26/1  "), "12/ОГХ-26/1")
        self.assertIsNone(job.normalize_number("  "))
        self.assertIsNone(job.normalize_number(None))

    def test_normalize_label_strips(self) -> None:
        self.assertEqual(job.normalize_label("   М.С."), "М.С.")
        self.assertIsNone(job.normalize_label(""))
        self.assertIsNone(job.normalize_label(None))

    def test_row_is_complete_requires_all_fields(self) -> None:
        self.assertTrue(job.row_is_complete("М.С.", "12/ОГХ-26/1", b"ewkb"))
        self.assertFalse(job.row_is_complete(None, "12/ОГХ-26/1", b"ewkb"))
        self.assertFalse(job.row_is_complete("М.С.", None, b"ewkb"))
        self.assertFalse(job.row_is_complete("М.С.", "12/ОГХ-26/1", None))
        self.assertFalse(job.row_is_complete("М.С.", "12/ОГХ-26/1", b""))


if __name__ == "__main__":
    unittest.main()
