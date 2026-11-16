import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    IncidentStatus,
    RiskCategory,
    CATEGORY_TO_SEVERITY,
)
from app.models import Incident, IncidentEvent, Building
from app.repositories import incident_repo

logger = logging.getLogger("juras.incident")

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

ALLOWED_TRANSITIONS = {
    IncidentStatus.open.value: {
        IncidentStatus.acknowledged.value,
        IncidentStatus.resolved.value,
        IncidentStatus.false_alarm.value,
    },
    IncidentStatus.acknowledged.value: {
        IncidentStatus.resolved.value,
        IncidentStatus.false_alarm.value,
    },
    IncidentStatus.resolved.value: set(),
    IncidentStatus.false_alarm.value: set(),
}

HAZARD_PREFIX = {"fire": "FIRE", "flood": "FLOOD", "structural": "STR"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _next_code(session: AsyncSession, hazard: str, target: str) -> str:
    base = f"AL-{HAZARD_PREFIX.get(hazard, hazard.upper())}-{target}"
    existing = await incident_repo.get_by_code(session, base)
    if existing is None:
        return base
    n = 2
    while await incident_repo.get_by_code(session, f"{base}-{n}") is not None:
        n += 1
    return f"{base}-{n}"


async def upsert_for_risk(
    session: AsyncSession,
    hazard: str,
    category: str,
    building: Building | None,
    node_code: str | None,
    pos: list[float],
    simulation_id: str | None,
    source: str,
    reasons: list[dict[str, Any]],
    events_out: list[tuple[str, dict[str, Any]]],
) -> tuple[Incident | None, bool]:
    if category not in (RiskCategory.high.value, RiskCategory.critical.value):
        return None, False
    target = building.code if building else (node_code or "AREA")
    building_id = building.id if building else None
    existing = await incident_repo.find_active(session, building_id, node_code, hazard)
    severity = CATEGORY_TO_SEVERITY[RiskCategory(category)].value
    if existing is not None:
        if SEVERITY_ORDER.get(severity, 0) > SEVERITY_ORDER.get(existing.severity, 0):
            old = existing.severity
            existing.severity = severity
            await incident_repo.add_event(
                session,
                IncidentEvent(
                    incident_id=existing.id,
                    action="severity_escalated",
                    old_status=old,
                    new_status=severity,
                    actor="risk_engine",
                    note=f"Risk escalated from {old} to {severity}",
                ),
            )
            events_out.append(
                ("incident.updated", incident_repo.incident_out(existing) | {"escalated": True})
            )
        return existing, False
    code = await _next_code(session, hazard, target)
    title = _title(hazard, target, severity)
    incident = Incident(
        code=code,
        hazard=hazard,
        building_id=building_id,
        node_code=node_code,
        severity=severity,
        status=IncidentStatus.open.value,
        title=title,
        description=_description(hazard, reasons),
        source=source,
        simulation_id=None if simulation_id is None else _uuid_or_none(simulation_id),
        opened_at=now_utc(),
        pos=pos,
        geom=func.ST_GeomFromText(f"POINT({float(pos[0]):.8f} {float(pos[1]):.8f})", 4326),
    )
    await incident_repo.insert(session, incident)
    await incident_repo.add_event(
        session,
        IncidentEvent(
            incident_id=incident.id,
            action="opened",
            old_status=None,
            new_status=IncidentStatus.open.value,
            actor="risk_engine",
            note=title,
        ),
    )
    events_out.append(("incident.created", incident_repo.incident_out(incident)))
    return incident, True


def _title(hazard: str, target: str, severity: str) -> str:
    labels = {
        "fire": f"Fire risk, {target}",
        "flood": f"Waterlogging risk, {target}",
        "structural": f"Structural deviation, {target}",
    }
    return labels.get(hazard, f"{hazard} risk, {target}")


def _description(hazard: str, reasons: list[dict[str, Any]]) -> str:
    rule_text = "; ".join(r.get("text", "") for r in reasons[:3])
    demo = "Illustrative demo rule. Not a certified safety judgment."
    return f"{hazard} risk crossed demo thresholds. Rules: {rule_text}. {demo}"


def _uuid_or_none(value: str | None):
    if value is None:
        return None
    import uuid as _uuid

    try:
        return _uuid.UUID(value)
    except ValueError:
        return None


async def transition(
    session: AsyncSession,
    incident: Incident,
    new_status: str,
    actor: str,
    note: str,
    events_out: list[tuple[str, dict[str, Any]]],
) -> Incident:
    old = incident.status
    if new_status == old:
        return incident
    allowed = ALLOWED_TRANSITIONS.get(old, set())
    if new_status not in allowed:
        from app.core.exceptions import ValidationAppError

        raise ValidationAppError(
            code="INVALID_TRANSITION",
            message=f"Cannot move incident from {old} to {new_status}",
        )
    incident.status = new_status
    ts = now_utc()
    if new_status == IncidentStatus.acknowledged.value:
        incident.acknowledged_at = ts
    elif new_status in (IncidentStatus.resolved.value, IncidentStatus.false_alarm.value):
        incident.resolved_at = ts
    await incident_repo.add_event(
        session,
        IncidentEvent(
            incident_id=incident.id,
            action="status_changed",
            old_status=old,
            new_status=new_status,
            actor=actor,
            note=note,
        ),
    )
    events_out.append(("incident.updated", incident_repo.incident_out(incident)))
    return incident
