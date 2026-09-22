"""Tests for the ORBISmap API client and vector_stroy job fetch stage."""

from __future__ import annotations

import json

import pytest

from collector.jobs import vector_stroy_job
from collector.vector_api_client import OrbisMapApiError, OrbisMapClient


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


class FakeSession:
    def __init__(self, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)


def _client(session):
    return OrbisMapClient(
        base_url="https://vector.example/api/2.8/mggt",
        username="user",
        password="pass",
        session=session,
    )


FEATURE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": 1,
            "properties": {"orbis_id": 1.0, "status": "Действует"},
            "geometry": {"type": "Point", "coordinates": [37.0, 55.0]},
        }
    ],
}


class TestOrbisMapClient:
    def test_login_posts_form_credentials(self):
        session = FakeSession(post_responses=[FakeResponse(json_data={"token": "abc"})])
        client = _client(session)
        token = client._login()
        assert token == "abc"
        url, kwargs = session.post_calls[0]
        assert url.endswith("/login/")
        assert kwargs["data"] == {"login": "user", "password": "pass"}

    def test_login_http_error_raises(self):
        session = FakeSession(post_responses=[FakeResponse(status_code=403, text="Forbidden")])
        with pytest.raises(OrbisMapApiError, match="403"):
            _client(session)._login()

    def test_login_without_token_raises(self):
        session = FakeSession(post_responses=[FakeResponse(json_data={})])
        with pytest.raises(OrbisMapApiError, match="no token"):
            _client(session)._login()

    def test_fetch_layer_geojson_passes_token_and_params(self):
        session = FakeSession(
            post_responses=[FakeResponse(json_data={"token": "abc"})],
            get_responses=[FakeResponse(json_data=FEATURE_COLLECTION)],
        )
        data = _client(session).fetch_layer_geojson("map221", "rs_2022", geom_sr=4326)
        assert data == FEATURE_COLLECTION
        url, kwargs = session.get_calls[0]
        assert "/map221/layers/rs_2022/export/" in url
        assert kwargs["params"]["token"] == "abc"
        assert kwargs["params"]["format"] == "geojson"
        assert kwargs["params"]["geomSR"] == 4326

    def test_fetch_relogins_once_on_401(self):
        session = FakeSession(
            post_responses=[
                FakeResponse(json_data={"token": "abc"}),
                FakeResponse(json_data={"token": "def"}),
            ],
            get_responses=[
                FakeResponse(status_code=401, text="unauthorized"),
                FakeResponse(json_data=FEATURE_COLLECTION),
            ],
        )
        data = _client(session).fetch_layer_geojson("map221", "rs_2022")
        assert data == FEATURE_COLLECTION
        assert len(session.post_calls) == 2
        assert len(session.get_calls) == 2
        assert session.get_calls[1][1]["params"]["token"] == "def"

    def test_fetch_http_error_raises(self):
        session = FakeSession(
            post_responses=[FakeResponse(json_data={"token": "abc"})],
            get_responses=[FakeResponse(status_code=500, text="boom")],
        )
        with pytest.raises(OrbisMapApiError, match="500"):
            _client(session).fetch_layer_geojson("map221", "rs_2022")

    def test_fetch_non_feature_collection_raises(self):
        session = FakeSession(
            post_responses=[FakeResponse(json_data={"token": "abc"})],
            get_responses=[FakeResponse(json_data=[{"id": 1}])],
        )
        with pytest.raises(OrbisMapApiError, match="FeatureCollection"):
            _client(session).fetch_layer_geojson("map221", "rs_2022")

    def test_fetch_non_json_raises(self):
        session = FakeSession(
            post_responses=[FakeResponse(json_data={"token": "abc"})],
            get_responses=[FakeResponse(text="<html>")],
        )
        with pytest.raises(OrbisMapApiError, match="non-JSON"):
            _client(session).fetch_layer_geojson("map221", "rs_2022")


class TestFetchGeojsonToDisk:
    def _patch_paths(self, monkeypatch, tmp_path):
        target = tmp_path / "url_222_wgs.geojson"
        monkeypatch.setattr(vector_stroy_job, "SOURCE_GEOJSON", target)
        return target

    def test_missing_credentials_skips(self, monkeypatch, tmp_path):
        target = self._patch_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(vector_stroy_job, "VECTOR_API_USERNAME", "")
        monkeypatch.setattr(vector_stroy_job, "VECTOR_API_PASSWORD", "")
        assert vector_stroy_job._fetch_geojson_to_disk() is False
        assert not target.exists()

    def test_writes_feature_collection(self, monkeypatch, tmp_path):
        target = self._patch_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(vector_stroy_job, "VECTOR_API_USERNAME", "user")
        monkeypatch.setattr(vector_stroy_job, "VECTOR_API_PASSWORD", "pass")

        class StubClient:
            def __init__(self, **kwargs):
                pass

            def fetch_layer_geojson(self, map_code, layer_code, *, geom_sr=4326):
                assert map_code == "map221"
                assert layer_code == "rs_2022"
                return FEATURE_COLLECTION

        monkeypatch.setattr(vector_stroy_job, "OrbisMapClient", StubClient)
        assert vector_stroy_job._fetch_geojson_to_disk() is True
        assert json.loads(target.read_text(encoding="utf-8")) == FEATURE_COLLECTION

    def test_fetch_error_returns_false(self, monkeypatch, tmp_path):
        target = self._patch_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(vector_stroy_job, "VECTOR_API_USERNAME", "user")
        monkeypatch.setattr(vector_stroy_job, "VECTOR_API_PASSWORD", "pass")

        class FailingClient:
            def __init__(self, **kwargs):
                pass

            def fetch_layer_geojson(self, map_code, layer_code, *, geom_sr=4326):
                raise OrbisMapApiError("boom")

        monkeypatch.setattr(vector_stroy_job, "OrbisMapClient", FailingClient)
        assert vector_stroy_job._fetch_geojson_to_disk() is False
        assert not target.exists()
