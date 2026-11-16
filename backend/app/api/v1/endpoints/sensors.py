from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories import sensor_repo

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("")
async def list_sensors(
    building_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    sensors = await sensor_repo.list_sensors(session, building_id=building_id, kind=type, status=status)
    return [
        {
            "id": str(s.id),
            "code": s.code,
            "label": s.label,
            "kind": s.kind,
            "building_id": str(s.building_id) if s.building_id else None,
            "node_code": s.node_code,
            "status": s.status,
            "source": s.source,
            "pos": s.pos,
            "attributes": s.attributes or {},
            "simulation": True,
        }
        for s in sensors
    ]
