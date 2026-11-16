from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class Envelope(BaseModel):
    event_id: str
    event: str
    version: int = 1
    occurred_at: str
    simulation: bool = True
    data: dict[str, Any] = Field(default_factory=dict)


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    next_cursor: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
