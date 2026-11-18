from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import SessionFactory, get_session
from app.realtime.bus import bus
from app.repositories import incident_repo
from app.schemas.incident import IncidentPatch
from app.services.incident_service import transition

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("")
async def list_incidents(
    status: str | None = Query(default=None),
    hazard: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    format: str | None = Query(default="json"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    incidents = await incident_repo.list_incidents(session, status=status, hazard=hazard, severity=severity)
    if format == "geojson":
        return {
            "type": "FeatureCollection",
            "features": [incident_repo.incident_feature(i) for i in incidents],
        }
    return {"items": [incident_repo.incident_out(i) for i in incidents]}


@router.get("/{incident_id}")
async def get_incident(incident_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    incident = await incident_repo.get(session, incident_id)
    if incident is None:
        raise NotFoundError("INCIDENT_NOT_FOUND", f"Incident {incident_id} does not exist")
    events = await incident_repo.events_for(session, incident.id)
    return {
        "incident": incident_repo.incident_out(incident),
        "events": [incident_repo.event_out(e) for e in events],
    }


@router.patch("/{incident_id}")
async def patch_incident(incident_id: str, payload: IncidentPatch) -> dict:
    events: list[tuple[str, dict]] = []
    async with SessionFactory() as session:
        incident = await incident_repo.get(session, incident_id)
        if incident is None:
            raise NotFoundError("INCIDENT_NOT_FOUND", f"Incident {incident_id} does not exist")
        await transition(session, incident, payload.status, payload.actor, payload.note, events)
        await session.commit()
        out = incident_repo.incident_out(incident)
    for name, data in events:
        await bus.broadcast_event(
            name, data, simulation=bool(data.get("simulation", True))
        )
    return out


@router.get("/{incident_id}/events")
async def get_incident_events(incident_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    incident = await incident_repo.get(session, incident_id)
    if incident is None:
        raise NotFoundError("INCIDENT_NOT_FOUND", f"Incident {incident_id} does not exist")
    events = await incident_repo.events_for(session, incident.id)
    return {"items": [incident_repo.event_out(e) for e in events]}
