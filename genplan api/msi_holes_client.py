"""Minimal client for the msi-holes M2M API.

Handles the OAuth2 client_credentials token automatically: mints on first use,
caches it, transparently re-mints shortly before expiry and once on a 401. The
caller never touches tokens.

Only dependency: httpx  (pip install httpx)

Usage
-----
    from msi_holes_client import MsiHolesClient

    # credentials JSON is the file create_service_client.py emitted
    with MsiHolesClient.from_file("msi-holes-backend.client.json") as api:
        r = api.get("/some/path")
        r.raise_for_status()          # API calls return the raw response; you raise
        data = r.json()

        api.post("/things", json={"name": "x"}).raise_for_status()

Contract / notes
----------------
- API methods (get/post/...) return the raw ``httpx.Response`` and do NOT raise on
  HTTP errors — call ``resp.raise_for_status()`` yourself. Only token minting and
  malformed input raise automatically.
- The instance is thread-safe and reuses one connection pool: create it once and
  share it. Tokens live ~15 min; this reuses one until it is about to expire — do
  NOT mint per request (each mint is a write in Hydra's DB).
- ``url`` may be a path (joined onto base_url) or an absolute URL whose origin
  equals base_url. An absolute URL to a different origin is refused so the bearer
  token can't be sent elsewhere. Caller headers are kept, but the client always
  sets Authorization itself.
- The automatic 401 re-mint replays the request, so it is skipped for one-shot
  bodies (``files=`` or a streaming ``content=``); pass ``json=`` or ``bytes``.
- Sync only. For network retries/backoff pass
  ``transport=httpx.HTTPTransport(retries=N)``; the 401 re-mint here is auth-only.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://m2m.msi-holes.cxm.dev"
DEFAULT_TOKEN_ENDPOINT = "https://id.cxm.dev/oauth2/token"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class MsiHolesClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_endpoint: str = DEFAULT_TOKEN_ENDPOINT,
        base_url: str = DEFAULT_BASE_URL,
        skew_seconds: float = 60.0,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,  # for tests / custom retries
    ) -> None:
        token_url = httpx.URL(token_endpoint)
        if token_url.scheme != "https" and token_url.host not in _LOCAL_HOSTS:
            raise ValueError(f"token_endpoint must be https (the client_secret is sent there): {token_endpoint}")
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_endpoint = token_endpoint
        self._skew = skew_seconds
        self._base = httpx.URL(base_url.rstrip("/"))
        self._http = httpx.Client(base_url=self._base, timeout=timeout, transport=transport)
        self._lock = threading.Lock()
        self._token: str | None = None
        self._refresh_at = 0.0  # monotonic deadline at which to re-mint

    @classmethod
    def from_file(cls, path: str | Path, **kwargs) -> "MsiHolesClient":
        """Build from a *.client.json credentials file. Reads client_id,
        client_secret, token_endpoint and (if present) base_url."""
        data = json.loads(Path(path).read_text())
        try:
            client_id = data["client_id"]
            client_secret = data["client_secret"]
        except KeyError as exc:
            raise ValueError(
                f"{path}: credentials file missing required key {exc}; "
                "expected a *.client.json from create_service_client.py"
            ) from exc
        kwargs.setdefault("token_endpoint", data.get("token_endpoint", DEFAULT_TOKEN_ENDPOINT))
        if "base_url" in data:
            kwargs.setdefault("base_url", data["base_url"])
        return cls(client_id=client_id, client_secret=client_secret, **kwargs)

    # -- token handling -----------------------------------------------------
    def _mint(self) -> None:
        resp = self._http.post(
            self._token_endpoint,
            auth=(self._client_id, self._client_secret),  # HTTP Basic (client_secret_basic)
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        body = resp.json()
        token = body.get("access_token")
        ttl = float(body.get("expires_in") or 0)
        if not token or ttl <= 0:
            raise ValueError(f"token endpoint returned an unexpected body (no access_token/expires_in): {body!r}")
        # Bake the refresh margin into the deadline, but never let it exceed half
        # the TTL — otherwise a short-lived token would collapse into 'mint every
        # request'. margin = min(skew, ttl/2).
        margin = min(self._skew, ttl * 0.5)
        self._token = token
        self._refresh_at = time.monotonic() + ttl - margin

    def _bearer(self, stale: str | None = None) -> str:
        with self._lock:
            # Re-mint if there is no token, it's due for refresh, or the caller's
            # token is the one currently cached (stale after a 401). If another
            # thread already rotated the token, reuse it — collapses concurrent
            # 401s into a single mint instead of a per-thread storm.
            if self._token is None or time.monotonic() >= self._refresh_at or (stale is not None and self._token == stale):
                self._mint()
            return self._token  # type: ignore[return-value]

    # -- requests -----------------------------------------------------------
    def _check_origin(self, url: str) -> None:
        u = httpx.URL(url)
        if u.is_absolute_url and (u.scheme, u.host, u.port) != (self._base.scheme, self._base.host, self._base.port):
            raise ValueError(
                f"refusing to send the bearer token to a non-base origin: {u.scheme}://{u.host} (base is {self._base})"
            )

    @staticmethod
    def _replayable(kwargs: dict) -> bool:
        if "files" in kwargs:
            return False
        content = kwargs.get("content")
        return content is None or isinstance(content, (bytes, str))

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Like httpx.request, but injects a valid Bearer token. `url` is a path
        (joined onto base_url) or an absolute URL with the same origin as base_url."""
        self._check_origin(url)
        headers = dict(kwargs.pop("headers", None) or {})  # keep caller headers...
        token = self._bearer()
        headers["Authorization"] = f"Bearer {token}"        # ...but the client owns auth
        resp = self._http.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 401 and self._replayable(kwargs):
            token = self._bearer(stale=token)
            headers["Authorization"] = f"Bearer {token}"
            resp = self._http.request(method, url, headers=headers, **kwargs)
        return resp

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    # -- lifecycle ----------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MsiHolesClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
