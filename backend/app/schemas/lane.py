from typing import Any
from pydantic import BaseModel


class LaneFeature(BaseModel):
    type: str = "Feature"
    id: str
    geometry: dict[str, Any]
    properties: dict[str, Any]


class LaneCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[LaneFeature]
    label: str = "illustrative demo data"
