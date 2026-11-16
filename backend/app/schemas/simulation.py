from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class SimulationCreate(BaseModel):
    scenario: str
    target_building_id: str | None = None
    target_node_code: str | None = None
    severity: str = "warning"
    duration_sec: int = Field(default=60, ge=5, le=300)
    interval_ms: int = Field(default=2000, ge=500, le=10000)
    seed: int | None = None
    actor: str = "dashboard"

    @field_validator("scenario")
    @classmethod
    def check_scenario(cls, v: str) -> str:
        if v not in ("fire", "flood", "structural"):
            raise ValueError("scenario must be one of fire, flood, structural")
        return v

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v: str) -> str:
        if v not in ("normal", "warning", "critical"):
            raise ValueError("severity must be one of normal, warning, critical")
        return v


class SimulationOut(BaseModel):
    id: str
    scenario: str
    status: str
    severity: str
    seed: int
    interval_ms: int
    duration_sec: int
    target_building_id: str | None
    target_node_code: str | None
    started_at: str | None
    ended_at: str | None
    elapsed_sec: float = 0
    actor: str = "dashboard"
    error_code: str | None = None
