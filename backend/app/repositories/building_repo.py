import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Building


def _bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    parts = [float(p) for p in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minlon,minlat,maxlon,maxlat")
    return parts[0], parts[1], parts[2], parts[3]


def source_of(row: Building) -> str:
    return ((row.attributes or {}).get("source") or "demo")


async def list_buildings(
    session: AsyncSession, bbox: str | None = None, limit: int = 200, source: str | None = None
) -> list[Building]:
    box = _bbox(bbox)
    if box:
        stmt = (
            select(Building)
            .where(
                func.ST_Intersects(
                    Building.geom,
                    func.ST_MakeEnvelope(box[0], box[1], box[2], box[3], 4326),
                )
            )
            .limit(min(limit, 500))
        )
    else:
        stmt = select(Building).limit(min(limit, 500))
    if source:
        stmt = stmt.where(
            func.coalesce(Building.attributes.op("->>")("source"), "demo") == source
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, building_id: str) -> Building | None:
    try:
        uid = uuid.UUID(building_id)
    except ValueError:
        return await get_by_code(session, building_id)
    result = await session.execute(select(Building).where(Building.id == uid))
    return result.scalar_one_or_none()


async def get_by_code(session: AsyncSession, code: str) -> Building | None:
    result = await session.execute(select(Building).where(Building.code == code))
    return result.scalar_one_or_none()


async def nearest_node_for_building(session: AsyncSession, building: Building) -> str | None:
    return building.access_node_code


def building_feature(b: Building, latest_risk: dict[str, Any] | None = None) -> dict[str, Any]:
    src = source_of(b)
    props = {
        "id": b.code,
        "name": b.name,
        "floors": b.floors,
        "building_type": b.building_type,
        "construction": b.construction,
        "occupancy": b.occupancy,
        "year_built": b.year_built,
        "height_m": b.height_m,
        "priority": b.priority,
        "status": b.status,
        "center": b.center,
        "access_node": b.access_node_code,
        "simulation": src == "demo",
        "source": src,
        "label": "OpenStreetMap import, geometry not field-verified" if src == "osm" else "illustrative demo data",
    }
    if latest_risk:
        props["risk"] = latest_risk
    return {"type": "Feature", "id": b.code, "geometry": {"type": "Polygon", "coordinates": [b.footprint]}, "properties": props}
