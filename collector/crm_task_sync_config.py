"""CRM task sync mapping for data_mos split tables (scoped geometry subgroups)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SplitLayerSync:
    items_table: str
    geom_type: str  # point | line | polygon


@dataclass(frozen=True)
class ServiceTaskSync:
    parent_table: str
    group_name: str
    task_column: str
    split_layers: tuple[SplitLayerSync, ...]


ETL_SYNC_LOGIN = "etl"

SERVICE_TASK_SYNC: dict[str, ServiceTaskSync] = {
    "items_2855": ServiceTaskSync(
        parent_table="data_mos.items_2855",
        group_name="Новые ордера ОАТИ, АВР и земляные работы",
        task_column="oati_id",
        split_layers=(
            SplitLayerSync("data_mos.items_2855_points", "point"),
            SplitLayerSync("data_mos.items_2855_lines", "line"),
            SplitLayerSync("data_mos.items_2855_polygons", "polygon"),
        ),
    ),
    "items_62501": ServiceTaskSync(
        parent_table="data_mos.items_62501",
        group_name="Новые ордера ОАТИ, АВР и земляные работы",
        task_column="earthwork_id",
        split_layers=(
            SplitLayerSync("data_mos.items_62501_points", "point"),
            SplitLayerSync("data_mos.items_62501_lines", "line"),
            SplitLayerSync("data_mos.items_62501_polygons", "polygon"),
        ),
    ),
    "items_62441": ServiceTaskSync(
        parent_table="data_mos.items_62441",
        group_name="Новые ордера ОАТИ, АВР и земляные работы",
        task_column="localwork_id",
        split_layers=(
            SplitLayerSync("data_mos.items_62441_points", "point"),
            SplitLayerSync("data_mos.items_62441_lines", "line"),
            SplitLayerSync("data_mos.items_62441_polygons", "polygon"),
        ),
    ),
    "items_62461": ServiceTaskSync(
        parent_table="data_mos.items_62461",
        group_name="Новые ордера ОАТИ, АВР и земляные работы",
        task_column="avr_mos_id",
        split_layers=(
            SplitLayerSync("data_mos.items_62461_points", "point"),
            SplitLayerSync("data_mos.items_62461_lines", "line"),
            SplitLayerSync("data_mos.items_62461_polygons", "polygon"),
        ),
    ),
}

TASK_ID_COLUMNS = (
    "photo_uuid",
    "photo_lens",
    "ogh_id",
    "oati_id",
    "earthwork_id",
    "localwork_id",
    "avr_mos_id",
)
