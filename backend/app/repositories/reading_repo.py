import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reading


async def insert(session: AsyncSession, reading: Reading) -> Reading:
    session.add(reading)
    await session.flush()
    return reading


async def latest_for_sensor(session: AsyncSession, sensor_id: uuid.UUID) -> Reading | None:
    result = await session.execute(
        select(Reading).where(Reading.sensor_id == sensor_id).order_by(desc(Reading.observed_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def latest_per_kind_for_building(
    session: AsyncSession, building_id: uuid.UUID
) -> dict[str, Reading]:
    result = await session.execute(
        select(Reading)
        .where(Reading.building_id == building_id)
        .order_by(desc(Reading.observed_at))
        .limit(50)
    )
    out: dict[str, Reading] = {}
    for r in result.scalars().all():
        if r.hazard not in out:
            out[r.hazard] = r
    return out


async def list_for(
    session: AsyncSession,
    building_id: str | None = None,
    sensor_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 200,
) -> list[Reading]:
    stmt = select(Reading).order_by(desc(Reading.observed_at)).limit(min(limit, 1000))
    if building_id:
        try:
            stmt = stmt.where(Reading.building_id == uuid.UUID(building_id))
        except ValueError:
            return []
    if sensor_id:
        try:
            stmt = stmt.where(Reading.sensor_id == uuid.UUID(sensor_id))
        except ValueError:
            return []
    if from_ts:
        stmt = stmt.where(Reading.observed_at >= from_ts)
    if to_ts:
        stmt = stmt.where(Reading.observed_at <= to_ts)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def reading_out(r: Reading) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "sensor_id": str(r.sensor_id) if r.sensor_id else None,
        "building_id": str(r.building_id) if r.building_id else None,
        "simulation_id": str(r.simulation_id) if r.simulation_id else None,
        "hazard": r.hazard,
        "values": r.values,
        "observed_at": r.observed_at.isoformat(),
        "received_at": r.received_at.isoformat(),
        "source": r.source,
        "simulation": r.simulation,
    }
