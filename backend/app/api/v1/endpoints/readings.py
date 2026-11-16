from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory, get_session
from app.repositories import reading_repo
from app.schemas.reading import ReadingCreate
from app.services.reading_service import ingest
from app.realtime.bus import bus

router = APIRouter(prefix="/readings", tags=["readings"])


@router.get("/latest")
async def latest_readings(
    building_id: str | None = Query(default=None),
    sensor_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.repositories import building_repo

    if not building_id:
        return {"readings": []}
    building = await building_repo.get_by_id(session, building_id)
    if building is None:
        return {"readings": []}
    readings = await reading_repo.latest_per_kind_for_building(session, building.id)
    items = []
    for hazard, r in readings.items():
        if sensor_type and r.hazard != sensor_type:
            continue
        items.append(reading_repo.reading_out(r))
    return {"readings": items, "simulation": True}


@router.get("")
async def list_readings(
    building_id: str | None = Query(default=None),
    sensor_id: str | None = Query(default=None),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.repositories import building_repo, sensor_repo

    eff_building: str | None = None
    if building_id:
        b = await building_repo.get_by_id(session, building_id)
        if b is None:
            return {"items": [], "limit": limit, "simulation": True}
        eff_building = str(b.id)
    eff_sensor: str | None = None
    if sensor_id:
        s = await sensor_repo.get_by_id(session, sensor_id)
        if s is None:
            return {"items": [], "limit": limit, "simulation": True}
        eff_sensor = str(s.id)
    readings = await reading_repo.list_for(
        session, building_id=eff_building, sensor_id=eff_sensor, from_ts=from_ts, to_ts=to_ts, limit=limit
    )
    return {
        "items": [reading_repo.reading_out(r) for r in readings],
        "limit": limit,
        "simulation": True,
    }


@router.post("", status_code=201)
async def create_reading(payload: ReadingCreate) -> dict:
    async with SessionFactory() as session:
        result = await ingest(session, payload.model_dump())
        await session.commit()
    events = result.pop("events", [])
    for name, data in events:
        await bus.broadcast_event(name, data)
    return result
