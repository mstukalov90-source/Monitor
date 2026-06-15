"""Configuration from environment variables."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "/app"))

OGH_DISRUPTION_GEOJSON = PROJECT_DIR / "mggt_dgn" / "mggt_dgn.geojson"

GENPLAN_API_DIR = PROJECT_DIR / "genplan api"
GENPLAN_JSON_DIR = PROJECT_DIR / "jsons_genplan"
GENPLAN_SAMPLE_FILES = frozenset({
    "order.json",
    "photo_meta.json",
    "upload.json",
    "uuid_area.json",
})
MSI_HOLES_CREDENTIALS_FILE = GENPLAN_API_DIR / "msi-holes-backend.client.json"


def _msi_holes_settings() -> tuple[str, str, str, str]:
    """Env vars first; fall back to genplan api/msi-holes-backend.client.json."""
    client_id = os.getenv("MSI_HOLES_CLIENT_ID", "")
    client_secret = os.getenv("MSI_HOLES_CLIENT_SECRET", "")
    base_url = os.getenv("MSI_HOLES_BASE_URL", "https://m2m.msi-holes.cxm.dev")
    token_endpoint = os.getenv(
        "MSI_HOLES_TOKEN_ENDPOINT", "https://id.cxm.dev/oauth2/token"
    )
    if (not client_id or not client_secret) and MSI_HOLES_CREDENTIALS_FILE.is_file():
        data = json.loads(MSI_HOLES_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        client_id = client_id or str(data.get("client_id", ""))
        client_secret = client_secret or str(data.get("client_secret", ""))
        if not os.getenv("MSI_HOLES_TOKEN_ENDPOINT"):
            token_endpoint = str(data.get("token_endpoint", token_endpoint))
        if not os.getenv("MSI_HOLES_BASE_URL") and data.get("base_url"):
            base_url = str(data["base_url"])
    return client_id, client_secret, base_url, token_endpoint


MSI_HOLES_CLIENT_ID, MSI_HOLES_CLIENT_SECRET, MSI_HOLES_BASE_URL, MSI_HOLES_TOKEN_ENDPOINT = (
    _msi_holes_settings()
)
GENPLAN_SEARCH_LAT = float(os.getenv("GENPLAN_SEARCH_LAT", "55.7558"))
GENPLAN_SEARCH_LNG = float(os.getenv("GENPLAN_SEARCH_LNG", "37.6173"))
GENPLAN_SEARCH_RADIUS_M = int(os.getenv("GENPLAN_SEARCH_RADIUS_M", "1000"))
# 0 = no limit; set e.g. 20 for local smoke tests
GENPLAN_FETCH_META_LIMIT = int(os.getenv("GENPLAN_FETCH_META_LIMIT", "0"))
GENPLAN_PHOTO_UPLOAD_DIR = PROJECT_DIR / "photo_to_upload"
GENPLAN_PHOTO_UPLOADED_DIR = PROJECT_DIR / "photo_uploaded"

MONITOR_API_PORT = int(os.getenv("MONITOR_API_PORT", "8000"))
MONITOR_API_PUBLIC_BASE_URL = os.getenv(
    "MONITOR_API_PUBLIC_BASE_URL", "http://77.222.63.161:8000"
)


def _monitor_api_keys() -> frozenset[str]:
    keys: list[str] = []
    single = os.getenv("MONITOR_API_KEY", "").strip()
    if single:
        keys.append(single)
    multi = os.getenv("MONITOR_API_KEYS", "")
    if multi:
        keys.extend(part.strip() for part in multi.split(",") if part.strip())
    return frozenset(keys)


MONITOR_API_KEYS = _monitor_api_keys()

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
LENS_STROYMONITORING_PURGE_FUNCTIONS_SQL = (
    PROJECT_DIR / "sql" / "14_lens_stroymonitoring_purge_functions.sql"
)
DATA_MOS_LINE_TO_POLYGON_SQL = PROJECT_DIR / "sql" / "07_line_to_polygon.sql"
DATA_MOS_GEOM_SPLIT_SQL = PROJECT_DIR / "sql" / "09_data_mos_geom_split.sql"
