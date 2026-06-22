"""Minimal client for the MONITOR M2M photo meta ingest API.

Only dependency: httpx  (pip install httpx)

Usage
-----
    from monitor_client import MonitorClient

    with MonitorClient(
        base_url="http://77.222.63.161:8000",
        api_key="your-256-bit-hex-key",
    ) as api:
        payload = {
            "status": "done",
            "lat": 55.78418187985141,
            "lng": 37.74234417284182,
            "image_name": "photo.jpg",
        }
        resp = api.put_photo_meta("550e8400-e29b-41d4-a716-446655440000", payload)
        resp.raise_for_status()
        print(resp.json())
"""
from __future__ import annotations

import httpx


class MonitorClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def put_photo_meta(self, uuid: str, payload: dict) -> httpx.Response:
        """PUT /api/photos/meta/{uuid} — create or update photo metadata."""
        body = dict(payload)
        body["uuid"] = uuid
        return self._http.put(
            f"/api/photos/meta/{uuid}",
            json=body,
            headers={"Accept": "application/json"},
        )

    def put_uuid(self, uuid: str) -> httpx.Response:
        """PUT /api/uuids/{uuid} — register photo uuid (insert-only)."""
        return self._http.put(
            f"/api/uuids/{uuid}",
            headers={"Accept": "application/json"},
        )

    def health(self) -> httpx.Response:
        return self._http.get("/health")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MonitorClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
