"""Real OSM emergency navigation graph.

Builds a routable graph directly from imported OpenStreetMap way geometry
(``lanes.path``) instead of the synthetic demo lane grid.

Connectivity rules (no connectivity is invented):
- A vertex shared by two or more distinct OSM ways becomes a junction.
- An endpoint of any OSM way becomes a node.
- Ways are split at those junctions while retaining their full LineString
  geometry; interior vertices are never assumed to connect to anything else.
- ``oneway`` / roundabout direction is honoured.
- Access tags (access / vehicle / motor_vehicle / bicycle / foot) and
  ``maxwidth`` / ``maxheight`` are applied per routing profile.
- Invalid / degenerate geometry is skipped deterministically.

All calculations use a local metric approximation around Jammu
(metres are accurate to well under 1 %% at this scale).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from heapq import heappop, heappush
from typing import Any, Iterable, Literal

from app.routing.graph import M_LAT, M_LON, dist_m_sqrt

NavProfile = Literal["fire_truck", "responder_bike", "walking"]
Weighting = Literal["time", "distance"]

ALLOWED_PROFILES: tuple[str, ...] = ("fire_truck", "responder_bike", "walking")

MAX_SNAP_DISTANCE_M = 500.0
SNAP_FRACTION_EPS = 1e-9
PAIR_CANDIDATE_LIMIT = 24
MAX_PAIR_ATTEMPTS = 128

FOOTWAY_CLASSES = {"footway", "pedestrian", "path", "steps", "corridor", "cycleway"}

# Conservative speed assumptions (km/h) by OSM highway class. The result is
# explicitly labelled as model output, not measured travel time.
SPEED_TABLE_KMH: dict[str, dict[str, float]] = {
    "fire_truck": {
        "trunk": 30.0,
        "primary": 30.0,
        "secondary": 25.0,
        "secondary_link": 20.0,
        "tertiary": 20.0,
        "unclassified": 15.0,
        "residential": 15.0,
        "service": 10.0,
    },
    "responder_bike": {
        "trunk": 18.0,
        "primary": 18.0,
        "secondary": 16.0,
        "secondary_link": 15.0,
        "tertiary": 16.0,
        "unclassified": 14.0,
        "residential": 14.0,
        "service": 12.0,
        "footway": 10.0,
        "pedestrian": 10.0,
        "path": 10.0,
        "cycleway": 12.0,
    },
    "walking": {
        "trunk": 4.5,
        "primary": 4.5,
        "secondary": 4.5,
        "secondary_link": 4.5,
        "tertiary": 4.5,
        "unclassified": 4.5,
        "residential": 4.5,
        "service": 4.5,
        "footway": 4.5,
        "pedestrian": 4.5,
        "path": 4.0,
        "cycleway": 4.5,
        "steps": 3.0,
    },
}
DEFAULT_SPEED_KMH = {"fire_truck": 12.0, "responder_bike": 12.0, "walking": 4.5}

PROFILE_MIN_WIDTH_M = {"fire_truck": 3.5, "responder_bike": 1.2, "walking": 0.9}
PROFILE_VEHICLE_WIDTH_M = {"fire_truck": 2.5, "responder_bike": 0.8}
PROFILE_VEHICLE_HEIGHT_M = {"fire_truck": 3.2, "responder_bike": 2.0}

DURATION_BASIS = "osm_highway_class_speed_table_no_live_traffic"

_MAX_SPEED_MPS = {p: max(table.values()) / 3.6 for p, table in SPEED_TABLE_KMH.items()}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


class NavigationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(slots=True)
class OsmWayInput:
    code: str
    name: str
    path: list[list[float]]
    width_m: float
    highway: str
    tags: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    vehicle_access: bool = True
    width_verified: bool = False


@dataclass(slots=True)
class NavNode:
    id: str
    pos: list[float]


@dataclass(slots=True)
class NavEdge:
    id: str
    way_code: str
    name: str
    path: list[list[float]]
    length_m: float
    highway: str
    width_m: float
    width_verified: bool
    oneway: str  # both | forward | backward
    stairs: bool
    tags: dict[str, Any]
    max_width_m: float | None
    max_height_m: float | None
    vehicle_access: bool = True
    blocked: bool = False
    node_a: str = ""
    node_b: str = ""


@dataclass(frozen=True, slots=True)
class Traversal:
    to: str
    edge_id: str
    forward: bool


@dataclass(slots=True)
class NavigationGraph:
    nodes: dict[str, NavNode] = field(default_factory=dict)
    edges: dict[str, NavEdge] = field(default_factory=dict)
    adj: dict[str, list[Traversal]] = field(default_factory=dict)
    components: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class SnapCandidate:
    edge: NavEdge
    component: int
    t: float
    point: list[float]
    distance_m: float


@dataclass(slots=True)
class Step:
    edge: NavEdge
    forward: bool
    t_start: float
    t_end: float
    length_m: float


@dataclass(slots=True)
class RouteResult:
    profile: str
    geometry: list[list[float]]
    distance_m: float
    duration_s: float | None
    edge_ids: list[str]
    origin: SnapCandidate
    destination: SnapCandidate
    warnings: list[str]
    algorithm: str
    weighting: str


@dataclass(slots=True)
class _Arc:
    to: str
    step: Step | None
    weight: float


def _round_key(pos: list[float]) -> tuple[float, float]:
    return (round(float(pos[0]), 7), round(float(pos[1]), 7))


def _clean_path(points: Iterable[Iterable[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for p in points:
        try:
            x = float(p[0])
            y = float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        if out and out[-1][0] == x and out[-1][1] == y:
            continue
        out.append([x, y])
    return out


def _path_length(path: list[list[float]]) -> float:
    return sum(dist_m_sqrt(path[i], path[i + 1]) for i in range(len(path) - 1))


def _normalise_flag(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _parse_metres(value: Any) -> float | None:
    if value is None:
        return None
    text = _normalise_flag(value)
    if not text or text in ("default", "none", "unsigned", "no"):
        return None
    match = _NUM_RE.search(text)
    if match is None:
        return None
    try:
        parsed = float(match.group(0))
    except ValueError:
        return None
    if parsed <= 0:
        return None
    # Feet are occasionally tagged explicitly.
    if "ft" in text or "feet" in text:
        parsed *= 0.3048
    return parsed


def _denied_by(tags: dict[str, Any], keys: tuple[str, ...], values: set[str]) -> bool:
    return any(_normalise_flag(tags.get(k)) in values for k in keys)


_DENY_ACCESS = {"no", "private", "customers", "permit"}


def _oneway_mode(tags: dict[str, Any]) -> str:
    flag = _normalise_flag(tags.get("oneway"))
    if flag in ("yes", "true", "1"):
        return "forward"
    if flag in ("-1", "reverse"):
        return "backward"
    if flag in ("no", "false", "0"):
        return "both"
    if _normalise_flag(tags.get("junction")) in ("roundabout", "circular"):
        return "forward"
    return "both"


def _edge_allowed(profile: str, edge: NavEdge) -> bool:
    if edge.blocked or edge.length_m <= 0:
        return False
    min_width = PROFILE_MIN_WIDTH_M[profile]
    if edge.width_m > 0 and edge.width_m < min_width:
        return False
    if edge.stairs and profile != "walking":
        return False
    if _denied_by(edge.tags, ("access",), _DENY_ACCESS):
        return False

    if profile == "walking":
        if _denied_by(edge.tags, ("foot",), {"no"}):
            return False
        return True

    if profile == "responder_bike":
        if _denied_by(edge.tags, ("bicycle",), {"no"}):
            return False
        if edge.stairs:
            return False
        return True

    # fire_truck
    if not edge.vehicle_access or edge.highway in FOOTWAY_CLASSES:
        return False
    if _denied_by(edge.tags, ("vehicle", "motor_vehicle", "motorcar"), {"no", "private"}):
        return False
    if edge.max_width_m is not None and edge.max_width_m < PROFILE_VEHICLE_WIDTH_M[profile]:
        return False
    if edge.max_height_m is not None and edge.max_height_m < PROFILE_VEHICLE_HEIGHT_M[profile]:
        return False
    return True


def _effective_oneway(profile: str, edge: NavEdge) -> str:
    if profile == "walking":
        foot = _normalise_flag(edge.tags.get("oneway:foot"))
        if foot in ("yes", "true", "1"):
            return "forward"
        if foot in ("-1", "reverse"):
            return "backward"
        return "both"
    if profile == "responder_bike":
        bike = _normalise_flag(edge.tags.get("oneway:bicycle"))
        if bike in ("no", "false", "0"):
            return "both"
        if bike in ("-1", "reverse"):
            return "backward"
        if bike in ("yes", "true", "1"):
            return "forward"
    return edge.oneway


def edge_speed_mps(profile: str, edge: NavEdge) -> float:
    table = SPEED_TABLE_KMH[profile]
    kmh = table.get(edge.highway, DEFAULT_SPEED_KMH[profile])
    return kmh / 3.6


def edge_travel_s(profile: str, edge: NavEdge, length_m: float) -> float:
    speed = edge_speed_mps(profile, edge)
    return length_m / speed if speed > 0 else 0.0


def _segment_geometry(path: list[list[float]], start_idx: int, end_idx: int) -> list[list[float]]:
    return [list(p) for p in path[start_idx : end_idx + 1]]


def build_navigation_graph(ways: Iterable[OsmWayInput]) -> NavigationGraph:
    """Deterministically build a routable graph from OSM way geometry."""
    prepared: list[tuple[OsmWayInput, list[list[float]], list[tuple[float, float]]]] = []
    way_vertex_keys: dict[str, set[tuple[float, float]]] = {}
    key_way_count: dict[tuple[float, float], set[str]] = {}

    for way in sorted(ways, key=lambda w: w.code):
        path = _clean_path(way.path)
        if len(path) < 2:
            continue
        length = _path_length(path)
        if length <= 0:
            continue
        keys = [_round_key(p) for p in path]
        way_vertex_keys[way.code] = set(keys)
        for key in set(keys):
            key_way_count.setdefault(key, set()).add(way.code)
        prepared.append((way, path, keys))

    junction_keys = {
        key for key, codes in key_way_count.items() if len(codes) >= 2
    }
    for way, path, keys in prepared:
        junction_keys.add(keys[0])
        junction_keys.add(keys[-1])

    coord_to_node: dict[tuple[float, float], str] = {}
    node_positions: dict[tuple[float, float], list[float]] = {}
    ordered_keys = sorted(junction_keys)
    for index, key in enumerate(ordered_keys, start=1):
        coord_to_node[key] = f"OSMG-{index:05d}"
        node_positions[key] = [key[0], key[1]]

    graph = NavigationGraph()
    for key, node_id in coord_to_node.items():
        graph.nodes[node_id] = NavNode(id=node_id, pos=node_positions[key])
        graph.adj[node_id] = []

    for way, path, keys in prepared:
        split_indices = [
            i for i, key in enumerate(keys) if key in junction_keys
        ]
        if not split_indices or split_indices[0] != 0:
            split_indices.insert(0, 0)
        if split_indices[-1] != len(path) - 1:
            split_indices.append(len(path) - 1)
        split_indices = sorted(set(split_indices))
        if len(split_indices) < 2:
            continue

        tags = dict(way.tags or {})
        highway = (way.highway or "").strip().lower() or "unclassified"
        oneway = _oneway_mode(tags)
        stairs = highway == "steps"
        max_width = _parse_metres(tags.get("maxwidth"))
        max_height = _parse_metres(tags.get("maxheight"))

        for seg_index in range(len(split_indices) - 1):
            start_idx = split_indices[seg_index]
            end_idx = split_indices[seg_index + 1]
            if end_idx <= start_idx:
                continue
            segment = _segment_geometry(path, start_idx, end_idx)
            length = _path_length(segment)
            if length <= 0:
                continue
            a_key = keys[start_idx]
            b_key = keys[end_idx]
            a = coord_to_node[a_key]
            b = coord_to_node[b_key]
            if a == b and len(segment) <= 2:
                continue
            edge_id = f"{way.code}#{seg_index + 1}"
            edge = NavEdge(
                id=edge_id,
                way_code=way.code,
                name=way.name,
                path=segment,
                length_m=length,
                highway=highway,
                width_m=float(way.width_m or 0.0),
                width_verified=bool(way.width_verified),
                oneway=oneway,
                stairs=stairs,
                tags=tags,
                max_width_m=max_width,
                max_height_m=max_height,
                vehicle_access=way.vehicle_access,
                blocked=way.blocked,
                node_a=a,
                node_b=b,
            )
            graph.edges[edge_id] = edge
            if way.blocked:
                continue
            graph.adj[a].append(Traversal(to=b, edge_id=edge_id, forward=True))
            graph.adj[b].append(Traversal(to=a, edge_id=edge_id, forward=False))

    _assign_components(graph)
    return graph


def _assign_components(graph: NavigationGraph) -> None:
    """Weakly-connected components: direction restrictions are enforced by the search."""
    neighbours: dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
    for node_id, traversals in graph.adj.items():
        for traversal in traversals:
            neighbours[node_id].add(traversal.to)
            neighbours[traversal.to].add(node_id)
    components: dict[str, int] = {}
    next_component = 0
    for node_id in sorted(graph.nodes):
        if node_id in components:
            continue
        stack = [node_id]
        components[node_id] = next_component
        while stack:
            current = stack.pop()
            for neighbour in neighbours.get(current, ()):
                if neighbour not in components:
                    components[neighbour] = next_component
                    stack.append(neighbour)
        next_component += 1
    graph.components = components


def _project_point(point: list[float], path: list[list[float]]) -> tuple[float, int, float, list[float]] | None:
    """Return (distance_m, segment_index, t_along_path, projected_point)."""
    total = _path_length(path)
    if total <= 0:
        return None
    px = float(point[0]) * M_LON
    py = float(point[1]) * M_LAT
    best: tuple[float, int, float, list[float]] | None = None
    travelled = 0.0
    for i in range(len(path) - 1):
        ax = path[i][0] * M_LON
        ay = path[i][1] * M_LAT
        bx = path[i + 1][0] * M_LON
        by = path[i + 1][1] * M_LAT
        dx = bx - ax
        dy = by - ay
        seg_sq = dx * dx + dy * dy
        if seg_sq <= 0:
            continue
        seg_len = math.sqrt(seg_sq)
        u = ((px - ax) * dx + (py - ay) * dy) / seg_sq
        u = min(1.0, max(0.0, u))
        cx = ax + dx * u
        cy = ay + dy * u
        distance = math.hypot(px - cx, py - cy)
        t = (travelled + u * seg_len) / total
        projected = [
            path[i][0] + (path[i + 1][0] - path[i][0]) * u,
            path[i][1] + (path[i + 1][1] - path[i][1]) * u,
        ]
        if best is None or distance < best[0]:
            best = (distance, i, t, projected)
        travelled += seg_len
    return best


def find_candidates(
    graph: NavigationGraph,
    lat: float,
    lon: float,
    profile: str,
    max_distance_m: float = MAX_SNAP_DISTANCE_M,
) -> list[SnapCandidate]:
    point = [float(lon), float(lat)]
    candidates: list[SnapCandidate] = []
    for edge_id in sorted(graph.edges):
        edge = graph.edges[edge_id]
        if not _edge_allowed(profile, edge):
            continue
        projection = _project_point(point, edge.path)
        if projection is None:
            continue
        distance, _seg, t, projected = projection
        if distance > max_distance_m:
            continue
        candidates.append(
            SnapCandidate(
                edge=edge,
                component=graph.components.get(edge.node_a, -1),
                t=t,
                point=projected,
                distance_m=distance,
            )
        )
    candidates.sort(key=lambda c: (round(c.distance_m, 6), c.edge.id))
    return candidates


def _candidate_component(graph: NavigationGraph, candidate: SnapCandidate) -> int:
    return graph.components.get(candidate.edge.node_a, -1)


def _plan_route(
    graph: NavigationGraph,
    origin_candidates: list[SnapCandidate],
    destination_candidates: list[SnapCandidate],
    profile: str,
    weighting: str,
) -> tuple[SnapCandidate, SnapCandidate, list[Step]]:
    """Try near snap pairs in order and return the first honestly traversable route."""
    if not origin_candidates:
        raise NavigationError(
            "ORIGIN_OUT_OF_NETWORK",
            "Origin is not within 500 m of any traversable OSM road for this profile",
        )
    if not destination_candidates:
        raise NavigationError(
            "DESTINATION_OUT_OF_NETWORK",
            "Destination is not within 500 m of any traversable OSM road for this profile",
        )

    origin_pool = origin_candidates[:PAIR_CANDIDATE_LIMIT]
    destination_pool = destination_candidates[:PAIR_CANDIDATE_LIMIT]
    pairs: list[tuple[float, str, str, SnapCandidate, SnapCandidate]] = []
    for origin in origin_pool:
        oc = _candidate_component(graph, origin)
        for destination in destination_pool:
            if _candidate_component(graph, destination) != oc:
                continue
            total = origin.distance_m + destination.distance_m
            pairs.append(
                (round(total, 6), origin.edge.id, destination.edge.id, origin, destination)
            )

    if not pairs:
        oc = _candidate_component(graph, origin_pool[0])
        dc = _candidate_component(graph, destination_pool[0])
        if oc != dc:
            raise NavigationError(
                "ROUTE_NOT_FOUND",
                "Origin and destination snap to different disconnected OSM road components; "
                "no honest route exists in the imported data",
                status_code=404,
            )

    pairs.sort(key=lambda pair: pair[:3])
    attempts = 0
    for _total, _origin_edge, _destination_edge, origin, destination in pairs:
        if attempts >= MAX_PAIR_ATTEMPTS:
            break
        attempts += 1
        try:
            steps = _shortest_path(graph, origin, destination, profile, weighting)
        except NavigationError as exc:
            if exc.code == "ROUTE_NOT_FOUND":
                continue
            raise
        return origin, destination, steps

    raise NavigationError(
        "ROUTE_NOT_FOUND",
        f"No traversable route exists for this profile after checking {attempts} nearby snap pairs; "
        "one-way restrictions or access tags may disconnect the requested points",
        status_code=404,
    )


def _slice_path(path: list[list[float]], t_start: float, t_end: float) -> list[list[float]]:
    total = _path_length(path)
    if total <= 0:
        return []
    t_start = min(1.0, max(0.0, t_start))
    t_end = min(1.0, max(0.0, t_end))
    if t_end < t_start:
        t_start, t_end = t_end, t_start
    d0 = t_start * total
    d1 = t_end * total

    cumulative = [0.0]
    for i in range(len(path) - 1):
        cumulative.append(cumulative[-1] + dist_m_sqrt(path[i], path[i + 1]))

    def point_at(distance: float) -> list[float]:
        if distance <= 0:
            return list(path[0])
        if distance >= total:
            return list(path[-1])
        for i in range(1, len(cumulative)):
            if distance <= cumulative[i]:
                seg = cumulative[i] - cumulative[i - 1]
                u = 0.0 if seg <= 0 else (distance - cumulative[i - 1]) / seg
                return [
                    path[i - 1][0] + (path[i][0] - path[i - 1][0]) * u,
                    path[i - 1][1] + (path[i][1] - path[i - 1][1]) * u,
                ]
        return list(path[-1])

    out: list[list[float]] = [point_at(d0)]
    for i in range(1, len(path) - 1):
        if d0 < cumulative[i] < d1:
            out.append(list(path[i]))
    out.append(point_at(d1))
    dedup: list[list[float]] = []
    for point in out:
        if not dedup or point != dedup[-1]:
            dedup.append(point)
    return dedup


def _step_length(edge: NavEdge, t_start: float, t_end: float) -> float:
    return edge.length_m * max(0.0, t_end - t_start)


def _step_weight(profile: str, step: Step, weighting: str) -> float:
    if weighting == "distance":
        return step.length_m
    return edge_travel_s(profile, step.edge, step.length_m)


def _origin_arcs(candidate: SnapCandidate, profile: str, weighting: str) -> list[_Arc]:
    edge = candidate.edge
    t = candidate.t
    start_node = edge.node_a
    end_node = edge.node_b
    arcs: list[_Arc] = []
    mode = _effective_oneway(profile, edge)
    if mode == "both":
        to_end = Step(edge, True, t, 1.0, _step_length(edge, t, 1.0))
        to_start = Step(edge, False, 1.0 - t, 1.0, _step_length(edge, 1.0 - t, 1.0))
        arcs.append(_Arc(end_node, to_end, _step_weight(profile, to_end, weighting)))
        arcs.append(_Arc(start_node, to_start, _step_weight(profile, to_start, weighting)))
    elif mode == "forward":
        if t >= 1.0 - SNAP_FRACTION_EPS:
            arcs.append(_Arc(end_node, None, 0.0))
        else:
            step = Step(edge, True, t, 1.0, _step_length(edge, t, 1.0))
            arcs.append(_Arc(end_node, step, _step_weight(profile, step, weighting)))
    else:
        if t <= SNAP_FRACTION_EPS:
            arcs.append(_Arc(start_node, None, 0.0))
        else:
            step = Step(edge, False, 1.0 - t, 1.0, _step_length(edge, 1.0 - t, 1.0))
            arcs.append(_Arc(start_node, step, _step_weight(profile, step, weighting)))
    return arcs


def _destination_arcs(candidate: SnapCandidate, profile: str, weighting: str) -> dict[str, list[_Arc]]:
    """Destination arcs keyed by the graph node they depart from."""
    edge = candidate.edge
    t = min(1.0, max(0.0, candidate.t))
    start_node = edge.node_a
    end_node = edge.node_b
    out: dict[str, list[_Arc]] = {}
    mode = _effective_oneway(profile, edge)
    if mode == "both":
        from_start = Step(edge, True, 0.0, t, _step_length(edge, 0.0, t))
        from_end = Step(edge, False, 0.0, 1.0 - t, _step_length(edge, 0.0, 1.0 - t))
        out[start_node] = [_Arc("__DEST__", from_start, _step_weight(profile, from_start, weighting))]
        out[end_node] = [_Arc("__DEST__", from_end, _step_weight(profile, from_end, weighting))]
    elif mode == "forward":
        if t >= 1.0 - SNAP_FRACTION_EPS:
            out[end_node] = [_Arc("__DEST__", None, 0.0)]
        else:
            step = Step(edge, True, 0.0, t, _step_length(edge, 0.0, t))
            out[start_node] = [
                _Arc("__DEST__", step if t > SNAP_FRACTION_EPS else None, _step_weight(profile, step, weighting))
            ]
    else:
        if t >= 1.0 - SNAP_FRACTION_EPS:
            out[end_node] = [_Arc("__DEST__", None, 0.0)]
        else:
            step = Step(edge, False, 0.0, 1.0 - t, _step_length(edge, 0.0, 1.0 - t))
            out[end_node] = [_Arc("__DEST__", step, _step_weight(profile, step, weighting))]
    return out


def _same_edge_direct_step(
    origin: SnapCandidate,
    destination: SnapCandidate,
    profile: str,
) -> Step | None:
    if origin.edge.id != destination.edge.id:
        return None
    edge = origin.edge
    t0 = origin.t
    t1 = destination.t
    if abs(t1 - t0) <= SNAP_FRACTION_EPS:
        return Step(edge, True, t0, t1, 0.0)
    mode = _effective_oneway(profile, edge)
    if mode == "both":
        if t1 > t0:
            return Step(edge, True, t0, t1, _step_length(edge, t0, t1))
        return Step(edge, False, 1.0 - t0, 1.0 - t1, _step_length(edge, 1.0 - t0, 1.0 - t1))
    if mode == "forward":
        if t1 >= t0:
            return Step(edge, True, t0, t1, _step_length(edge, t0, t1))
        return None
    if t1 <= t0:
        return Step(edge, False, 1.0 - t0, 1.0 - t1, _step_length(edge, 1.0 - t0, 1.0 - t1))
    return None


def _heuristic(
    graph: NavigationGraph,
    node_id: str,
    target_pos: list[float],
    profile: str,
    weighting: str,
) -> float:
    node = graph.nodes.get(node_id)
    if node is None:
        return 0.0
    distance = dist_m_sqrt(node.pos, target_pos)
    if weighting == "distance":
        return distance
    return distance / max(_MAX_SPEED_MPS.get(profile, 1.0), 1e-6)


def _shortest_path(
    graph: NavigationGraph,
    origin: SnapCandidate,
    destination: SnapCandidate,
    profile: str,
    weighting: str,
) -> list[Step]:
    start = "__ORIGIN__"
    target = "__DEST__"
    origin_arcs = _origin_arcs(origin, profile, weighting)
    destination_arcs = _destination_arcs(destination, profile, weighting)
    direct = _same_edge_direct_step(origin, destination, profile)

    def arcs_from(node_id: str) -> Iterable[_Arc]:
        if node_id == start:
            yield from origin_arcs
            if direct is not None:
                yield _Arc(target, direct, _step_weight(profile, direct, weighting))
            return
        for traversal in graph.adj.get(node_id, []):
            edge = graph.edges[traversal.edge_id]
            mode = _effective_oneway(profile, edge)
            if traversal.forward and mode not in ("both", "forward"):
                continue
            if not traversal.forward and mode not in ("both", "backward"):
                continue
            step = Step(edge, traversal.forward, 0.0, 1.0, edge.length_m)
            weight = edge.length_m if weighting == "distance" else edge_travel_s(profile, edge, edge.length_m)
            yield _Arc(traversal.to, step, weight)
        yield from destination_arcs.get(node_id, [])

    cost: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, _Arc]] = {}
    done: set[str] = set()
    heap: list[tuple[float, float, str]] = [(0.0, 0.0, start)]
    order = 0
    while heap:
        _priority, _order, current = heappop(heap)
        if current in done:
            continue
        done.add(current)
        if current == target:
            break
        for arc in arcs_from(current):
            if arc.to in done:
                continue
            new_cost = cost[current] + arc.weight
            if new_cost < cost.get(arc.to, float("inf")):
                cost[arc.to] = new_cost
                prev[arc.to] = (current, arc)
                order += 1
                heuristic = (
                    0.0
                    if arc.to == target
                    else _heuristic(graph, arc.to, destination.point, profile, weighting)
                )
                heappush(heap, (new_cost + heuristic, float(order), arc.to))
    if target not in prev:
        raise NavigationError(
            "ROUTE_NOT_FOUND",
            "No traversable route exists between the snapped origin and destination for this profile",
            status_code=404,
        )
    steps: list[Step] = []
    current = target
    while current != start:
        previous, arc = prev[current]
        if arc.step is not None:
            steps.append(arc.step)
        current = previous
    steps.reverse()
    return steps


def compute_navigation(
    graph: NavigationGraph,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    profile: str,
    weighting: str = "time",
) -> RouteResult:
    if profile not in ALLOWED_PROFILES:
        raise NavigationError("INVALID_PROFILE", f"Unsupported routing profile {profile!r}")
    if not graph.edges or not graph.nodes:
        raise NavigationError("OSM_GRAPH_EMPTY", "No OSM road network is available to route on")

    origin_candidates = find_candidates(graph, origin_lat, origin_lng, profile)
    destination_candidates = find_candidates(graph, destination_lat, destination_lng, profile)
    origin, destination, steps = _plan_route(
        graph, origin_candidates, destination_candidates, profile, weighting
    )

    coords: list[list[float]] = [list(origin.point)]
    distance = 0.0
    duration = 0.0
    edge_ids: list[str] = []
    unverified_width = False
    for step in steps:
        oriented = step.edge.path if step.forward else list(reversed(step.edge.path))
        sliced = _slice_path(oriented, step.t_start, step.t_end)
        step_length = _path_length(sliced)
        distance += step_length
        duration += edge_travel_s(profile, step.edge, step_length)
        for point in sliced:
            if coords[-1] != point:
                coords.append(point)
        if step.edge.id not in edge_ids:
            edge_ids.append(step.edge.id)
        if step.edge.width_m > 0 and not step.edge.width_verified:
            unverified_width = True

    if not coords or coords[-1] != destination.point:
        coords.append(list(destination.point))
    if len(coords) == 1:
        coords.append(list(destination.point))

    warnings: list[str] = [
        "Route follows imported OpenStreetMap geometry, not the synthetic demo grid.",
    ]
    if origin.distance_m > 50:
        warnings.append(f"Origin was snapped {origin.distance_m:.0f} m to the nearest OSM road.")
    if destination.distance_m > 50:
        warnings.append(
            f"Destination was snapped {destination.distance_m:.0f} m to the nearest OSM road."
        )
    if unverified_width:
        warnings.append(
            "Lane widths are OSM highway-class estimates, not field-verified; "
            "width-based profile restrictions are therefore approximate."
        )
    warnings.append(
        "Travel time is a class-based model assumption with no live traffic; it is not a guaranteed ETA."
    )

    return RouteResult(
        profile=profile,
        geometry=coords,
        distance_m=distance,
        duration_s=duration,
        edge_ids=edge_ids,
        origin=origin,
        destination=destination,
        warnings=warnings,
        algorithm="astar_osm",
        weighting=weighting,
    )
