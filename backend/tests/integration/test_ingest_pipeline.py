import pytest

from app.core.exceptions import NotFoundError
from app.services.reading_service import ingest
from app.services.incident_service import transition


async def test_ingest_persists_reading_risk_incident(db, seeded_world):
    result = await ingest(
        db,
        {
            "sensor_id": str(seeded_world["sensor"].id),
            "building_id": str(seeded_world["building"].id),
            "hazard": "fire",
            "values": {"temperature_c": 95, "smoke_level": 88, "smoke_ppm": 880},
            "source": "simulation",
            "simulation": True,
        },
    )
    assert result["accepted"] is True
    assert result["risk"]["category"] == "critical"
    assert result["risk"]["score"] >= 85
    assert result["incident_created"] is True
    assert result["incident_id"] is not None


async def test_incident_dedupe_no_duplicate_per_tick(db, seeded_world):
    first = await ingest(
        db,
        {"building_id": str(seeded_world["building"].id), "hazard": "fire",
         "values": {"temperature_c": 95, "smoke_level": 88}},
    )
    second = await ingest(
        db,
        {"building_id": str(seeded_world["building"].id), "hazard": "fire",
         "values": {"temperature_c": 96, "smoke_level": 90}},
    )
    assert first["incident_id"] == second["incident_id"]
    assert second["incident_created"] is False


async def test_incident_reopens_after_resolve(db, seeded_world):
    first = await ingest(
        db,
        {"building_id": str(seeded_world["building"].id), "hazard": "fire",
         "values": {"temperature_c": 95, "smoke_level": 88}},
    )
    from app.repositories import incident_repo

    inc = await incident_repo.get(db, first["incident_id"])
    await transition(db, inc, "resolved", "test", "closing", [])
    await db.commit()
    second = await ingest(
        db,
        {"building_id": str(seeded_world["building"].id), "hazard": "fire",
         "values": {"temperature_c": 97, "smoke_level": 92}},
    )
    assert second["incident_created"] is True
    assert second["incident_id"] != first["incident_id"]


async def test_normal_reading_creates_no_incident(db, seeded_world):
    result = await ingest(
        db,
        {"building_id": str(seeded_world["building"].id), "hazard": "fire",
         "values": {"temperature_c": 32, "smoke_level": 3}},
    )
    assert result["risk"]["category"] == "normal"
    assert result["incident_id"] is None
    assert result["incident_created"] is False


async def test_reading_tagged_synthetic(db, seeded_world):
    result = await ingest(
        db,
        {"building_id": str(seeded_world["building"].id), "hazard": "fire",
         "values": {"temperature_c": 95, "smoke_level": 88}},
    )
    from app.repositories import reading_repo

    reading = await reading_repo.latest_for_sensor(db, seeded_world["sensor"].id)
    assert reading.simulation is True
    assert reading.source == "simulation"
    assert reading.simulation_id is None


async def test_sensor_only_reading_inherits_sensor_building(db, seeded_world):
    result = await ingest(
        db,
        {"sensor_id": str(seeded_world["sensor"].id), "hazard": "fire",
         "values": {"temperature_c": 95, "smoke_level": 88, "smoke_ppm": 880},
         "source": "field", "simulation": False},
    )
    assert result["risk"]["entity_type"] == "building"
    assert result["risk"]["entity_code"] == "B-T1"
    assert result["risk"]["category"] == "critical"
    assert result["incident_created"] is True


async def test_building_without_matching_sensor_returns_404(db, seeded_world):
    with pytest.raises(NotFoundError) as exc:
        await ingest(
            db,
            {"building_id": "B-T1", "hazard": "structural",
             "values": {"tilt_deg": 1.0, "crack_mm": 1.2}},
        )
    assert exc.value.code == "SENSOR_NOT_FOUND"
    assert exc.value.status_code == 404
