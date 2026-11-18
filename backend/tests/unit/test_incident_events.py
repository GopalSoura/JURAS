from datetime import datetime, timezone

from app.repositories.incident_repo import incident_out
from app.services.incident_service import transition


class FakeSession:
    def add(self, obj) -> None:
        pass

    async def flush(self) -> None:
        pass


class FakeIncident:
    def __init__(self, status: str = "acknowledged") -> None:
        now = datetime.now(timezone.utc)
        self.id = "inc-1"
        self.code = "AL-FLOOD-I"
        self.hazard = "flood"
        self.building_id = None
        self.node_code = "I"
        self.severity = "high"
        self.status = status
        self.title = "Waterlogging risk, I"
        self.description = "demo"
        self.source = "simulation"
        self.simulation_id = None
        self.opened_at = now
        self.acknowledged_at = now
        self.resolved_at = None
        self.pos = [74.8567, 32.7290]


async def test_resolving_emits_incident_resolved_not_updated():
    inc = FakeIncident()
    events: list[tuple[str, dict]] = []

    await transition(FakeSession(), inc, "resolved", "operator:ui", "Resolved", events)

    assert inc.status == "resolved"
    assert [name for name, _ in events] == ["incident.resolved"]
    payload = events[0][1]
    assert payload["code"] == "AL-FLOOD-I"
    assert payload["status"] == "resolved"
    assert payload["simulation"] is True
    assert payload["last_update"] == payload["resolved_at"]


def test_incident_payload_has_target_and_update_time():
    out = incident_out(FakeIncident("open"))
    assert out["node_code"] == "I"
    assert out["last_update"] is not None
    assert out["simulation"] is True
