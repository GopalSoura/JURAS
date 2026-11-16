from datetime import datetime
from typing import Any
from pydantic import BaseModel


class RiskOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    entity_code: str
    hazard: str
    score: int
    category: str
    reasons: list[dict[str, Any]]
    assessed_at: str
    simulation_id: str | None = None
    rule_version: str = "demo-v1"
