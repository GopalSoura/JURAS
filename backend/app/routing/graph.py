from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ORIGIN_LON = 74.8575
ORIGIN_LAT = 32.7285
M_LAT = 110574.0
M_LON = 111320.0 * 0.84119298  # cos(32.7285 deg)


def dist_m(a: list[float], b: list[float]) -> float:
    return ((a[0] - b[0]) * M_LON) ** 2 + ((a[1] - b[1]) * M_LAT) ** 2


def dist_m_sqrt(a: list[float], b: list[float]) -> float:
    return dist_m(a, b) ** 0.5


def midpoint(a: list[float], b: list[float]) -> list[float]:
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]


@dataclass
class LaneEdgeData:
    id: str
    a: str
    b: str
    width_m: float
    stairs: bool


@dataclass
class LaneNodeData:
    id: str
    pos: list[float]
    label: str
    kind: str


@dataclass
class Arc:
    to: str
    edge: LaneEdgeData
    len: float


@dataclass
class Graph:
    nodes: dict[str, LaneNodeData] = field(default_factory=dict)
    adj: dict[str, list[Arc]] = field(default_factory=dict)

    @classmethod
    def build(cls, nodes: list[LaneNodeData], edges: list[LaneEdgeData]) -> "Graph":
        g = cls(nodes={n.id: n for n in nodes}, adj={n.id: [] for n in nodes})
        for e in edges:
            a = g.nodes.get(e.a)
            b = g.nodes.get(e.b)
            if a is None or b is None:
                continue
            ln = dist_m_sqrt(a.pos, b.pos)
            g.adj.setdefault(e.a, []).append(Arc(to=e.b, edge=e, len=ln))
            g.adj.setdefault(e.b, []).append(Arc(to=e.a, edge=e, len=ln))
        return g


@dataclass
class Ctx:
    hazards: list[dict[str, Any]] = field(default_factory=list)
    floods: list[dict[str, Any]] = field(default_factory=list)
    closures: list[dict[str, Any]] = field(default_factory=list)
