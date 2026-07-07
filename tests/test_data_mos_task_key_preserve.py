"""Tests for task_key preservation across data_mos ETL reload."""

from __future__ import annotations

from unittest.mock import MagicMock

from collector.data_mos_geom_split import (
    _restore_task_key_links,
    _save_task_key_links,
)


def test_save_and_restore_task_key_links_by_global_id_geom_hash():
    cur = MagicMock()
    task_key = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    global_id = 12345
    geom_hash = "abc123"
    old_id = 99

    cur.fetchall.return_value = [(task_key, global_id, geom_hash, old_id)]

    links = _save_task_key_links(cur, "data_mos.items_2855_lines")
    assert len(links) == 1

    cur.rowcount = 1
    restored = _restore_task_key_links(cur, "data_mos.items_2855_lines", links)
    assert restored == 1
    update_call = next(c for c in cur.execute.call_args_list if "UPDATE" in c[0][0])
    update_sql = update_call[0][0]
    update_params = update_call[0][1]
    assert "global_id" in update_sql
    assert "task_key" in update_sql
    assert "NOT EXISTS" in update_sql
    assert update_params == (task_key, global_id, geom_hash, task_key)


def test_restore_skips_when_task_key_already_occupied():
    cur = MagicMock()
    task_key = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    links = [
        (task_key, 111, "hash_a", 1),
        (task_key, 222, "hash_b", 2),
    ]
    rowcount_queue = [1, 0]

    def execute_side_effect(sql, params=None):
        if sql.strip().upper().startswith("UPDATE"):
            cur.rowcount = rowcount_queue.pop(0)
        elif sql.strip().upper().startswith("SELECT"):
            cur.fetchone.return_value = (1,)

    cur.execute.side_effect = execute_side_effect

    restored = _restore_task_key_links(cur, "data_mos.items_2855_points", links)
    assert restored == 1
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE" in c[0][0]]
    assert len(update_calls) == 2
    for call in update_calls:
        assert "NOT EXISTS" in call[0][0]
        assert call[0][1][-1] == task_key


def test_restore_sql_includes_not_exists_for_id_fallback():
    cur = MagicMock()
    task_key = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    links = [(task_key, None, None, 42)]

    cur.rowcount = 1
    restored = _restore_task_key_links(cur, "data_mos.items_2855_points", links)
    assert restored == 1
    update_sql = cur.execute.call_args_list[0][0][0]
    update_params = cur.execute.call_args_list[0][0][1]
    assert "WHERE id = %s" in update_sql
    assert "NOT EXISTS" in update_sql
    assert update_params == (task_key, 42, task_key)


def test_merge_load_uses_upsert_not_truncate():
    from collector.jobs import data_mos_job

    source = open(data_mos_job.__file__).read()
    assert "TRUNCATE TABLE" not in source
    assert "upsert_feature" in source
    assert "linked_before" in source


def test_geom_split_preserves_task_key_links():
    from collector.data_mos_geom_split import rebuild_geom_split

    source = open(rebuild_geom_split.__code__.co_filename).read()
    assert "TRUNCATE TABLE" not in source
    assert "_save_task_key_links" in source
    assert "_restore_task_key_links" in source
