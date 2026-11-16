from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class BuildingFeature(BaseModel):
    type: str = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any]


class BuildingCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[BuildingFeature]
    label: str = "illustrative demo data"


class BuildingDetail(BaseModel):
    id: str
    code: str
    name: str
    floors: int
    building_type: str
    construction: str
    occupancy: int
    year_built: int
    height_m: float
    priority: int
    status: str
    center: list[float]
    footprint: list[list[float]]
    access_node: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    latest_reading: dict[str, Any] | None = None
    latest_risk: dict[str, Any] | None = None
