"""Configuration from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "/app"))

OGH_DISRUPTION_GEOJSON = PROJECT_DIR / "mggt_dgn" / "mggt_dgn.geojson"

GENPLAN_JSON_DIR = PROJECT_DIR / "jsons_genplan"
GENPLAN_SAMPLE_FILES = frozenset({
    "order.json",
    "photo_meta.json",
    "upload.json",
    "uuid_area.json",
})

LOCAL_DB = {
    "host": os.getenv("LOCAL_DB_HOST", "localhost"),
    "port": int(os.getenv("LOCAL_DB_PORT", "5432")),
    "dbname": os.getenv("LOCAL_DB_NAME", os.getenv("POSTGRES_DB", "monitor")),
    "user": os.getenv("LOCAL_DB_USER", os.getenv("POSTGRES_USER", "monitor")),
    "password": os.getenv("LOCAL_DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "monitor")),
}

REMOTE_DB = {
    "host": os.getenv("REMOTE_DB_HOST", "172.16.206.170"),
    "port": int(os.getenv("REMOTE_DB_PORT", "5432")),
    "dbname": os.getenv("REMOTE_DB_NAME", "sps"),
    "user": os.getenv("REMOTE_DB_USER", "asidorov"),
    "password": os.getenv("REMOTE_DB_PASSWORD", "qwerty1234"),
}

WEB_GEO_DB = {
    "host": os.getenv("WEB_GEO_DB_HOST", "172.21.198.149"),
    "port": int(os.getenv("WEB_GEO_DB_PORT", "5432")),
    "dbname": os.getenv("WEB_GEO_DB_NAME", "web_geo"),
    "user": os.getenv("WEB_GEO_DB_USER", "asidorov"),
    "password": os.getenv("WEB_GEO_DB_PASSWORD", ""),
}

STROYMONITORING_REMOTE_SCHEMA = "public"
STROYMONITORING_REMOTE_TABLE = "boundaries_aip"
STROYMONITORING_LOCAL_SCHEMA = "stroymonitoring"
STROYMONITORING_LOCAL_TABLE = "boundaries_aip"

TZ = os.getenv("TZ", "Europe/Moscow")

PurgeRuleKind = Literal["date_on_or_before_month_ago", "year_before_current"]


@dataclass(frozen=True)
class DataMosPurgeRule:
    column: str
    kind: PurgeRuleKind


@dataclass(frozen=True)
class DataMosExportConfig:
    service_id: int
    script: Path
    geojson: Path
    gpkg: Path
    table: str
    job_name: str
    purge_rule: Optional[DataMosPurgeRule] = None


def _data_mos_export(
    service_id: int,
    purge_rule: Optional[DataMosPurgeRule] = None,
) -> DataMosExportConfig:
    prefix = f"Data_mos_export_{service_id}"
    return DataMosExportConfig(
        service_id=service_id,
        script=PROJECT_DIR / f"data_mos_export_{service_id}.py",
        geojson=PROJECT_DIR / f"{prefix}.geojson",
        gpkg=PROJECT_DIR / f"{prefix}.gpkg",
        table=f"items_{service_id}",
        job_name=f"data_mos_{service_id}",
        purge_rule=purge_rule,
    )


_DATE_PURGE = DataMosPurgeRule("work_end_date", "date_on_or_before_month_ago")
_ACTUAL_END_DATE_PURGE = DataMosPurgeRule(
    "actual_end_date", "date_on_or_before_month_ago"
)
_YEAR_PURGE = DataMosPurgeRule(
    "plan_year_construction_complete", "year_before_current"
)

DATA_MOS_EXPORTS: tuple[DataMosExportConfig, ...] = (
    _data_mos_export(2855, _DATE_PURGE),
    _data_mos_export(2941, _YEAR_PURGE),
    _data_mos_export(62461, _DATE_PURGE),
    _data_mos_export(62501, _DATE_PURGE),
    _data_mos_export(1498),
    _data_mos_export(1500),
    _data_mos_export(2386),
    _data_mos_export(62441, _ACTUAL_END_DATE_PURGE),
)

DATA_MOS_EXPORT_BY_JOB: dict[str, DataMosExportConfig] = {
    cfg.job_name: cfg for cfg in DATA_MOS_EXPORTS
}

DATA_MOS_TABLES_SQL = PROJECT_DIR / "sql" / "04_data_mos_dynamic_tables.sql"
DATA_MOS_PURGE_FUNCTIONS_SQL = PROJECT_DIR / "sql" / "05_data_mos_purge_functions.sql"
DATA_MOS_LINE_TO_POLYGON_SQL = PROJECT_DIR / "sql" / "07_line_to_polygon.sql"
DATA_MOS_GEOM_SPLIT_SQL = PROJECT_DIR / "sql" / "09_data_mos_geom_split.sql"
