import uuid
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, UUIDMixin


class Sensor(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "sensors"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id"), nullable=True
    )
    node_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    source: Mapped[str] = mapped_column(String(16), default="simulation")
    pos: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
