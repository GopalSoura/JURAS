import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskAssessment


async def insert(session: AsyncSession, ra: RiskAssessment) -> RiskAssessment:
    session.add(ra)
    await session.flush()
    return ra


async def latest_for_entity(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> RiskAssessment | None:
    result = await session.execute(
        select(RiskAssessment)
        .where(RiskAssessment.entity_type == entity_type, RiskAssessment.entity_id == entity_id)
        .order_by(RiskAssessment.assessed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def latest_map(session: AsyncSession) -> dict[uuid.UUID, RiskAssessment]:
    result = await session.execute(
        select(RiskAssessment).order_by(RiskAssessment.assessed_at.desc()).limit(200)
    )
    out: dict[uuid.UUID, RiskAssessment] = {}
    for r in result.scalars().all():
        if r.entity_id not in out:
            out[r.entity_id] = r
    return out


async def list_assessments(session: AsyncSession) -> list[RiskAssessment]:
    result = await session.execute(
        select(RiskAssessment).order_by(RiskAssessment.assessed_at.desc()).limit(200)
    )
    return list(result.scalars().all())


def assessment_out(r: RiskAssessment) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "entity_type": r.entity_type,
        "entity_id": str(r.entity_id),
        "entity_code": r.entity_code,
        "hazard": r.hazard,
        "score": r.score,
        "category": r.category,
        "reasons": r.reasons,
        "assessed_at": r.assessed_at.isoformat() if r.assessed_at else None,
        "simulation_id": str(r.simulation_id) if r.simulation_id else None,
        "rule_version": r.rule_version,
    }
