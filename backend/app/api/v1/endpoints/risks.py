from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories import risk_repo

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get("")
async def list_risks(
    entity_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    bbox: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    assessments = await risk_repo.list_assessments(session)
    items = []
    seen: set[str] = set()
    for r in assessments:
        key = f"{r.entity_type}:{r.entity_id}:{r.hazard}"
        if key in seen:
            continue
        seen.add(key)
        if entity_type and r.entity_type != entity_type:
            continue
        if category and r.category != category:
            continue
        items.append(risk_repo.assessment_out(r))
    return {"items": items, "rule_version": "demo-v1", "label": "Illustrative demo scores, not calibrated probability"}
