"""Tests for data_mos geometry split helpers."""

from __future__ import annotations

import unittest

from collector.data_mos_geom_split import (
    SPLIT_SOURCE_TABLES,
    _ALL_ROUTED_TYPES,
    _GEOMETRY_COLLECTION_TYPE,
    _LINE_TYPES,
    _POINT_TYPES,
    _POLYGON_TYPES,
    _collection_parts_lateral_sql,
    _insert_routed,
    collection_insert_sql_fragment,
    _valid_geom_expr,
    _valid_geom_filter,
    qualified_split_names,
)
from collector.data_mos_tasked import tasked_child_delete_guard
from unittest.mock import MagicMock


class QualifiedSplitNamesTests(unittest.TestCase):
    def test_names_for_service_table(self) -> None:
        points, lines, polygons = qualified_split_names("data_mos.items_2855")
        self.assertEqual(points, "data_mos.items_2855_points")
        self.assertEqual(lines, "data_mos.items_2855_lines")
        self.assertEqual(polygons, "data_mos.items_2855_polygons")

    def test_split_sources_cover_four_services(self) -> None:
        self.assertEqual(
            SPLIT_SOURCE_TABLES,
            frozenset({
                "items_2855",
                "items_62441",
                "items_62461",
                "items_62501",
            }),
        )


class GeometryTypeFilterTests(unittest.TestCase):
    def test_families_are_disjoint(self) -> None:
        self.assertFalse(set(_POINT_TYPES) & set(_LINE_TYPES))
        self.assertFalse(set(_LINE_TYPES) & set(_POLYGON_TYPES))
        self.assertFalse(set(_POINT_TYPES) & set(_POLYGON_TYPES))

    def test_all_routed_union(self) -> None:
        self.assertEqual(
            _ALL_ROUTED_TYPES,
            _POINT_TYPES + _LINE_TYPES + _POLYGON_TYPES,
        )

    def test_valid_geom_sql_uses_make_valid(self) -> None:
        self.assertIn("ST_MakeValid", _valid_geom_expr())
        self.assertIn("ST_MakeValid", _valid_geom_filter())
        self.assertIn("ST_IsEmpty", _valid_geom_filter())


class GeometryCollectionSqlTests(unittest.TestCase):
    def test_collection_lateral_uses_st_dump(self) -> None:
        sql = _collection_parts_lateral_sql("src.geom")
        self.assertIn(collection_insert_sql_fragment(), sql)
        self.assertIn(_GEOMETRY_COLLECTION_TYPE, sql)
        self.assertIn("UNION ALL", sql)


class TaskedGuardTests(unittest.TestCase):
    def test_delete_guard_protects_tasked_parent_children(self) -> None:
        guard = tasked_child_delete_guard("data_mos.items_2855", "t")
        self.assertIn("p.tasked IS TRUE", guard)
        self.assertIn("t.source_id", guard)

    def test_insert_routed_skips_tasked_parents(self) -> None:
        cur = MagicMock()
        cur.rowcount = 0
        _insert_routed(
            cur,
            "data_mos.items_2855",
            "data_mos.items_2855_points",
            ["global_id"],
            _POINT_TYPES,
        )
        sql = cur.execute.call_args[0][0]
        self.assertIn("src.tasked IS NOT TRUE", sql)
        self.assertIn("FROM data_mos.items_2855 AS src", sql)


if __name__ == "__main__":
    unittest.main()
