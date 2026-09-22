"""Client for the Vector GIST ORBISmap REST API (vector.mggt.ru)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


class OrbisMapApiError(RuntimeError):
    """Raised when the ORBISmap API returns an unexpected response."""


class OrbisMapClient:
    """Minimal ORBISmap REST client: session login + layer GeoJSON export.

    Login mints a session token (POST /login/, form-urlencoded ``login`` /
    ``password``); the server drops the session after 10 idle minutes, so the
    client re-logins on demand instead of caching tokens between runs.
    """

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        verify: bool = True,
        timeout: float = 600.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify = verify
        self.timeout = timeout
        self.session = session or requests.Session()
        self._token: Optional[str] = None

    def _login(self) -> str:
        response = self.session.post(
            f"{self.base_url}/login/",
            data={"login": self.username, "password": self.password},
            headers=_BROWSER_HEADERS,
            verify=self.verify,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise OrbisMapApiError(
                f"ORBISmap login failed: HTTP {response.status_code}: "
                f"{_body_preview(response)}"
            )
        try:
            token = response.json().get("token")
        except ValueError as exc:
            raise OrbisMapApiError(
                f"ORBISmap login returned non-JSON: {_body_preview(response)}"
            ) from exc
        if not token:
            raise OrbisMapApiError(
                f"ORBISmap login response has no token: {_body_preview(response)}"
            )
        self._token = str(token)
        return self._token

    def _get_with_token(self, url: str, params: dict[str, Any]) -> requests.Response:
        """GET with the session token; re-login once and retry on 401/403."""
        for attempt in (1, 2):
            if self._token is None:
                self._login()
            response = self.session.get(
                url,
                params={"token": self._token, **params},
                headers=_BROWSER_HEADERS,
                verify=self.verify,
                timeout=self.timeout,
            )
            if response.status_code in (401, 403) and attempt == 1:
                logger.info("ORBISmap session expired (HTTP %s) — re-login",
                            response.status_code)
                self._token = None
                continue
            return response
        return response  # pragma: no cover - loop always returns on attempt 2

    def fetch_layer_geojson(
        self,
        map_code: str,
        layer_code: str,
        *,
        geom_sr: int = 4326,
    ) -> dict:
        """Download a whole layer as a GeoJSON FeatureCollection dict."""
        url = f"{self.base_url}/{map_code}/layers/{layer_code}/export/"
        response = self._get_with_token(
            url, {"format": "geojson", "geomSR": geom_sr}
        )
        if response.status_code != 200:
            raise OrbisMapApiError(
                f"ORBISmap export {map_code}/{layer_code} failed: "
                f"HTTP {response.status_code}: {_body_preview(response)}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise OrbisMapApiError(
                f"ORBISmap export {map_code}/{layer_code} returned non-JSON: "
                f"{_body_preview(response)}"
            ) from exc
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            raise OrbisMapApiError(
                f"ORBISmap export {map_code}/{layer_code} is not a "
                f"FeatureCollection: {_body_preview(response)}"
            )
        return data


def _body_preview(response: requests.Response) -> str:
    return response.text[:500] if response.text else ""
