import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, UUIDMixin


class Simulation(UUIDMixin, Base):
    __tablename__ = "simulations"

    scenario: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_building_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id"), nullable=True, index=True
    )
    target_node_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_sensor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sensors.id"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    seed: Mapped[int] = mapped_column(Integer, default=42)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    interval_ms: Mapped[int] = mapped_column(Integer, default=2000)
    duration_sec: Mapped[int] = mapped_column(Integer, default=60)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actor: Mapped[str] = mapped_column(String(64), default="dashboard")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
