from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationAppError
from app.services.incident_service import ALLOWED_TRANSITIONS, transition


class FakeSession:
    def add(self, obj) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, obj) -> None:
        pass


from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)


def incident(status: str = "open"):
    return SimpleNamespace(
        id="i1", status=status, acknowledged_at=None, resolved_at=None,
        code="AL-FIRE-B-001", severity="high", hazard="fire", building_id=None,
        node_code=None, title="t", description="d", source="manual",
        simulation_id=None, opened_at=NOW, pos=[0.0, 0.0],
    )


async def test_open_to_acknowledged_allowed():
    inc = incident()
    await transition(FakeSession(), inc, "acknowledged", "op", "note", [])
    assert inc.status == "acknowledged"
    assert inc.acknowledged_at is not None


async def test_acknowledged_to_resolved_allowed():
    inc = incident("acknowledged")
    await transition(FakeSession(), inc, "resolved", "op", "note", [])
    assert inc.status == "resolved"
    assert inc.resolved_at is not None


async def test_resolved_is_terminal():
    assert ALLOWED_TRANSITIONS["resolved"] == set()
    with pytest.raises(ValidationAppError):
        await transition(FakeSession(), incident("resolved"), "acknowledged", "op", "note", [])


async def test_open_to_false_alarm_allowed():
    inc = incident()
    await transition(FakeSession(), inc, "false_alarm", "op", "note", [])
    assert inc.status == "false_alarm"


async def test_no_status_change_no_error():
    inc = incident()
    await transition(FakeSession(), inc, "open", "op", "note", [])
    assert inc.status == "open"


async def test_same_status_rejected_when_not_allowed():
    with pytest.raises(ValidationAppError):
        await transition(FakeSession(), incident("acknowledged"), "open", "op", "note", [])

