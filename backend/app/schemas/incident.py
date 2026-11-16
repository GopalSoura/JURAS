from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator


class IncidentPatch(BaseModel):
    status: str
    note: str = ""
    actor: str = "operator"

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in ("acknowledged", "resolved", "false_alarm"):
            raise ValueError("status must be one of acknowledged, resolved, false_alarm")
        return v


class IncidentEventOut(BaseModel):
    id: str
    action: str
    old_status: str | None
    new_status: str | None
    actor: str
    note: str
    created_at: str


class IncidentOut(BaseModel):
    id: str
    code: str
    hazard: str
    building_id: str | None
    node_code: str | None
    severity: str
    status: str
    title: str
    description: str
    source: str
    simulation_id: str | None
    opened_at: str
    acknowledged_at: str | None
    resolved_at: str | None
    pos: list[float]


class IncidentFeature(BaseModel):
    type: str = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any]


class IncidentCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[IncidentFeature]


class IncidentDetail(BaseModel):
    incident: IncidentOut
    events: list[IncidentEventOut]
