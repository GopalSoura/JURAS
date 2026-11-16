import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import get_session


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


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("healthy", "degraded")


async def test_buildings_geojson(client, seeded_world):
    r = await client.get("/api/v1/buildings")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert any(f["properties"]["id"] == "B-T1" for f in body["features"])


async def test_building_detail(client, seeded_world):
    r = await client.get("/api/v1/buildings/B-T1")
    assert r.status_code == 200
    assert r.json()["code"] == "B-T1"
    assert r.json()["access_node"] == "B"


async def test_post_reading_returns_201_and_risk(client, seeded_world):
    r = await client.post(
        "/api/v1/readings",
        json={"building_id": "B-T1", "hazard": "fire",
              "values": {"temperature_c": 95, "smoke_level": 88}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["risk"]["category"] == "critical"
    assert body["incident_id"] is not None


async def test_incident_patch_and_events(client, seeded_world):
    r = await client.post(
        "/api/v1/readings",
        json={"building_id": "B-T1", "hazard": "fire",
              "values": {"temperature_c": 95, "smoke_level": 88}},
    )
    incident_id = r.json()["incident_id"]
    r2 = await client.patch(f"/api/v1/incidents/{incident_id}", json={"status": "acknowledged", "note": "t"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "acknowledged"
    r3 = await client.get(f"/api/v1/incidents/{incident_id}")
    assert len(r3.json()["events"]) >= 2


async def test_route_endpoint(client, seeded_world):
    r = await client.post(
        "/api/v1/routes",
        json={"origin": {"lat": 32.7285, "lon": 74.8576}, "destination_building_id": "B-T1", "responder_type": "fire_vehicle"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["geometry"]["type"] == "LineString"
    assert body["distance_m"] > 0
    assert body["algorithm"] == "dijkstra"
    assert len(body["warnings"]) >= 1


async def test_route_unknown_building_404(client, seeded_world):
    r = await client.post(
        "/api/v1/routes",
        json={"destination_building_id": "NOPE", "responder_type": "ambulance"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BUILDING_NOT_FOUND"


async def test_validation_error_contract(client):
    r = await client.post("/api/v1/readings", json={"hazard": "fire", "values": {}})
    assert r.status_code == 422
