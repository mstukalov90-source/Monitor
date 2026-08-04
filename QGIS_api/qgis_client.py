"""Minimal client for the MONITOR QGIS photo download API.

Only dependency: httpx  (pip install httpx)

Usage
-----
    from pathlib import Path
    from qgis_client import QgisPhotoClient

    with QgisPhotoClient(
        base_url="http://172.21.198.219:8000",
        api_key="your-256-bit-hex-key",
    ) as api:
        resp = api.get_genplan_photo("550e8400-e29b-41d4-a716-446655440000")
        resp.raise_for_status()
        Path("photo.jpg").write_bytes(resp.content)

        resp = api.get_field_photo("test_upload.jpg")
        resp.raise_for_status()
        Path("field.jpg").write_bytes(resp.content)

Test stand (SWEB): base_url="http://77.222.63.161:8000"
"""
from __future__ import annotations

import httpx


class QgisPhotoClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def get_genplan_photo(self, uuid: str) -> httpx.Response:
        """GET /api/qgis/photos/genplan/{uuid} — download genplan JPEG/PNG."""
        return self._http.get(
            f"/api/qgis/photos/genplan/{uuid}",
            headers={"Accept": "image/jpeg, image/png"},
        )

    def get_field_photo(self, filename: str) -> httpx.Response:
        """GET /api/qgis/photos/field/{filename} — download field JPEG/PNG."""
        return self._http.get(
            f"/api/qgis/photos/field/{filename}",
            headers={"Accept": "image/jpeg, image/png"},
        )

    def health(self) -> httpx.Response:
        return self._http.get("/health")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "QgisPhotoClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
