from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import gis_service

router = APIRouter(prefix="/lanes", tags=["lanes"])


@router.get("")
async def list_lanes(
    bbox: str | None = Query(default=None),
    blocked: bool | None = Query(default=None),
    accessible_to: str | None = Query(default=None),
    source: str | None = Query(default=None, pattern="^(demo|osm)$"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await gis_service.lanes_geojson(session, blocked=blocked, accessible_to=accessible_to, source=source)


@router.get("/nodes")
async def list_nodes(
    source: str | None = Query(default=None, pattern="^(demo|osm)$"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await gis_service.nodes_geojson(session, source=source)
