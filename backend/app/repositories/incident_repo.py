import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Incident, IncidentEvent
from app.core.constants import IncidentStatus


async def insert(session: AsyncSession, incident: Incident) -> Incident:
    session.add(incident)
    await session.flush()
    return incident


async def add_event(session: AsyncSession, event: IncidentEvent) -> IncidentEvent:
    session.add(event)
    await session.flush()
    return event


async def get(session: AsyncSession, incident_id: str) -> Incident | None:
    try:
        uid = uuid.UUID(incident_id)
    except ValueError:
        return await get_by_code(session, incident_id)
    result = await session.execute(select(Incident).where(Incident.id == uid))
    return result.scalar_one_or_none()


async def get_by_code(session: AsyncSession, code: str) -> Incident | None:
    result = await session.execute(select(Incident).where(Incident.code == code))
    return result.scalar_one_or_none()


async def find_active(
    session: AsyncSession,
    building_id: uuid.UUID | None,
    node_code: str | None,
    hazard: str,
) -> Incident | None:
    stmt = select(Incident).where(
        Incident.hazard == hazard,
        Incident.status.in_([IncidentStatus.open.value, IncidentStatus.acknowledged.value]),
    )
    if building_id is not None:
        stmt = stmt.where(Incident.building_id == building_id)
    elif node_code is not None:
        stmt = stmt.where(Incident.node_code == node_code)
    else:
        stmt = stmt.where(Incident.building_id.is_(None), Incident.node_code.is_(None))
    result = await session.execute(stmt.limit(1))
    return result.scalar_one_or_none()


async def list_incidents(
    session: AsyncSession,
    status: str | None = None,
    hazard: str | None = None,
    severity: str | None = None,
) -> list[Incident]:
    stmt = select(Incident).order_by(Incident.opened_at.desc()).limit(200)
    if status:
        stmt = stmt.where(Incident.status == status)
    if hazard:
        stmt = stmt.where(Incident.hazard == hazard)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def events_for(session: AsyncSession, incident_id: uuid.UUID) -> list[IncidentEvent]:
    result = await session.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at)
    )
    return list(result.scalars().all())


def incident_out(i: Incident) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "code": i.code,
        "hazard": i.hazard,
        "building_id": str(i.building_id) if i.building_id else None,
        "node_code": i.node_code,
        "severity": i.severity,
        "status": i.status,
        "title": i.title,
        "description": i.description,
        "source": i.source,
        "simulation_id": str(i.simulation_id) if i.simulation_id else None,
        "opened_at": i.opened_at.isoformat(),
        "acknowledged_at": i.acknowledged_at.isoformat() if i.acknowledged_at else None,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        "pos": i.pos,
    }


def event_out(e: IncidentEvent) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "action": e.action,
        "old_status": e.old_status,
        "new_status": e.new_status,
        "actor": e.actor,
        "note": e.note,
        "created_at": e.created_at.isoformat(),
    }


def incident_feature(i: Incident) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": i.code,
        "geometry": {"type": "Point", "coordinates": i.pos},
        "properties": {
            "id": str(i.id),
            "code": i.code,
            "hazard": i.hazard,
            "severity": i.severity,
            "status": i.status,
            "title": i.title,
            "simulation": i.source == "simulation",
        },
    }
