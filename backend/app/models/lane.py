import uuid
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedMixin, UUIDMixin


class LaneNode(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "lane_nodes"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="junction")
    pos: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)


class Lane(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "lanes"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    width_m: Mapped[float] = mapped_column(Float, nullable=False)
    stairs: Mapped[bool] = mapped_column(Boolean, default=False)
    slope_pct: Mapped[float] = mapped_column(Float, default=0.0)
    vehicle_access: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    surface: Mapped[str] = mapped_column(String(32), default="paved")
    length_m: Mapped[float] = mapped_column(Float, default=0.0)
    node_a_code: Mapped[str] = mapped_column(String(32), ForeignKey("lane_nodes.code"), nullable=False)
    node_b_code: Mapped[str] = mapped_column(String(32), ForeignKey("lane_nodes.code"), nullable=False)
    path: Mapped[list[list[float]]] = mapped_column(JSON, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    geom = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)


class GraphEdge(UUIDMixin, CreatedMixin, Base):
    __tablename__ = "graph_edges"

    from_node: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    to_node: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    lane_code: Mapped[str] = mapped_column(String(64), nullable=False)
    length_m: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    width_m: Mapped[float] = mapped_column(Float, default=0.0)
    stairs: Mapped[bool] = mapped_column(Boolean, default=False)
    slope_pct: Mapped[float] = mapped_column(Float, default=0.0)
    vehicle_access: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
