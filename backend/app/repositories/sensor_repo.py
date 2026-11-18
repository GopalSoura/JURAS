import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sensor


async def list_sensors(
    session: AsyncSession,
    building_id: str | None = None,
    kind: str | None = None,
    status: str | None = None,
) -> list[Sensor]:
    stmt = select(Sensor)
    if building_id:
        try:
            uid = uuid.UUID(building_id)
            stmt = stmt.where(Sensor.building_id == uid)
        except ValueError:
            b = await session.execute(
                select(Sensor).where(Sensor.building_id == uuid.UUID(int=0))
            )
            return []
    if kind:
        stmt = stmt.where(Sensor.kind == kind)
    if status:
        stmt = stmt.where(Sensor.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, sensor_id: str) -> Sensor | None:
    try:
        uid = uuid.UUID(sensor_id)
    except ValueError:
        return await get_by_code(session, sensor_id)
    result = await session.execute(select(Sensor).where(Sensor.id == uid))
    return result.scalar_one_or_none()


async def get_by_code(session: AsyncSession, code: str) -> Sensor | None:
    result = await session.execute(select(Sensor).where(Sensor.code == code))
    return result.scalar_one_or_none()


async def find_for_building(session: AsyncSession, building_id: uuid.UUID, kind: str) -> Sensor | None:
    result = await session.execute(
        select(Sensor).where(Sensor.building_id == building_id, Sensor.kind == kind).limit(1)
    )
    return result.scalar_one_or_none()


async def find_for_node(session: AsyncSession, node_code: str, kind: str) -> Sensor | None:
    result = await session.execute(
        select(Sensor).where(Sensor.node_code == node_code, Sensor.kind == kind).limit(1)
    )
    return result.scalar_one_or_none()
