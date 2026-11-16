import uuid
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, UUIDMixin


class Building(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "buildings"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    floors: Mapped[int] = mapped_column(Integer, default=1)
    building_type: Mapped[str] = mapped_column(String(64), default="residential")
    construction: Mapped[str] = mapped_column(String(64), default="")
    occupancy: Mapped[int] = mapped_column(Integer, default=0)
    year_built: Mapped[int] = mapped_column(Integer, default=1970)
    height_m: Mapped[float] = mapped_column(Float, default=3.3)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    center: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    footprint: Mapped[list[list[float]]] = mapped_column(JSON, nullable=False)
    access_node_code: Mapped[str] = mapped_column(String(32), default="")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    center_point = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
