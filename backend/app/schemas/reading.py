from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator


class ReadingCreate(BaseModel):
    sensor_id: str | None = None
    building_id: str | None = None
    simulation_id: str | None = None
    hazard: str = Field(default="fire")
    values: dict[str, float] = Field(default_factory=dict)
    observed_at: datetime | None = None
    source: str = "simulation"
    simulation: bool = True

    @field_validator("hazard")
    @classmethod
    def check_hazard(cls, v: str) -> str:
        if v not in ("fire", "flood", "structural"):
            raise ValueError("hazard must be one of fire, flood, structural")
        return v

    @field_validator("source")
    @classmethod
    def check_source(cls, v: str) -> str:
        if v not in ("simulation", "field", "imported"):
            raise ValueError("source must be one of simulation, field, imported")
        return v

    @field_validator("values")
    @classmethod
    def check_values(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("values must not be empty")
        return v


class ReadingOut(BaseModel):
    id: str
    sensor_id: str | None
    building_id: str | None
    simulation_id: str | None
    hazard: str
    values: dict[str, Any]
    observed_at: str
    received_at: str
    source: str
    simulation: bool


class ReadingIngestResult(BaseModel):
    id: str
    accepted: bool
    risk: dict[str, Any] | None = None
    incident_id: str | None = None
    incident_created: bool = False
