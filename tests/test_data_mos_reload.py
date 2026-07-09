"""Tests for TRUNCATE-reload path on non-task data_mos services."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
from shapely.geometry import Point

from collector.config import DATA_MOS_EXPORT_BY_JOB
from collector.crm_task_sync_config import is_task_sync_parent


def _minimal_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"global_id": [1], "geometry": [Point(37.6, 55.7)]},
        crs="EPSG:4326",
    )


def test_is_task_sync_parent_classification():
    assert is_task_sync_parent("items_2855") is True
    assert is_task_sync_parent("items_62501") is True
    assert is_task_sync_parent("items_1500") is False
    assert is_task_sync_parent("items_2941") is False


@patch("collector.jobs.data_mos_job.local_connection")
@patch("collector.jobs.data_mos_job.gpd.read_file")
@patch("collector.jobs.data_mos_job.truncate_table")
@patch("collector.jobs.data_mos_job.reload_features")
@patch("collector.jobs.data_mos_job.purge_archived")
@patch("collector.jobs.data_mos_job.upsert_feature")
@patch("collector.jobs.data_mos_job.sync_crm_tasks_after_etl")
@patch("collector.jobs.data_mos_job.rebuild_geom_split")
@patch("collector.jobs.data_mos_job.derive_polygons_from_lines")
@patch("collector.jobs.data_mos_job.ensure_tasked_column")
def test_non_task_service_uses_truncate_reload(
    mock_ensure_tasked,
    mock_derive,
    mock_split,
    mock_crm_sync,
    mock_upsert,
    mock_purge,
    mock_reload,
    mock_truncate,
    mock_read_file,
    mock_conn,
    tmp_path: Path,
):
    from collector.jobs.data_mos_job import load_geojson_to_db

    geojson = tmp_path / "Data_mos_export_1500.geojson"
    geojson.write_text("{}")
    config = DATA_MOS_EXPORT_BY_JOB["data_mos_1500"]
    config = type(config)(
        service_id=config.service_id,
        script=config.script,
        geojson=geojson,
        gpkg=tmp_path / "Data_mos_export_1500.gpkg",
        table=config.table,
        job_name=config.job_name,
        purge_rule=config.purge_rule,
    )

    mock_read_file.return_value = _minimal_gdf()
    mock_reload.return_value = 1
    conn = MagicMock()
    mock_conn.return_value.__enter__.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    result = load_geojson_to_db(config)

    mock_truncate.assert_called_once_with(cur, "data_mos.items_1500")
    mock_reload.assert_called_once()
    mock_upsert.assert_not_called()
    mock_ensure_tasked.assert_not_called()
    mock_derive.assert_not_called()
    mock_split.assert_not_called()
    mock_crm_sync.assert_not_called()
    mock_purge.assert_not_called()
    assert result.truncated is True
    assert result.loaded == 1
    assert result.crm_sync is None


@patch("collector.jobs.data_mos_job.local_connection")
@patch("collector.jobs.data_mos_job.gpd.read_file")
@patch("collector.jobs.data_mos_job.truncate_table")
@patch("collector.jobs.data_mos_job.reload_features")
@patch("collector.jobs.data_mos_job.purge_archived")
@patch("collector.jobs.data_mos_job.upsert_feature")
@patch("collector.jobs.data_mos_job.sync_crm_tasks_after_etl")
@patch("collector.jobs.data_mos_job.rebuild_geom_split")
@patch("collector.jobs.data_mos_job.derive_polygons_from_lines")
@patch("collector.jobs.data_mos_job.ensure_tasked_column")
@patch("collector.jobs.data_mos_job._count_split_task_keys", return_value=0)
@patch("collector.jobs.data_mos_job._count_split_gap", return_value=0)
def test_task_service_uses_upsert_path(
    mock_gap,
    mock_task_keys,
    mock_ensure_tasked,
    mock_derive,
    mock_split,
    mock_crm_sync,
    mock_upsert,
    mock_purge,
    mock_reload,
    mock_truncate,
    mock_read_file,
    mock_conn,
    tmp_path: Path,
):
    from collector.crm_task_sync import CrmTaskSyncResult
    from collector.jobs.data_mos_job import load_geojson_to_db

    geojson = tmp_path / "Data_mos_export_2855.geojson"
    geojson.write_text("{}")
    base = DATA_MOS_EXPORT_BY_JOB["data_mos_2855"]
    config = type(base)(
        service_id=base.service_id,
        script=base.script,
        geojson=geojson,
        gpkg=tmp_path / "Data_mos_export_2855.gpkg",
        table=base.table,
        job_name=base.job_name,
        purge_rule=base.purge_rule,
    )

    mock_read_file.return_value = _minimal_gdf()
    mock_upsert.return_value = 42
    mock_crm_sync.return_value = CrmTaskSyncResult()
    conn = MagicMock()
    mock_conn.return_value.__enter__.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    result = load_geojson_to_db(config)

    mock_truncate.assert_not_called()
    mock_reload.assert_not_called()
    mock_upsert.assert_called()
    mock_ensure_tasked.assert_called_once()
    mock_derive.assert_called_once()
    mock_split.assert_called_once()
    mock_crm_sync.assert_called_once()
    assert result.truncated is False
    assert result.crm_sync is not None


@patch("collector.jobs.data_mos_job.local_connection")
@patch("collector.jobs.data_mos_job.gpd.read_file")
@patch("collector.jobs.data_mos_job.truncate_table")
@patch("collector.jobs.data_mos_job.reload_features")
@patch("collector.jobs.data_mos_job.purge_archived", return_value=3)
@patch("collector.jobs.data_mos_job.upsert_feature")
def test_2941_reload_runs_purge_after_insert(
    mock_upsert,
    mock_purge,
    mock_reload,
    mock_truncate,
    mock_read_file,
    mock_conn,
    tmp_path: Path,
):
    from collector.jobs.data_mos_job import load_geojson_to_db

    geojson = tmp_path / "Data_mos_export_2941.geojson"
    geojson.write_text("{}")
    base = DATA_MOS_EXPORT_BY_JOB["data_mos_2941"]
    config = type(base)(
        service_id=base.service_id,
        script=base.script,
        geojson=geojson,
        gpkg=tmp_path / "Data_mos_export_2941.gpkg",
        table=base.table,
        job_name=base.job_name,
        purge_rule=base.purge_rule,
    )

    mock_read_file.return_value = _minimal_gdf()
    mock_reload.return_value = 2
    conn = MagicMock()
    mock_conn.return_value.__enter__.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    result = load_geojson_to_db(config)

    mock_truncate.assert_called_once()
    mock_reload.assert_called_once()
    mock_purge.assert_called_once_with(cur, "data_mos.items_2941", base.purge_rule)
    assert result.purged == 3
    assert result.truncated is True
