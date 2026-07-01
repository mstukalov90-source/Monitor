"""Fetch GeoJSON layers from vector.mka.mos.ru."""

from __future__ import annotations

import json
import os

import requests

from collector.config import VECTOR_MKA_TOKEN_FILE, VECTOR_MKA_VERIFY_SSL

URL_221_EXPORT = (
    "https://vector.mka.mos.ru/api/2.8/orbis/map221/layers/rs_2022/export/"
    "?format=geojson&geomSR=3857&token={token}"
)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    "Connection": "keep-alive",
}

_FETCH_TIMEOUT_SECONDS = 600


def read_token() -> str | None:
    """Return token from VECTOR_MKA_TOKEN env or Vector_py/token.md."""
    env_token = os.getenv("VECTOR_MKA_TOKEN", "").strip()
    if env_token:
        return env_token

    if not VECTOR_MKA_TOKEN_FILE.is_file():
        return None

    token = VECTOR_MKA_TOKEN_FILE.read_text(encoding="utf-8").strip()
    return token or None


def fetch_url_221_geojson(token: str) -> dict:
    """Download map221/rs_2022 GeoJSON (EPSG:3857 in source)."""
    url = URL_221_EXPORT.format(token=token)
    response = requests.get(
        url,
        headers=_DEFAULT_HEADERS,
        verify=VECTOR_MKA_VERIFY_SSL,
        timeout=_FETCH_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        body_preview = response.text[:500] if response.text else ""
        raise RuntimeError(
            f"vector.mka url_221 export failed: HTTP {response.status_code}: {body_preview}"
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        body_preview = response.text[:500] if response.text else ""
        raise RuntimeError(
            f"vector.mka url_221 export returned non-JSON: {body_preview}"
        ) from exc
