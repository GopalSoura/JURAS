import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Simulation
from app.core.constants import SimulationStatus


async def insert(session: AsyncSession, sim: Simulation) -> Simulation:
    session.add(sim)
    await session.flush()
    return sim


async def get(session: AsyncSession, sim_id: str) -> Simulation | None:
    try:
        uid = uuid.UUID(sim_id)
    except ValueError:
        return None
    result = await session.execute(select(Simulation).where(Simulation.id == uid))
    return result.scalar_one_or_none()


async def list_by_status(session: AsyncSession, status: str | None = None) -> list[Simulation]:
    stmt = select(Simulation).order_by(Simulation.started_at.desc().nullslast()).limit(100)
    if status:
        stmt = stmt.where(Simulation.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_active(session: AsyncSession) -> int:
    result = await session.execute(
        select(Simulation).where(Simulation.status == SimulationStatus.running.value)
    )
    return len(list(result.scalars().all()))


async def active_for_target(
    session: AsyncSession, building_id: uuid.UUID, scenario: str
) -> Simulation | None:
    result = await session.execute(
        select(Simulation)
        .where(
            Simulation.target_building_id == building_id,
            Simulation.scenario == scenario,
            Simulation.status == SimulationStatus.running.value,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()
