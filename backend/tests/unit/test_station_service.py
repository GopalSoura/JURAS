"""Unit tests for Mapbox-listed emergency station lookup."""

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import station_service

PAYLOAD = {
    "features": [
        {
            "properties": {
                "mapbox_id": "dXJuOm1ieHBvaTpzdGF0aW9uMg",
                "name": "Gandhi Nagar Fire Station",
                "full_address": "Gandhi Nagar, Jammu",
                "poi_category": ["fire_station"],
            },
            "geometry": {"type": "Point", "coordinates": [74.86869848, 32.71022814]},
        },
        {
            "properties": {
                "mapbox_id": "dXJuOm1ieHBvaTpzdGF0aW9uMQ",
                "name": "Fire Station",
                "place_formatted": "Residency Road, Jammu",
            },
            "geometry": {"type": "Point", "coordinates": [74.86874893, 32.74079311]},
        },
        {
            "properties": {"name": "Broken geometry"},
            "geometry": None,
        },
    ]
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, params=None):
        FakeClient.calls.append((url, params))
        return FakeResponse(PAYLOAD)


@pytest.fixture(autouse=True)
def clear_cache():
    station_service._cache.clear()
    FakeClient.calls.clear()
    yield
    station_service._cache.clear()


@pytest.fixture
def mapbox_enabled(monkeypatch):
    monkeypatch.setattr(settings, "mapbox_access_token", "pk.test-token")
    monkeypatch.setattr(station_service.httpx, "AsyncClient", FakeClient)


async def test_mapbox_stations_returns_nearest_first(mapbox_enabled):
    stations = await station_service.mapbox_stations("fire", 32.7285, 74.8575, limit=5)
    assert [station["name"] for station in stations] == [
        "Fire Station",
        "Gandhi Nagar Fire Station",
    ]
    assert stations[0]["lat"] == pytest.approx(32.74079311)
    assert stations[0]["lng"] == pytest.approx(74.86874893)
    assert stations[0]["source"] == "mapbox"
    assert stations[0]["address"] == "Residency Road, Jammu"
    assert stations[0]["distance_m"] < stations[1]["distance_m"]
    assert len(FakeClient.calls) == 1
    url, params = FakeClient.calls[0]
    assert url.endswith("/fire_station")
    assert params["proximity"] == "74.857500,32.728500"
    assert params["access_token"] == "pk.test-token"


async def test_mapbox_stations_uses_cache(mapbox_enabled):
    first = await station_service.mapbox_stations("fire", 32.7285, 74.8575)
    second = await station_service.mapbox_stations("fire", 32.7285, 74.8575)
    assert first == second
    assert len(FakeClient.calls) == 1


async def test_mapbox_stations_without_token_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "mapbox_access_token", "")
    assert await station_service.mapbox_stations("fire", 32.7285, 74.8575) == []


async def test_nearest_stations_falls_back_to_demo_fire_post(monkeypatch):
    monkeypatch.setattr(settings, "mapbox_access_token", "")
    nodes = [
        SimpleNamespace(kind="fire_post", code="A", label="Fire Post A", pos=[74.85429648225089, 32.72705300522726]),
        SimpleNamespace(kind="medical_post", code="E", label="Medical Post E", pos=[74.86070351774912, 32.72705300522726]),
    ]
    stations = await station_service.nearest_stations(
        "fire", 32.7285, 74.8575, fallback_nodes=nodes
    )
    assert len(stations) == 1
    assert stations[0]["source"] == "demo"
    assert stations[0]["name"] == "Fire Post A"
    assert stations[0]["pos"] == [74.85429648225089, 32.72705300522726]


async def test_nearest_stations_police_has_no_demo_fallback(monkeypatch):
    monkeypatch.setattr(settings, "mapbox_access_token", "")
    assert await station_service.nearest_stations("police", 32.7285, 74.8575) == []
