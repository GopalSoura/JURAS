from typing import Any
from pydantic import BaseModel


class SensorOut(BaseModel):
    id: str
    code: str
    label: str
    kind: str
    building_id: str | None = None
    node_code: str | None = None
    status: str
    source: str
    pos: list[float]
    attributes: dict[str, Any] = {}
