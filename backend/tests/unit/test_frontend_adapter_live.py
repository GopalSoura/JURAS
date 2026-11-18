import asyncio
from datetime import datetime, timezone

from app.ws.frontend_adapter import FrontendWorld, now_ms


def make_world() -> FrontendWorld:
    world = FrontendWorld(None, None)  # type: ignore[arg-type]
    world.building_by_id = {"b14": "B-014", "b07": "B-007"}
    world.buildings = {
        "B-014": {"id": "B-014", "center": [74.857, 32.728], "priority": 20, "status": "ok"},
        "B-007": {
            "id": "B-007",
            "center": [74.856, 32.729],
            "priority": 55,
            "status": "watch",
            "tilt_deg": 0.06,
            "crack_mm": 0.1,
        },
    }
    world.base_buildings = {k: dict(v) for k, v in world.buildings.items()}
    world.sensors = [
        {
            "node_id": "JM-014",
            "kind": "smoke_temp",
            "pos": [74.857, 32.728],
            "label": "Smoke + temp, B-014",
            "building_id": "B-014",
            "node_code": None,
            "device_id": "JURAS-FIRE-001",
            "source": "simulation",
            "simulation": True,
        },
        {
            "node_id": "JM-S07",
            "kind": "structure",
            "pos": [74.856, 32.729],
            "label": "Tilt + crack, B-007",
            "building_id": "B-007",
            "node_code": None,
            "device_id": "JURAS-STRUCT-001",
            "source": "simulation",
            "simulation": True,
        },
        {
            "node_id": "JM-R01",
            "kind": "rain_level",
            "pos": [74.8567, 32.7290],
            "label": "Lane I-L low point",
            "building_id": None,
            "node_code": "I",
            "device_id": "JURAS-STORM-001",
            "source": "simulation",
            "simulation": True,
            "flood_factor": 1.0,
        },
    ]
    world.battery = {"JM-014": 90.0, "JM-S07": 91.0, "JM-R01": 92.0}

    async def broadcast(message: dict) -> None:
        world.broadcasts.append(message)  # type: ignore[attr-defined]

    world.broadcasts = []  # type: ignore[attr-defined]
    world.broadcast = broadcast  # type: ignore[method-assign]
    return world


async def test_fire_reading_updates_live_telemetry_and_not_synthetic():
    world = make_world()
    world._on_reading(
        {
            "sensor_code": "JM-014",
            "device_id": "JURAS-FIRE-001",
            "realtime": True,
            "values": {"smoke_level": 72.0, "smoke_ppm": 720.0, "temperature_c": 58.5},
            "observed_at": "2026-11-18T10:00:00+00:00",
            "source": "simulation",
            "simulation": True,
        }
    )
    await asyncio.sleep(0)

    sent = world.broadcasts  # type: ignore[attr-defined]
    assert sent and sent[-1]["t"] == "live"
    item = world._telemetry()[0]
    assert item["node_id"] == "JM-014"
    assert item["device_id"] == "JURAS-FIRE-001"
    assert item["live"] is True
    assert item["realtime"] is True
    assert item["simulation"] is True
    assert item["live_values"]["smoke_ppm"] == 720.0
    assert item["live_values"]["temp_c"] == 58.5
    # Simulation values stay synthetic; Wokwi data cannot overwrite them.
    assert "sim_values" in item and item["values"] == item["sim_values"]


async def test_structural_reading_preserves_vibration_and_deviation():
    world = make_world()
    world._on_reading(
        {
            "sensor_code": "JM-S07",
            "device_id": "JURAS-STRUCT-001",
            "realtime": True,
            "values": {
                "tilt_deg": 0.95,
                "crack_mm": 1.05,
                "vib_rms": 0.08,
                "deviation_mm": 4.6,
            },
            "simulation": True,
        }
    )
    item = next(i for i in world._telemetry() if i["node_id"] == "JM-S07")
    assert item["live_values"] == {
        "tilt_deg": 0.95,
        "crack_mm": 1.05,
        "vib_rms": 0.08,
        "deviation_mm": 4.6,
    }


async def test_storm_reading_maps_water_level_to_level_cm():
    world = make_world()
    world._on_reading(
        {
            "sensor_code": "JM-R01",
            "device_id": "JURAS-STORM-001",
            "realtime": True,
            "values": {"water_level_cm": 27.5, "rain_mmh": 18.0},
            "simulation": True,
        }
    )
    item = next(i for i in world._telemetry() if i["node_id"] == "JM-R01")
    assert item["live_values"]["level_cm"] == 27.5
    assert item["live_values"]["water_level_cm"] == 27.5
    assert item["live_values"]["rain_mmh"] == 18.0


async def test_risk_event_updates_building_marker_and_panel():
    world = make_world()
    world.live_readings["JM-S07"] = {
        "ts": 9_999_999_999_999.0,
        "values": {"tilt_deg": 1.2, "crack_mm": 1.5, "vib_rms": 0.1, "deviation_mm": 5.0},
    }
    world._on_risk(
        {
            "sensor_code": "JM-S07",
            "device_id": "JURAS-STRUCT-001",
            "hazard": "structural",
            "entity_type": "building",
            "entity_code": "B-007",
            "building_code": "B-007",
            "score": 92,
            "category": "critical",
            "reasons": [{"rule": "STRUCT-R1", "text": "tilt over threshold"}],
            "assessed_at": "2026-11-18T10:00:00+00:00",
            "simulation": True,
            "realtime": True,
        }
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert world.live_risks["JM-S07"]["category"] == "critical"
    assert "JM-S07" not in world.risks
    # Realtime patches never overwrite the Simulation Mode building record.
    assert world.buildings["B-007"]["status"] == "watch"
    assert world.live_building_patches["B-007"]["status"] == "inspect"
    assert world.live_building_patches["B-007"]["tilt_deg"] == 1.2
    kinds = [m["t"] for m in world.broadcasts]  # type: ignore[attr-defined]
    assert "risk" in kinds and "building" in kinds
    patch = next(m for m in world.broadcasts if m["t"] == "building")  # type: ignore[attr-defined]
    assert patch["realtime"] is True


async def test_incident_create_and_resolve_sync_dashboard_alert():
    world = make_world()
    created = {
        "id": "inc-1",
        "code": "AL-FLOOD-I",
        "hazard": "flood",
        "node_code": "I",
        "severity": "high",
        "status": "open",
        "title": "Waterlogging risk, I",
        "description": "Water level 30 cm",
        "source": "simulation",
        "simulation": True,
        "opened_at": "2026-11-18T10:00:00+00:00",
        "last_update": "2026-11-18T10:00:00+00:00",
        "pos": [74.8567, 32.7290],
    }
    world._on_incident_event("incident.created", created)
    await asyncio.sleep(0)
    alert = world.alerts["AL-FLOOD-I"]
    assert alert["status"] == "new"
    assert alert["module"] == "flood"
    assert alert["target"] == "I"
    assert alert["simulation"] is True

    resolved = {**created, "status": "resolved", "resolved_at": "2026-11-18T10:05:00+00:00", "last_update": "2026-11-18T10:05:00+00:00"}
    world._on_incident_event("incident.resolved", resolved)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert world.alerts["AL-FLOOD-I"]["status"] == "resolved"
    assert world.alerts["AL-FLOOD-I"]["last_update"] == "2026-11-18T10:05:00+00:00"


async def test_incident_update_does_not_downgrade_dispatched_alert():
    world = make_world()
    world.alerts["AL-FIRE-B-014"] = {
        "id": "AL-FIRE-B-014",
        "module": "fire",
        "severity": "high",
        "status": "dispatched",
        "title": "Fire",
        "detail": "",
        "building_id": "B-014",
        "target": "B-014",
        "pos": [74.857, 32.728],
        "confidence": 0.8,
        "sources": [],
        "created_at": 1.0,
        "updated_at": 1.0,
        "simulation": True,
    }
    world._on_incident_event(
        "incident.updated",
        {
            "code": "AL-FIRE-B-014",
            "hazard": "fire",
            "building_id": "b14",
            "severity": "critical",
            "status": "open",
            "title": "Fire escalated",
            "description": "Smoke rising",
            "simulation": True,
            "pos": [74.857, 32.728],
        },
    )
    await asyncio.sleep(0)
    alert = world.alerts["AL-FIRE-B-014"]
    assert alert["severity"] == "critical"
    assert alert["status"] == "dispatched"


async def test_realtime_incident_uses_separate_alert_namespace():
    world = make_world()
    world._on_incident_event(
        "incident.created",
        {
            "code": "AL-FIRE-B-014",
            "hazard": "fire",
            "building_id": "b14",
            "severity": "critical",
            "status": "open",
            "title": "Fire risk, B-014",
            "description": "MQ-2 and flame triggered",
            "device_id": "JURAS-FIRE-001",
            "sensor_code": "JM-014",
            "realtime": True,
            "source": "simulation",
            "simulation": True,
            "opened_at": "2026-11-18T10:00:00+00:00",
            "last_update": "2026-11-18T10:00:00+00:00",
            "pos": [74.857, 32.728],
        },
    )
    await asyncio.sleep(0)

    assert "RT-AL-FIRE-B-014" in world.alerts
    assert world.alerts["RT-AL-FIRE-B-014"]["realtime"] is True
    assert "AL-FIRE-B-014" not in world.alerts

    world._on_incident_event(
        "incident.created",
        {
            "code": "AL-FIRE-B-014",
            "hazard": "fire",
            "building_id": "b14",
            "severity": "high",
            "status": "open",
            "title": "Simulated fire",
            "description": "simulation scenario",
            "source": "simulation",
            "simulation": True,
            "realtime": False,
            "opened_at": "2026-11-18T10:01:00+00:00",
            "last_update": "2026-11-18T10:01:00+00:00",
            "pos": [74.857, 32.728],
        },
    )
    await asyncio.sleep(0)
    assert world.alerts["AL-FIRE-B-014"]["realtime"] is False
    assert world.alerts["RT-AL-FIRE-B-014"]["realtime"] is True


async def test_simulation_reading_never_becomes_realtime():
    world = make_world()
    world._on_reading(
        {
            "sensor_code": "JM-014",
            "device_id": "JURAS-FIRE-001",
            "realtime": False,
            "values": {"smoke_ppm": 800.0, "temp_c": 70.0},
        }
    )
    assert world.live_readings == {}
    assert not any(m["t"] == "live" for m in world.broadcasts)  # type: ignore[attr-defined]


class FakeDbIncident:
    code = "AL-STR-B-007"
    hazard = "structural"
    building_id = "b07"
    node_code = None
    severity = "high"
    status = "acknowledged"
    title = "Structural watch, B-007"
    description = "seeded demo incident"
    source = "simulation"
    simulation_id = None
    opened_at = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
    acknowledged_at = datetime(2026, 11, 18, 9, 30, tzinfo=timezone.utc)
    resolved_at = None
    pos = [74.856, 32.729]


def test_db_seeded_incident_always_stays_in_simulation_mode():
    world = make_world()
    # A live Wokwi reading at the same building must not move the seeded
    # incident into Realtime Mode.
    world.live_readings["JM-S07"] = {
        "ts": now_ms(),
        "values": {"tilt_deg": 2.0, "crack_mm": 2.0},
    }

    alert = world._alert_from_incident(FakeDbIncident())  # type: ignore[arg-type]

    assert alert["id"] == "AL-STR-B-007"
    assert alert["simulation"] is True
    assert alert["realtime"] is False
    assert world._incident_realtime(
        {"code": "AL-STR-B-007", "realtime": False}, "B-007", None
    ) is False
    # Explicit realtime events still reach the realtime namespace.
    assert world._incident_realtime(
        {"code": "AL-FIRE-B-014", "realtime": True}, "B-014", None
    ) is True


class FakeManager:
    async def shutdown(self) -> None:
        pass


class FakeSession:
    async def execute(self, *args, **kwargs) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeSessionFactory:
    def __call__(self) -> "FakeSessionFactory":
        return self

    async def __aenter__(self) -> FakeSession:
        return FakeSession()

    async def __aexit__(self, *args) -> bool:
        return False


async def test_reset_world_restores_seeded_incidents_and_keeps_realtime():
    world = make_world()
    world.manager = FakeManager()  # type: ignore[assignment]
    world.session_factory = FakeSessionFactory()  # type: ignore[assignment]
    seeded = {
        "id": "AL-STR-B-007",
        "module": "structure",
        "status": "ack",
        "severity": "medium",
        "building_id": "B-007",
        "pos": [74.856, 32.729],
        "created_at": 1.0,
        "updated_at": 2.0,
        "realtime": False,
        "simulation": True,
    }
    world.seed_alerts = {"AL-STR-B-007": dict(seeded)}
    world.alerts = {
        "AL-STR-B-007": dict(seeded),
        "AL-FIRE-B-021": {**seeded, "id": "AL-FIRE-B-021", "module": "fire"},
        "RT-AL-FIRE-B-014": {
            **seeded,
            "id": "RT-AL-FIRE-B-014",
            "module": "fire",
            "realtime": True,
        },
    }

    await world.reset_world()

    assert "AL-STR-B-007" in world.alerts
    assert world.alerts["AL-STR-B-007"]["realtime"] is False
    # In-session simulation incident is cleared by the reset.
    assert "AL-FIRE-B-021" not in world.alerts
    # Realtime state survives the simulation reset.
    assert "RT-AL-FIRE-B-014" in world.alerts
    assert world.alerts["RT-AL-FIRE-B-014"]["realtime"] is True
    snapshot = world.broadcasts[-1]  # type: ignore[attr-defined]
    assert snapshot["t"] == "snapshot"
    assert "AL-STR-B-007" in {a["id"] for a in snapshot["alerts"]}
