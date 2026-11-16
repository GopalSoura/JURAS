from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lane, LaneNode


async def list_nodes(session: AsyncSession) -> list[LaneNode]:
    result = await session.execute(select(LaneNode).order_by(LaneNode.code))
    return list(result.scalars().all())


async def list_lanes(
    session: AsyncSession,
    blocked: bool | None = None,
    accessible_to: str | None = None,
    source: str | None = None,
) -> list[Lane]:
    stmt = select(Lane)
    if blocked is not None:
        stmt = stmt.where(Lane.blocked == blocked)
    if accessible_to == "foot_responder":
        stmt = stmt.where(Lane.width_m >= 0.9)
    elif accessible_to == "ambulance":
        stmt = stmt.where(Lane.width_m >= 1.2, Lane.stairs.is_(False))
    elif accessible_to == "fire_vehicle":
        stmt = stmt.where(Lane.width_m >= 3.5, Lane.stairs.is_(False))
    if source:
        stmt = stmt.where(func.coalesce(Lane.attributes.op("->>")("source"), "demo") == source)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_node_by_code(session: AsyncSession, code: str) -> LaneNode | None:
    result = await session.execute(select(LaneNode).where(LaneNode.code == code))
    return result.scalar_one_or_none()


async def get_lane_by_code(session: AsyncSession, code: str) -> Lane | None:
    result = await session.execute(select(Lane).where(Lane.code == code))
    return result.scalar_one_or_none()


def node_feature(n: LaneNode) -> dict:
    return {
        "type": "Feature",
        "id": n.code,
        "geometry": {"type": "Point", "coordinates": n.pos},
        "properties": {"id": n.code, "label": n.label, "kind": n.kind, "simulation": True},
    }


def lane_feature(l: Lane) -> dict:
    src = (l.attributes or {}).get("source") or "demo"
    return {
        "type": "Feature",
        "id": l.code,
        "geometry": {"type": "LineString", "coordinates": l.path},
        "properties": {
            "id": l.code,
            "name": l.name,
            "width_m": l.width_m,
            "stairs": l.stairs,
            "slope_pct": l.slope_pct,
            "vehicle_access": l.vehicle_access,
            "blocked": l.blocked,
            "surface": l.surface,
            "length_m": l.length_m,
            "node_a": l.node_a_code,
            "node_b": l.node_b_code,
            "simulation": src == "demo",
            "source": src,
            "label": "OpenStreetMap import, widths not field-verified" if src == "osm" else "illustrative demo data",
        },
    }
