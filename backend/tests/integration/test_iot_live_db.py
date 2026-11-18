"""DB-backed checks for the three Wokwi mappings.

These tests run against the configured ``DATABASE_URL`` (the seeded Supabase
database in development) inside a single transaction that is rolled back, so
they never leave readings, risks or incidents behind.

They are skipped by default because the normal test suite uses a local
PostgreSQL instance. Run them explicitly:

    $env:JURAS_LIVE_DB_TESTS = "1"
    .\\.venv\\Scripts\\python.exe -m pytest tests/integration/test_iot_live_db.py -q
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import NotFoundError, ValidationAppError
from app.db.session import SessionFactory
from app.iot.registry import IOT_DEVICES
from app.models import Building, Incident, LaneNode, Reading, RiskAssessment, Sensor
from app.repositories import incident_repo, sensor_repo
from app.services.incident_service import transition
from app.services.reading_service import ingest

pytestmark = pytest.mark.skipif(
    os.getenv("JURAS_LIVE_DB_TESTS") != "1",
    reason="set JURAS_LIVE_DB_TESTS=1 to run against the configured database",
)

FIRE_NORMAL = {
    "device_id": "JURAS-FIRE-001",
    "sensor_id": "JM-014",
    "building_id": "B-014",
    "hazard": "fire",
    "source": "simulation",
    "simulation": True,
    "values": {"smoke_level": 4.0, "smoke_ppm": 40.0, "temperature_c": 31.8},
}

FIRE_HIGH = {
    "device_id": "JURAS-FIRE-001",
    "sensor_id": "JM-014",
    "building_id": "B-014",
    "hazard": "fire",
    "source": "simulation",
    "simulation": True,
    "values": {"smoke_level": 95.0, "smoke_ppm": 950.0, "temperature_c": 95.0},
}

STRUCT_NORMAL = {
    "device_id": "JURAS-STRUCT-001",
    "sensor_id": "JM-S07",
    "building_id": "B-007",
    "hazard": "structural",
    "source": "simulation",
    "simulation": True,
    "values": {"tilt_deg": 0.05, "crack_mm": 0.12, "vib_rms": 0.02, "deviation_mm": 2.9},
}

STORM_NORMAL = {
    "device_id": "JURAS-STORM-001",
    "sensor_id": "JM-R01",
    "node_code": "I",
    "hazard": "flood",
    "source": "simulation",
    "simulation": True,
    "values": {"water_level_cm": 2.0, "rain_mmh": 0.0, "distance_cm": 98.0},
}


@pytest.fixture
async def live_db():
    async with SessionFactory() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def _sensor(session, code: str) -> Sensor | None:
    return await sensor_repo.get_by_code(session, code)


async def _count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_registry_matches_seeded_rows_and_has_no_duplicates(live_db):
    for device in IOT_DEVICES.values():
        sensor = await _sensor(live_db, device.sensor_code)
        assert sensor is not None, f"{device.sensor_code} is missing"
        assert sensor.kind == device.sensor_kind
        assert sensor.source == "simulation"
        assert (sensor.attributes or {}).get("device_id") == device.device_id
        assert (sensor.attributes or {}).get("wokwi") is True

        duplicates = await live_db.scalar(
            select(func.count()).select_from(Sensor).where(Sensor.code == device.sensor_code)
        )
        assert duplicates == 1

        if device.target_type == "building":
            assert sensor.node_code is None
            building = await live_db.get(Building, sensor.building_id)
            assert building is not None
            assert building.code == device.target_code
        else:
            assert sensor.building_id is None
            assert sensor.node_code == device.target_code
            node = (
                await live_db.execute(select(LaneNode).where(LaneNode.code == device.target_code))
            ).scalar_one_or_none()
            assert node is not None


async def test_all_three_payloads_ingest_with_verified_targets(live_db):
    cases = [
        (FIRE_NORMAL, "JM-014", "B-014", None, "JURAS-FIRE-001"),
        (STRUCT_NORMAL, "JM-S07", "B-007", None, "JURAS-STRUCT-001"),
        (STORM_NORMAL, "JM-R01", None, "I", "JURAS-STORM-001"),
    ]
    for payload, sensor_code, building_code, node_code, device_id in cases:
        result = await ingest(live_db, payload)
        assert result["accepted"] is True
        assert result["sensor_code"] == sensor_code
        assert result["building_code"] == building_code
        assert result["node_code"] == node_code
        assert result["device_id"] == device_id
        assert result["source"] == "simulation"
        assert result["simulation"] is True
        assert result["risk"] is not None
        assert result["risk"]["device_id"] == device_id
        assert result["risk"]["simulation"] is True

        names = [name for name, _ in result["events"]]
        assert names == ["reading.updated", "risk.updated"]
        for name, data in result["events"]:
            assert data["simulation"] is True
            assert data["device_id"] == device_id


async def test_simulation_flags_are_forced_for_registered_devices(live_db):
    # An older sketch may still send source=field / simulation=false. The
    # backend must store simulation anyway because the device is a Wokwi node.
    payload = {**FIRE_NORMAL, "source": "field", "simulation": False}
    result = await ingest(live_db, payload)
    assert result["source"] == "simulation"
    assert result["simulation"] is True

    reading = (
        await live_db.execute(select(Reading).where(Reading.id == uuid.UUID(result["id"])))
    ).scalar_one_or_none()
    assert reading is not None
    assert reading.source == "simulation"
    assert reading.simulation is True

    reading_event = next(data for name, data in result["events"] if name == "reading.updated")
    risk_event = next(data for name, data in result["events"] if name == "risk.updated")
    assert reading_event["source"] == "simulation"
    assert reading_event["simulation"] is True
    assert risk_event["simulation"] is True


async def test_device_only_payload_resolves_building_and_node(live_db):
    fire = await ingest(live_db, {k: v for k, v in FIRE_NORMAL.items() if k != "building_id"})
    assert fire["building_code"] == "B-014"

    storm = await ingest(live_db, {k: v for k, v in STORM_NORMAL.items() if k != "node_code"})
    assert storm["node_code"] == "I"
    assert storm["building_code"] is None


async def test_high_reading_creates_one_incident_and_dedupes(live_db):
    first = await ingest(live_db, FIRE_HIGH)
    assert first["incident_created"] is True
    assert first["incident_code"] == "AL-FIRE-B-014"
    assert first["risk"]["incident_status"] == "open"
    assert [name for name, _ in first["events"]].count("incident.created") == 1

    second = await ingest(live_db, FIRE_HIGH)
    assert second["incident_created"] is False
    assert second["incident_code"] == first["incident_code"]
    assert [name for name, _ in second["events"]].count("incident.created") == 0

    active = await live_db.scalar(
        select(func.count())
        .select_from(Incident)
        .where(
            Incident.hazard == "fire",
            Incident.status == "open",
            Incident.code == first["incident_code"],
        )
    )
    assert active == 1

    incident = await incident_repo.get_by_code(live_db, first["incident_code"])
    assert incident is not None
    events: list[tuple[str, dict]] = []
    await transition(live_db, incident, "resolved", "test", "resolved in DB test", events)
    assert [name for name, _ in events] == ["incident.resolved"]
    assert events[0][1]["simulation"] is True
    assert events[0][1]["last_update"] == events[0][1]["resolved_at"]

    # A resolved incident must not absorb a new event.
    third = await ingest(live_db, FIRE_HIGH)
    assert third["incident_created"] is True
    assert third["incident_code"] != first["incident_code"]


async def test_invalid_and_unknown_inputs_are_rejected_without_writes(live_db):
    readings_before = await _count(live_db, Reading)
    risks_before = await _count(live_db, RiskAssessment)
    incidents_before = await _count(live_db, Incident)

    with pytest.raises(ValidationAppError) as non_finite:
        await ingest(live_db, {**FIRE_NORMAL, "values": {"temperature_c": float("nan")}})
    assert non_finite.value.code == "INVALID_READING"

    with pytest.raises(ValidationAppError) as out_of_range:
        await ingest(live_db, {**FIRE_NORMAL, "values": {"temperature_c": 500.0}})
    assert out_of_range.value.code == "INVALID_READING"

    with pytest.raises(ValidationAppError) as non_numeric:
        await ingest(live_db, {**FIRE_NORMAL, "values": {"temperature_c": "hot"}})
    assert non_numeric.value.code == "INVALID_READING"

    with pytest.raises(NotFoundError) as unknown_device:
        await ingest(live_db, {**FIRE_NORMAL, "device_id": "JURAS-UNKNOWN-999"})
    assert unknown_device.value.code == "UNKNOWN_DEVICE"

    with pytest.raises(NotFoundError) as unknown_sensor:
        await ingest(live_db, {**FIRE_NORMAL, "sensor_id": "JM-NOPE", "device_id": None})
    assert unknown_sensor.value.code == "SENSOR_NOT_FOUND"

    with pytest.raises(ValidationAppError) as wrong_building:
        await ingest(live_db, {**FIRE_NORMAL, "building_id": "B-007"})
    assert wrong_building.value.code == "SENSOR_TARGET_MISMATCH"

    with pytest.raises(ValidationAppError) as wrong_hazard:
        await ingest(
            live_db,
            {
                **FIRE_NORMAL,
                "hazard": "flood",
                "values": {"water_level_cm": 10.0, "rain_mmh": 5.0},
            },
        )
    assert wrong_hazard.value.code == "DEVICE_HAZARD_MISMATCH"

    assert await _count(live_db, Reading) == readings_before
    assert await _count(live_db, RiskAssessment) == risks_before
    assert await _count(live_db, Incident) == incidents_before
