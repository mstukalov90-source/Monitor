"""Configuration from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "/app"))

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

TZ = os.getenv("TZ", "Europe/Moscow")


@dataclass(frozen=True)
class DataMosExportConfig:
    service_id: int
    script: Path
    geojson: Path
    gpkg: Path
    table: str
    job_name: str


def _data_mos_export(service_id: int) -> DataMosExportConfig:
    prefix = f"Data_mos_export_{service_id}"
    return DataMosExportConfig(
        service_id=service_id,
        script=PROJECT_DIR / f"data_mos_export_{service_id}.py",
        geojson=PROJECT_DIR / f"{prefix}.geojson",
        gpkg=PROJECT_DIR / f"{prefix}.gpkg",
        table=f"items_{service_id}",
        job_name=f"data_mos_{service_id}",
    )


DATA_MOS_EXPORTS: tuple[DataMosExportConfig, ...] = (
    _data_mos_export(2855),
    _data_mos_export(2941),
    _data_mos_export(62461),
    _data_mos_export(62501),
)

DATA_MOS_EXPORT_BY_JOB: dict[str, DataMosExportConfig] = {
    cfg.job_name: cfg for cfg in DATA_MOS_EXPORTS
}

DATA_MOS_TABLES_SQL = PROJECT_DIR / "sql" / "04_data_mos_dynamic_tables.sql"
