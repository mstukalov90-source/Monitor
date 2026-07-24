"""Memory-safe streaming load from data.mos.ru API into data_mos.items_*."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterator
import warnings

import geopandas as gpd
import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

from collector.config import DataMosExportConfig
from collector.data_mos_schema import (
    collect_schema,
    ensure_base_table,
    ensure_columns,
    extract_feature_properties,
    insert_feature,
    truncate_table,
)
from collector.db import local_connection

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

_BASE_URL = "https://apidata.mos.ru/v1/datasets"
_PAGE_SIZE = 500
_COMMIT_EVERY_PAGES = 5


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = False
    return session


def _api_key() -> str | None:
    return os.getenv("DATA_MOS_API_KEY") or None


def _extract_features(payload: Any) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("features", "data", "Items"):
            if key in payload and isinstance(payload[key], list):
                return payload[key]
    if isinstance(payload, list):
        return payload
    return []


def _iter_feature_pages(service_id: int, page_size: int = _PAGE_SIZE) -> Iterator[list[dict]]:
    """Yield GeoJSON Feature pages sequentially (API requires $skip >= 1)."""
    url = f"{_BASE_URL}/{service_id}/features"
    key = _api_key()
    skip = 1
    with _session() as session:
        while True:
            params: dict[str, Any] = {"$skip": skip, "$top": page_size}
            if key:
                params["api_key"] = key
            response = session.get(url, params=params, timeout=120)
            response.raise_for_status()
            features = _extract_features(response.json())
            if not features:
                return
            yield features
            if len(features) < page_size:
                return
            skip += page_size


def _insert_gdf(cur, qualified: str, schema: dict[str, str], gdf: gpd.GeoDataFrame) -> int:
    count = 0
    for _, row in gdf.iterrows():
        props = extract_feature_properties(row)
        geom_json = None
        if row.geometry is not None and not row.geometry.is_empty:
            geom_json = json.dumps(row.geometry.__geo_interface__)
        insert_feature(cur, qualified, schema, props, geom_json)
        count += 1
    return count


def stream_load_to_db(config: DataMosExportConfig) -> int:
    """TRUNCATE once, then page API → insert without keeping the full dataset in RAM."""
    table = config.table
    qualified = f"data_mos.{table}"
    schema: dict[str, str] = {}
    loaded = 0
    pages = 0

    with local_connection() as conn:
        with conn.cursor() as cur:
            ensure_base_table(cur, qualified)
            truncate_table(cur, qualified)
            conn.commit()
            logger.info("Truncated %s for stream load (service %s)", qualified, config.service_id)

            for features in _iter_feature_pages(config.service_id):
                pages += 1
                gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
                if gdf.empty:
                    continue
                if gdf.crs is None:
                    gdf = gdf.set_crs("EPSG:4326")
                else:
                    gdf = gdf.to_crs("EPSG:4326")

                page_schema = collect_schema(gdf)
                new_cols = {k: v for k, v in page_schema.items() if k not in schema}
                if new_cols:
                    schema.update(new_cols)
                    ensure_columns(cur, qualified, schema)

                loaded += _insert_gdf(cur, qualified, schema, gdf)
                if pages % _COMMIT_EVERY_PAGES == 0:
                    conn.commit()
                    logger.info(
                        "Stream load %s: %s features (%s pages)",
                        config.service_id,
                        loaded,
                        pages,
                    )

            conn.commit()

    logger.info(
        "Stream load finished for service %s: %s features, %s pages, %s columns",
        config.service_id,
        loaded,
        pages,
        len(schema),
    )
    return loaded
