from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RiskCategory
from app.core.exceptions import NotFoundError
from app.db.session import get_session
from app.repositories import building_repo, reading_repo, risk_repo
from app.schemas.building import BuildingDetail
from app.services import gis_service

router = APIRouter(prefix="/buildings", tags=["buildings"])


@router.get("")
async def list_buildings(
    bbox: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    source: str | None = Query(default=None, pattern="^(demo|osm)$"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await gis_service.buildings_geojson(session, bbox=bbox, limit=limit, source=source)


@router.get("/{building_id}")
async def get_building(building_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    building = await building_repo.get_by_id(session, building_id)
    if building is None:
        raise NotFoundError("BUILDING_NOT_FOUND", f"Building {building_id} does not exist")
    readings = await reading_repo.latest_per_kind_for_building(session, building.id)
    latest_risk = await risk_repo.latest_for_entity(session, "building", building.id)
    latest_reading = None
    if readings:
        r = next(iter(readings.values()))
        latest_reading = reading_repo.reading_out(r)
    src = (building.attributes or {}).get("source") or "demo"
    return {
        "id": str(building.id),
        "code": building.code,
        "name": building.name,
        "floors": building.floors,
        "building_type": building.building_type,
        "construction": building.construction,
        "occupancy": building.occupancy,
        "year_built": building.year_built,
        "height_m": building.height_m,
        "priority": building.priority,
        "status": building.status,
        "center": building.center,
        "footprint": building.footprint,
        "access_node": building.access_node_code,
        "attributes": building.attributes or {},
        "latest_reading": latest_reading,
        "latest_risk": risk_repo.assessment_out(latest_risk) if latest_risk else None,
        "simulation": src == "demo",
        "source": src,
        "label": "OpenStreetMap import, geometry not field-verified" if src == "osm" else "illustrative demo data",
    }
