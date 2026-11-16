import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, utcnow


class Reading(UUIDMixin, Base):
    __tablename__ = "readings"

    sensor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sensors.id"), nullable=True
    )
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id"), nullable=True
    )
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=True
    )
    hazard: Mapped[str] = mapped_column(String(32), nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), default="simulation")
    simulation: Mapped[bool] = mapped_column(Boolean, default=True)


Index("ix_readings_sensor_observed", Reading.sensor_id, Reading.observed_at)
Index("ix_readings_building_observed", Reading.building_id, Reading.observed_at)
