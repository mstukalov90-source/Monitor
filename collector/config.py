"""Configuration from environment variables."""

import os
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

DATA_MOS_EXPORT_SCRIPT = PROJECT_DIR / "data_mos_export.py"
DATA_MOS_GEOJSON = PROJECT_DIR / "Data_mos_export.geojson"
DATA_MOS_GPKG = PROJECT_DIR / "Data_mos_export.gpkg"

TZ = os.getenv("TZ", "Europe/Moscow")
