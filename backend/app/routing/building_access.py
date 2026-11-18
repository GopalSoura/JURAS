"""Street-facing access points for building response routes.

Routing to a building's geometric centre makes the final connector run through
the frontage and stop inside the building. On the map that looks like the
vehicle went past the gate and parked behind it. These helpers trim the last
connector at the footprint edge facing the approach road, so a response route
visibly ends at the front of the building.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from app.routing.graph import dist_m_sqrt
from app.routing.osm_graph import ACCESS_WARN_DISTANCE_M, CONNECTOR_WALK_SPEED_MPS

Point = list[float]

_EPS = 1e-9


def _clean_ring(footprint: Iterable[Sequence[float]] | None) -> list[Point]:
    ring: list[Point] = []
    for raw in footprint or ():
        try:
            lon = float(raw[0])
            lat = float(raw[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (math.isfinite(lon) and math.isfinite(lat)):
            continue
        ring.append([lon, lat])
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    return ring if len(ring) >= 3 else []


def _segment_hit(
    a: Sequence[float], b: Sequence[float], c: Sequence[float], d: Sequence[float]
) -> tuple[float, Point] | None:
    """Return (t along a->b, intersection) when two segments cross."""
    rx = float(b[0]) - float(a[0])
    ry = float(b[1]) - float(a[1])
    sx = float(d[0]) - float(c[0])
    sy = float(d[1]) - float(c[1])
    denominator = rx * sy - ry * sx
    if abs(denominator) <= _EPS:
        return None
    qx = float(c[0]) - float(a[0])
    qy = float(c[1]) - float(a[1])
    t = (qx * sy - qy * sx) / denominator
    u = (qx * ry - qy * rx) / denominator
    if t < -_EPS or t > 1.0 + _EPS or u < -_EPS or u > 1.0 + _EPS:
        return None
    t = min(1.0, max(0.0, t))
    return t, [float(a[0]) + t * rx, float(a[1]) + t * ry]


def _closest_on_segment(
    point: Sequence[float], a: Sequence[float], b: Sequence[float]
) -> tuple[float, Point]:
    dx = float(b[0]) - float(a[0])
    dy = float(b[1]) - float(a[1])
    length_sq = dx * dx + dy * dy
    if length_sq <= _EPS:
        candidate = [float(a[0]), float(a[1])]
        return dist_m_sqrt(point, candidate), candidate
    t = (
        (float(point[0]) - float(a[0])) * dx + (float(point[1]) - float(a[1])) * dy
    ) / length_sq
    t = min(1.0, max(0.0, t))
    candidate = [float(a[0]) + t * dx, float(a[1]) + t * dy]
    return dist_m_sqrt(point, candidate), candidate


def entrance_point(
    footprint: Iterable[Sequence[float]] | None,
    approach: Sequence[float] | None,
    centre: Sequence[float] | None,
) -> Point | None:
    """Point where the final approach meets the building's street-facing edge.

    ``approach`` is normally the snapped OSM road point the last connector
    starts from, and ``centre`` the requested building centre. The first
    footprint edge crossed by that connector is the frontage the vehicle sees,
    so it is the right place to stop instead of driving to the centre.
    """
    ring = _clean_ring(footprint)
    if len(ring) < 3 or approach is None or centre is None:
        return None
    try:
        approach_point = [float(approach[0]), float(approach[1])]
        centre_point = [float(centre[0]), float(centre[1])]
    except (TypeError, ValueError, IndexError):
        return None
    if dist_m_sqrt(approach_point, centre_point) < 0.5:
        return None

    hits: list[tuple[float, Point]] = []
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        hit = _segment_hit(approach_point, centre_point, start, end)
        if hit is not None:
            hits.append(hit)
    if hits:
        hits.sort(key=lambda item: item[0])
        for _t, point in hits:
            if dist_m_sqrt(point, centre_point) >= 0.5:
                return point

    # Degenerate data (for example a snap point already inside the footprint):
    # fall back to the nearest frontage to the approach so the route still
    # stops outside the building.
    best: tuple[float, Point] | None = None
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        candidate = _closest_on_segment(approach_point, start, end)
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        return None
    if dist_m_sqrt(best[1], centre_point) < 0.5:
        return None
    return best[1]


def trim_route_to_entrance(
    result: Any,
    footprint: Iterable[Sequence[float]] | None,
    centre: Sequence[float] | None,
    building_name: str | None = None,
) -> Point | None:
    """Move a computed route's last point from the centre to the frontage.

    ``result`` is an ``osm_graph.RouteResult``. Distance and duration stay
    road-only; only the walking connector and the drawn endpoint change.
    """
    geometry = getattr(result, "geometry", None)
    destination = getattr(result, "destination", None)
    if not geometry or destination is None:
        return None
    gate = entrance_point(footprint, getattr(destination, "point", None), centre)
    if gate is None:
        return None
    if dist_m_sqrt(geometry[-1], gate) < 0.5:
        return None
    geometry[-1] = gate
    result.egress_distance_m = dist_m_sqrt(destination.point, gate)
    result.egress_duration_s = result.egress_distance_m / CONNECTOR_WALK_SPEED_MPS
    result.destination.distance_m = result.egress_distance_m
    result.warnings = [
        warning
        for warning in result.warnings
        if not warning.startswith("Destination is ")
    ]
    if result.egress_distance_m > ACCESS_WARN_DISTANCE_M:
        result.warnings.append(
            f"The building front is {result.egress_distance_m:.0f} m from the nearest "
            "OSM road; a short connector links the last mapped road to it."
        )
    label = f" of {building_name}" if building_name else ""
    result.warnings.append(
        f"Route ends at the street-facing entrance{label}, not the building centre."
    )
    return gate
