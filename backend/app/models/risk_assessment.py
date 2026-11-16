import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, UUIDMixin


class RiskAssessment(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "risk_assessments"

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_code: Mapped[str] = mapped_column(String(64), nullable=False)
    hazard: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=True
    )
    rule_version: Mapped[str] = mapped_column(String(16), default="demo-v1")


CheckConstraint("score >= 0 AND score <= 100", name="score_range")
Index("ix_risk_entity_time", RiskAssessment.entity_type, RiskAssessment.entity_id, RiskAssessment.assessed_at)
