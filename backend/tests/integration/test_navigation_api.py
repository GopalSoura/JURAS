"""Integration tests for POST /api/v1/routes/navigate on real OSM-shaped data."""

import json

import httpx
import pytest
from sqlalchemy import text

from app.db.session import get_session
from app.services.osm_import_service import import_osm


def _road(way_id: str, coordinates, *, highway="residential", **tags):
    props = {
        "@id": f"way/{way_id}",
        "juras_type": "lane_or_road",
        "juras_id": f"way/{way_id}",
        "highway": highway,
        **tags,
    }
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": coordinates},
    }


NAV_LANES = {
    "type": "FeatureCollection",
    "features": [
        _road("8001", [[74.8590, 32.7290], [74.8595, 32.7290]], highway="secondary", lanes="2"),
        _road(
            "8002",
            [[74.8595, 32.7290], [74.8598, 32.7293], [74.8600, 32.7290]],
            highway="residential",
        ),
        _road(
            "8003",
            [[74.8600, 32.7290], [74.8600, 32.7400]],
            highway="footway",
        ),
        _road("8004", [[74.8800, 32.7290], [74.8805, 32.7290]], highway="residential", oneway="yes"),
        _road("8005", [[74.8900, 32.7290], [74.8920, 32.7290]], highway="secondary"),
    ],
}

NAV_BUILDINGS = {"type": "FeatureCollection", "features": []}


@pytest.fixture
def nav_datasets(tmp_path):
    buildings = tmp_path / "buildings.geojson"
    lanes = tmp_path / "roads_lanes.geojson"
    buildings.write_text(json.dumps(NAV_BUILDINGS), encoding="utf-8")
    lanes.write_text(json.dumps(NAV_LANES), encoding="utf-8")
    return buildings, lanes


@pytest.fixture
async def imported_osm(db, nav_datasets):
    buildings, lanes = nav_datasets
    await import_osm(db, buildings, lanes)
    await db.commit()


@pytest.fixture
def patch_db(test_session_factory, monkeypatch):
    sf = test_session_factory

    async def override_get_session():
        async with sf() as session:
            yield session

    from app.main import app

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr("app.api.v1.endpoints.readings.SessionFactory", sf)
    monkeypatch.setattr("app.api.v1.endpoints.incidents.SessionFactory", sf)
    yield sf
    app.dependency_overrides.clear()


@pytest.fixture
async def client(patch_db):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _nav_body(origin, destination, profile="fire_truck"):
    return {
        "origin": {"lat": origin[1], "lng": origin[0]},
        "destination": {"lat": destination[1], "lng": destination[0]},
        "profile": profile,
    }


async def test_navigate_connected_osm_route_returns_real_geometry(client, imported_osm):
    response = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), (74.8600, 32.7290)),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    route = body["route"]
    assert route["type"] == "Feature"
    assert route["geometry"]["type"] == "LineString"
    coords = route["geometry"]["coordinates"]
    assert len(coords) >= 4
    assert [74.8595, 32.729] in coords
    assert [74.8598, 32.7293] in coords
    properties = route["properties"]
    assert properties["profile"] == "fire_truck"
    assert properties["distance_m"] == pytest.approx(128, abs=6)
    assert isinstance(properties["duration_s"], int) and properties["duration_s"] > 0
    assert properties["geometry_source"] == "openstreetmap"
    assert properties["algorithm"] == "astar_osm"
    assert properties["edge_ids"]
    assert body["origin"]["snap_distance_m"] < 1
    assert body["destination"]["snap_distance_m"] < 1


async def test_navigate_walking_reaches_footway_but_fire_truck_does_not(client, imported_osm):
    destination = (74.8600, 32.7400)
    fire = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), destination, profile="fire_truck"),
    )
    assert fire.status_code == 422
    assert fire.json()["error"]["code"] == "DESTINATION_OUT_OF_NETWORK"

    walk = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), destination, profile="walking"),
    )
    assert walk.status_code == 200, walk.text
    assert walk.json()["route"]["properties"]["distance_m"] > 1000


async def test_navigate_honours_oneway_direction(client, imported_osm):
    forward = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8800, 32.7290), (74.8805, 32.7290)),
    )
    assert forward.status_code == 200, forward.text

    reverse = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8805, 32.7290), (74.8800, 32.7290)),
    )
    assert reverse.status_code == 404
    assert reverse.json()["error"]["code"] == "ROUTE_NOT_FOUND"


async def test_navigate_disconnected_components_are_refused(client, imported_osm):
    response = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), (74.8910, 32.7290)),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTE_NOT_FOUND"
    assert "disconnected" in response.json()["error"]["message"].lower()


async def test_navigate_validation_contract(client):
    bad_profile = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), (74.8600, 32.7290), profile="rocket"),
    )
    assert bad_profile.status_code == 422
    assert bad_profile.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = await client.post(
        "/api/v1/routes/navigate",
        json={"origin": {"lat": 32.729, "lng": 74.859}, "profile": "fire_truck"},
    )
    assert missing.status_code == 422


async def test_navigate_without_osm_import_reports_empty_graph(client, db):
    await db.execute(text("DELETE FROM lanes"))
    await db.commit()
    response = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), (74.8600, 32.7290)),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OSM_GRAPH_EMPTY"
