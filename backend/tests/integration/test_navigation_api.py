"""Integration tests for POST /api/v1/routes/navigate on real OSM-shaped data."""

import json

import httpx
import pytest
from sqlalchemy import text

from app.db.session import get_session
from app.models import Building
from app.services.osm_import_service import import_osm
from app.state import app_state


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

    app_state.clear_closures()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app_state.clear_closures()


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


async def test_navigate_connects_requested_endpoints_with_road_only_steps(client, imported_osm):
    origin = (74.8590, 32.7290 + 20.0 / 110574.0)
    destination = (74.8598, 32.7293)
    response = await client.post(
        "/api/v1/routes/navigate",
        json={**_nav_body(origin, destination), "avoid_hazards": False},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    coordinates = body["route"]["geometry"]["coordinates"]
    assert coordinates[0] == pytest.approx(list(origin))
    assert [74.8590, 32.7290] in coordinates
    assert coordinates[-1] == pytest.approx(list(destination))
    properties = body["route"]["properties"]
    assert properties["steps"]
    assert properties["steps"][0]["maneuver"] == "depart"
    assert properties["steps"][-1]["maneuver"] == "arrive"
    assert all(step["mode"] != "walk" for step in properties["steps"])
    assert properties["access_distance_m"] == pytest.approx(20.0, abs=1.0)
    assert properties["road_distance_m"] > 0
    assert properties["distance_m"] == pytest.approx(properties["road_distance_m"], abs=1.0)
    assert any("nearest OSM roads" in warning for warning in properties["warnings"])


async def test_navigate_trims_the_final_connector_at_the_building_frontage(
    client, imported_osm, db
):
    footprint = [
        [74.8599, 32.7291],
        [74.8601, 32.7291],
        [74.8601, 32.7293],
        [74.8599, 32.7293],
        [74.8599, 32.7291],
    ]
    center = [74.8600, 32.7292]
    db.add(
        Building(
            code="B-TEST",
            name="Frontage Block",
            floors=2,
            building_type="Residential",
            construction="Brick",
            occupancy=10,
            year_built=1980,
            height_m=6.6,
            priority=50,
            status="ok",
            center=center,
            footprint=footprint,
            access_node_code="",
            attributes={},
            geom=(
                "POLYGON(("
                + ", ".join(f"{p[0]:.8f} {p[1]:.8f}" for p in footprint)
                + "))"
            ),
            center_point=f"POINT({center[0]:.8f} {center[1]:.8f})",
        )
    )
    await db.commit()

    response = await client.post(
        "/api/v1/routes/navigate",
        json={
            **_nav_body((74.8590, 32.7290), center),
            "destination_building_id": "B-TEST",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    coordinates = body["route"]["geometry"]["coordinates"]
    assert coordinates[-1] == pytest.approx([74.8600, 32.7291], abs=1e-5)
    assert body["destination"]["lat"] == pytest.approx(32.7291, abs=1e-5)
    assert body["destination"]["lng"] == pytest.approx(74.8600, abs=1e-5)
    assert any(
        "street-facing entrance" in warning for warning in body["warnings"]
    )


async def test_navigate_without_osm_import_reports_empty_graph(client, db):
    await db.execute(text("DELETE FROM lanes"))
    await db.commit()
    response = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), (74.8600, 32.7290)),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OSM_GRAPH_EMPTY"


async def test_navigate_nearest_station_uses_mapbox_station(client, imported_osm, monkeypatch):
    async def fake_mapbox(department, lat, lng, *, limit=8):
        assert department == "fire"
        assert lat == pytest.approx(32.7290)
        assert lng == pytest.approx(74.8600)
        return [
            {
                "id": "mapbox:fire-1",
                "department": "fire",
                "name": "Fire Station",
                "address": "Residency Road, Jammu",
                "lat": 32.7290,
                "lng": 74.8590,
                "pos": [74.8590, 32.7290],
                "distance_m": 93.0,
                "source": "mapbox",
                "category": "fire_station",
            }
        ]

    monkeypatch.setattr("app.services.station_service.mapbox_stations", fake_mapbox)
    response = await client.post(
        "/api/v1/routes/navigate",
        json={
            "destination": {"lat": 32.7290, "lng": 74.8600},
            "origin_mode": "nearest_station",
            "department": "fire",
            "profile": "fire_truck",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    station = body["origin_station"]
    assert station["name"] == "Fire Station"
    assert station["source"] == "mapbox"
    assert station["lat"] == pytest.approx(32.7290)
    assert body["stations_considered"] == 1
    assert body["origin"]["snap_distance_m"] < 1
    assert any("Mapbox-listed fire" in warning for warning in body["warnings"])


async def test_navigate_nearest_station_requires_department(client, imported_osm):
    response = await client.post(
        "/api/v1/routes/navigate",
        json={
            "destination": {"lat": 32.7290, "lng": 74.8600},
            "origin_mode": "nearest_station",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_navigate_nearest_station_reports_missing_station_data(client, imported_osm, monkeypatch):
    async def no_stations(department, lat, lng, *, limit=8):
        return []

    monkeypatch.setattr("app.services.station_service.mapbox_stations", no_stations)
    response = await client.post(
        "/api/v1/routes/navigate",
        json={
            "destination": {"lat": 32.7290, "lng": 74.8600},
            "origin_mode": "nearest_station",
            "department": "police",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "STATION_DATA_UNAVAILABLE"


async def test_stations_endpoint_lists_mapbox_stations(client, imported_osm, monkeypatch):
    async def fake_mapbox(department, lat, lng, *, limit=8):
        return [
            {
                "id": "mapbox:hospital-1",
                "department": department,
                "name": "Government Medical College Hospital",
                "address": "Bakshi Nagar, Jammu",
                "lat": 32.73066607,
                "lng": 74.85733675,
                "pos": [74.85733675, 32.73066607],
                "distance_m": 51.2,
                "source": "mapbox",
                "category": "hospital",
            }
        ]

    monkeypatch.setattr("app.services.station_service.mapbox_stations", fake_mapbox)
    response = await client.get(
        "/api/v1/routes/stations",
        params={"department": "medical", "lat": 32.7290, "lng": 74.8600, "limit": 3},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["department"] == "medical"
    assert body["count"] == 1
    assert body["source"] == "mapbox"
    assert body["stations"][0]["name"] == "Government Medical College Hospital"


async def test_closure_api_blocks_route_until_removed(client, imported_osm):
    body = _nav_body((74.8590, 32.7290), (74.8600, 32.7290))
    baseline = await client.post("/api/v1/routes/navigate", json=body)
    assert baseline.status_code == 200, baseline.text

    created = await client.post(
        "/api/v1/routes/closures",
        json={
            "lat": 32.7293,
            "lng": 74.8598,
            "radius_m": 80,
            "reason": "Water main repair",
            "source": "manual",
        },
    )
    assert created.status_code == 201, created.text
    closure = created.json()
    assert closure["id"].startswith("closure-")
    assert closure["reason"] == "Water main repair"

    listed = await client.get("/api/v1/routes/closures")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    blocked = await client.post("/api/v1/routes/navigate", json=body)
    assert blocked.status_code == 404
    assert blocked.json()["error"]["code"] == "ROUTE_NOT_FOUND"

    removed = await client.delete(f"/api/v1/routes/closures/{closure['id']}")
    assert removed.status_code == 200
    reopened = await client.post("/api/v1/routes/navigate", json=body)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["route"]["properties"]["distance_m"] == pytest.approx(
        baseline.json()["route"]["properties"]["distance_m"]
    )


async def test_clear_closures_reopens_all_roads(client, imported_osm):
    body = _nav_body((74.8590, 32.7290), (74.8600, 32.7290))
    created = await client.post(
        "/api/v1/routes/closures",
        json={"lat": 32.7293, "lng": 74.8598, "radius_m": 15},
    )
    assert created.status_code == 201
    cleared = await client.delete("/api/v1/routes/closures")
    assert cleared.status_code == 200
    assert (await client.get("/api/v1/routes/closures")).json()["count"] == 0
    reopened = await client.post("/api/v1/routes/navigate", json=body)
    assert reopened.status_code == 200, reopened.text


async def test_navigation_reports_active_closures(client, imported_osm):
    await client.post(
        "/api/v1/routes/closures",
        json={"lat": 32.7350, "lng": 74.8700, "radius_m": 10},
    )
    response = await client.post(
        "/api/v1/routes/navigate",
        json=_nav_body((74.8590, 32.7290), (74.8600, 32.7290)),
    )
    assert response.status_code == 200, response.text
    properties = response.json()["route"]["properties"]
    assert properties["closures_considered"] == 1
    assert any("road closure" in warning for warning in properties["warnings"])
