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

CONNECTOR_WALK_SPEED_MPS = 1.3
ACCESS_WARN_DISTANCE_M = 25.0
PAIR_SNAP_WINDOW_M = 25.0
MAX_PAIR_ROUTE_EVALUATIONS = 24
GEOMETRY_TOLERANCE_M = 1.0

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
class RouteStep:
    maneuver: str
    instruction: str
    road_name: str
    highway: str
    mode: str
    distance_m: float
    duration_s: float
    start: list[float]
    end: list[float]
    geometry: list[list[float]]


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
    steps: list[RouteStep]
    road_distance_m: float
    road_duration_s: float
    access_distance_m: float
    access_duration_s: float
    egress_distance_m: float
    egress_duration_s: float


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


def _path_distance_m(point: list[float], path: list[list[float]]) -> float:
    projection = _project_point(point, path)
    return projection[0] if projection is not None else float("inf")


def _edge_penalty(
    edge: NavEdge,
    profile: str,
    hazards: Iterable[dict[str, Any]] | None,
    floods: Iterable[dict[str, Any]] | None,
    closures: Iterable[dict[str, Any]] | None = None,
) -> float | None:
    """Cost multiplier for an edge, or ``None`` when the edge is unsafe.

    Hazards are penalised exactly like the legacy demo planner (x6 within
    radius + 10 m). Deep water blocks fire trucks, matching the legacy rule.
    Operator closures are hard blocks for every profile, so any affected edge
    is removed from the graph and the router must find an alternative.
    """
    multiplier = 1.0
    for closure in closures or ():
        radius = float(closure.get("radius_m", 15.0))
        if _path_distance_m(closure["pos"], edge.path) <= radius:
            return None
    for hazard in hazards or ():
        radius = float(hazard.get("radius_m", 0.0))
        if _path_distance_m(hazard["pos"], edge.path) <= radius + 10.0:
            multiplier *= 6.0
    for flood in floods or ():
        radius = float(flood.get("radius_m", 0.0))
        depth = float(flood.get("depth_cm", 0.0))
        if _path_distance_m(flood["pos"], edge.path) <= radius + 6.0:
            if profile == "fire_truck" and depth >= 25.0:
                return None
            multiplier *= 1.0 + depth / 30.0
    return multiplier


def _edge_penalties(
    graph: NavigationGraph,
    profile: str,
    hazards: Iterable[dict[str, Any]] | None,
    floods: Iterable[dict[str, Any]] | None,
    closures: Iterable[dict[str, Any]] | None = None,
) -> dict[str, float | None]:
    if not hazards and not floods and not closures:
        return {}
    return {
        edge_id: _edge_penalty(edge, profile, hazards, floods, closures)
        for edge_id, edge in graph.edges.items()
    }


def _penalty_for(penalties: dict[str, float | None] | None, edge_id: str) -> float | None:
    if not penalties:
        return 1.0
    return penalties.get(edge_id, 1.0)


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


def validate_route_geometry(
    geometry: list[list[float]],
    edges: Iterable[NavEdge],
    tolerance_m: float = GEOMETRY_TOLERANCE_M,
) -> list[str]:
    """Return violations when a route line leaves the given OSM road edges.

    Every vertex and segment midpoint is checked against the route's own edge
    geometry, so a fabricated straight connector between two otherwise on-road
    points is detected instead of silently passing a vertex-only check.
    """
    road_paths = [edge.path for edge in edges if len(edge.path) >= 2]
    if not road_paths:
        return ["Route has no OSM road edges to validate against"]
    if len(geometry) < 2:
        return ["Route geometry has fewer than two coordinates"]

    def add_violation(target: list[str], label: str, point: list[float]) -> None:
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError, IndexError):
            target.append(f"{label} is not a valid lon/lat pair")
            return
        if not (math.isfinite(x) and math.isfinite(y)):
            target.append(f"{label} contains non-finite coordinates")
            return
        distance = min(_path_distance_m([x, y], path) for path in road_paths)
        if distance > tolerance_m:
            target.append(f"{label} is {distance:.1f} m off the OSM road network")

    violations: list[str] = []
    for index, point in enumerate(geometry):
        add_violation(violations, f"Route coordinate {index}", point)
    for index in range(len(geometry) - 1):
        start = geometry[index]
        end = geometry[index + 1]
        try:
            midpoint = [
                (float(start[0]) + float(end[0])) / 2.0,
                (float(start[1]) + float(end[1])) / 2.0,
            ]
        except (TypeError, ValueError, IndexError):
            violations.append(f"Route segment {index} is not a valid lon/lat pair")
            continue
        add_violation(violations, f"Route segment {index} midpoint", midpoint)
    return violations


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
    penalties: dict[str, float | None] | None = None,
) -> tuple[SnapCandidate, SnapCandidate, list[Step]]:
    """Choose the best honestly traversable snap pair, Google-Maps style.

    Candidate pairs are ordered by total walk-to-road distance. Every pair is
    really routed (A*, with hazard/flood penalties) and the pair with the best
    combined road + access/egress cost wins. A zero-length "route" caused by two
    points snapping to the same spot is only used when no real road route exists.
    """
    if not origin_candidates:
        raise NavigationError(
            "ORIGIN_OUT_OF_NETWORK",
            "No valid accessible road route found: origin is not within 500 m of any "
            "traversable OSM road for this profile",
        )
    if not destination_candidates:
        raise NavigationError(
            "DESTINATION_OUT_OF_NETWORK",
            "No valid accessible road route found: destination is not within 500 m of any "
            "traversable OSM road for this profile",
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
                "No valid accessible road route found: origin and destination snap to "
                "different disconnected OSM road components in the imported data",
                status_code=404,
            )

    pairs.sort(key=lambda pair: pair[:3])

    # Prefer snap pairs whose access/egress gaps are close to the best available
    # snap. This keeps the road-only route ending near the requested destination
    # instead of taking a shorter road detour to a road that is far away.
    min_origin = min(candidate.distance_m for candidate in origin_pool)
    min_destination = min(candidate.distance_m for candidate in destination_pool)
    near_pairs: list[tuple[float, str, str, SnapCandidate, SnapCandidate]] = []
    far_pairs: list[tuple[float, str, str, SnapCandidate, SnapCandidate]] = []
    for pair in pairs:
        origin, destination = pair[3], pair[4]
        if (
            origin.distance_m <= min_origin + PAIR_SNAP_WINDOW_M
            and destination.distance_m <= min_destination + PAIR_SNAP_WINDOW_M
        ):
            near_pairs.append(pair)
        else:
            far_pairs.append(pair)
    ordered_pairs = [(True, pair) for pair in near_pairs] + [
        (False, pair) for pair in far_pairs
    ]

    def pair_score(
        origin: SnapCandidate,
        destination: SnapCandidate,
        steps: list[Step],
        include_connectors: bool,
    ) -> tuple[float, float]:
        road_m = sum(step.length_m for step in steps)
        road_s = sum(edge_travel_s(profile, step.edge, step.length_m) for step in steps)
        walk_m = origin.distance_m + destination.distance_m
        walk_s = walk_m / CONNECTOR_WALK_SPEED_MPS
        if weighting == "distance":
            return road_m + (walk_m if include_connectors else 0.0), road_m
        return road_s + (walk_s if include_connectors else 0.0), road_m

    best: tuple[float, SnapCandidate, SnapCandidate, list[Step]] | None = None
    best_near: tuple[float, SnapCandidate, SnapCandidate, list[Step]] | None = None
    best_fallback: tuple[float, SnapCandidate, SnapCandidate, list[Step]] | None = None
    attempts = 0
    for is_near, (_total, _origin_edge, _destination_edge, origin, destination) in ordered_pairs:
        if attempts >= MAX_PAIR_ATTEMPTS or attempts >= MAX_PAIR_ROUTE_EVALUATIONS:
            break
        attempts += 1
        try:
            steps = _shortest_path(
                graph, origin, destination, profile, weighting, penalties
            )
        except NavigationError as exc:
            if exc.code == "ROUTE_NOT_FOUND":
                continue
            raise
        score, road_m = pair_score(origin, destination, steps, not is_near)
        candidate = (score, origin, destination, steps)
        if best is None or score < best[0]:
            best = candidate
        if road_m > 0.5:
            target = best_near if is_near else best_fallback
            if target is None or score < target[0]:
                if is_near:
                    best_near = candidate
                else:
                    best_fallback = candidate

    chosen = best_near or best_fallback
    if chosen is not None:
        _score, origin, destination, steps = chosen
        return origin, destination, steps

    if best is not None:
        raise NavigationError(
            "ROUTE_NOT_FOUND",
            "No valid accessible road route found: origin and destination snap to the same "
            "point on the OSM road network, so there is no road segment to travel",
            status_code=404,
        )
    raise NavigationError(
        "ROUTE_NOT_FOUND",
        f"No traversable road route exists for this profile after checking {attempts} nearby snap pairs; "
        "one-way restrictions, road closures or access tags may disconnect the requested points",
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


def _step_weight(profile: str, step: Step, weighting: str, penalty: float = 1.0) -> float:
    if weighting == "distance":
        return step.length_m * penalty
    return edge_travel_s(profile, step.edge, step.length_m) * penalty


def _origin_arcs(
    candidate: SnapCandidate,
    profile: str,
    weighting: str,
    penalties: dict[str, float | None] | None = None,
) -> list[_Arc]:
    edge = candidate.edge
    t = candidate.t
    start_node = edge.node_a
    end_node = edge.node_b
    arcs: list[_Arc] = []
    penalty = _penalty_for(penalties, edge.id)
    if penalty is None:
        return arcs
    mode = _effective_oneway(profile, edge)
    if mode == "both":
        to_end = Step(edge, True, t, 1.0, _step_length(edge, t, 1.0))
        to_start = Step(edge, False, 1.0 - t, 1.0, _step_length(edge, 1.0 - t, 1.0))
        arcs.append(_Arc(end_node, to_end, _step_weight(profile, to_end, weighting, penalty)))
        arcs.append(_Arc(start_node, to_start, _step_weight(profile, to_start, weighting, penalty)))
    elif mode == "forward":
        if t >= 1.0 - SNAP_FRACTION_EPS:
            arcs.append(_Arc(end_node, None, 0.0))
        else:
            step = Step(edge, True, t, 1.0, _step_length(edge, t, 1.0))
            arcs.append(_Arc(end_node, step, _step_weight(profile, step, weighting, penalty)))
    else:
        if t <= SNAP_FRACTION_EPS:
            arcs.append(_Arc(start_node, None, 0.0))
        else:
            step = Step(edge, False, 1.0 - t, 1.0, _step_length(edge, 1.0 - t, 1.0))
            arcs.append(_Arc(start_node, step, _step_weight(profile, step, weighting, penalty)))
    return arcs


def _destination_arcs(
    candidate: SnapCandidate,
    profile: str,
    weighting: str,
    penalties: dict[str, float | None] | None = None,
) -> dict[str, list[_Arc]]:
    """Destination arcs keyed by the graph node they depart from."""
    edge = candidate.edge
    t = min(1.0, max(0.0, candidate.t))
    start_node = edge.node_a
    end_node = edge.node_b
    out: dict[str, list[_Arc]] = {}
    penalty = _penalty_for(penalties, edge.id)
    if penalty is None:
        return out
    mode = _effective_oneway(profile, edge)
    if mode == "both":
        from_start = Step(edge, True, 0.0, t, _step_length(edge, 0.0, t))
        from_end = Step(edge, False, 0.0, 1.0 - t, _step_length(edge, 0.0, 1.0 - t))
        out[start_node] = [
            _Arc("__DEST__", from_start, _step_weight(profile, from_start, weighting, penalty))
        ]
        out[end_node] = [
            _Arc("__DEST__", from_end, _step_weight(profile, from_end, weighting, penalty))
        ]
    elif mode == "forward":
        if t >= 1.0 - SNAP_FRACTION_EPS:
            out[end_node] = [_Arc("__DEST__", None, 0.0)]
        else:
            step = Step(edge, True, 0.0, t, _step_length(edge, 0.0, t))
            out[start_node] = [
                _Arc(
                    "__DEST__",
                    step if t > SNAP_FRACTION_EPS else None,
                    _step_weight(profile, step, weighting, penalty),
                )
            ]
    else:
        if t >= 1.0 - SNAP_FRACTION_EPS:
            out[end_node] = [_Arc("__DEST__", None, 0.0)]
        else:
            step = Step(edge, False, 0.0, 1.0 - t, _step_length(edge, 0.0, 1.0 - t))
            out[end_node] = [
                _Arc("__DEST__", step, _step_weight(profile, step, weighting, penalty))
            ]
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
    penalties: dict[str, float | None] | None = None,
) -> list[Step]:
    start = "__ORIGIN__"
    target = "__DEST__"
    origin_arcs = _origin_arcs(origin, profile, weighting, penalties)
    destination_arcs = _destination_arcs(destination, profile, weighting, penalties)
    direct = _same_edge_direct_step(origin, destination, profile)
    direct_penalty = _penalty_for(penalties, origin.edge.id)
    if direct is not None and direct_penalty is None:
        direct = None

    def arcs_from(node_id: str) -> Iterable[_Arc]:
        if node_id == start:
            yield from origin_arcs
            if direct is not None:
                yield _Arc(
                    target,
                    direct,
                    _step_weight(profile, direct, weighting, direct_penalty or 1.0),
                )
            return
        for traversal in graph.adj.get(node_id, []):
            edge = graph.edges[traversal.edge_id]
            mode = _effective_oneway(profile, edge)
            if traversal.forward and mode not in ("both", "forward"):
                continue
            if not traversal.forward and mode not in ("both", "backward"):
                continue
            penalty = _penalty_for(penalties, edge.id)
            if penalty is None:
                continue
            step = Step(edge, traversal.forward, 0.0, 1.0, edge.length_m)
            weight = _step_weight(profile, step, weighting, penalty)
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


_COMPASS = (
    "north",
    "north-east",
    "east",
    "south-east",
    "south",
    "south-west",
    "west",
    "north-west",
)


def _bearing(start: list[float], end: list[float]) -> float | None:
    dx = (float(end[0]) - float(start[0])) * M_LON
    dy = (float(end[1]) - float(start[1])) * M_LAT
    if dx == 0.0 and dy == 0.0:
        return None
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def _path_start_bearing(path: list[list[float]]) -> float:
    for i in range(len(path) - 1):
        bearing = _bearing(path[i], path[i + 1])
        if bearing is not None:
            return bearing
    return 0.0


def _path_end_bearing(path: list[list[float]]) -> float:
    for i in range(len(path) - 1, 0, -1):
        bearing = _bearing(path[i - 1], path[i])
        if bearing is not None:
            return bearing
    return 0.0


def _compass(bearing: float) -> str:
    return _COMPASS[int((bearing + 22.5) // 45.0) % 8]


def _angle_delta(incoming: float, outgoing: float) -> float:
    return (outgoing - incoming + 540.0) % 360.0 - 180.0


def _profile_mode(profile: str) -> str:
    if profile == "fire_truck":
        return "drive"
    if profile == "responder_bike":
        return "bike"
    return "walk"


def _group_road_steps(profile: str, steps: list[Step], geometries: list[list[list[float]]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for step, geometry in zip(steps, geometries):
        if len(geometry) < 2:
            continue
        if (
            groups
            and groups[-1]["way_code"] == step.edge.way_code
            and groups[-1]["forward"] == step.forward
        ):
            merged = groups[-1]["geometry"]
            for point in geometry:
                if merged[-1] != point:
                    merged.append(point)
            groups[-1]["distance_m"] = _path_length(merged)
            groups[-1]["end"] = list(merged[-1])
            groups[-1]["roundabout"] = groups[-1]["roundabout"] or _is_roundabout(step.edge)
            continue
        groups.append(
            {
                "way_code": step.edge.way_code,
                "forward": step.forward,
                "road_name": step.edge.name.strip() if step.edge.name else "",
                "highway": step.edge.highway,
                "roundabout": _is_roundabout(step.edge),
                "edge": step.edge,
                "distance_m": _path_length(geometry),
                "geometry": [list(point) for point in geometry],
                "start": list(geometry[0]),
                "end": list(geometry[-1]),
            }
        )
    return groups


def _is_roundabout(edge: NavEdge) -> bool:
    return _normalise_flag(edge.tags.get("junction")) in ("roundabout", "circular")


def _turn_copy(maneuver: str, road_name: str) -> str:
    onto = f" onto {road_name}" if road_name else ""
    if maneuver == "continue":
        return f"Continue on {road_name}" if road_name else "Continue straight"
    if maneuver == "roundabout":
        return f"At the roundabout, continue{onto}" if road_name else "At the roundabout, continue"
    if maneuver == "uturn":
        return f"Make a U-turn{onto}"
    labels = {
        "turn-left": "Turn left",
        "turn-right": "Turn right",
        "slight-left": "Slight left",
        "slight-right": "Slight right",
        "sharp-left": "Sharp left",
        "sharp-right": "Sharp right",
    }
    return f"{labels.get(maneuver, 'Continue')}{onto}"


def _build_route_steps(
    profile: str,
    steps: list[Step],
    geometries: list[list[list[float]]],
    destination_snapped: list[float],
) -> list[RouteStep]:
    out: list[RouteStep] = []
    mode = _profile_mode(profile)
    groups = _group_road_steps(profile, steps, geometries)
    previous_bearing: float | None = None
    for index, group in enumerate(groups):
        geometry = group["geometry"]
        road_name = group["road_name"]
        start_bearing = _path_start_bearing(geometry)
        if index == 0:
            maneuver = "depart"
            instruction = (
                f"Head {_compass(start_bearing)} on {road_name}"
                if road_name
                else f"Head {_compass(start_bearing)}"
            )
        else:
            delta = _angle_delta(previous_bearing or 0.0, start_bearing)
            if group["roundabout"]:
                maneuver = "roundabout"
            elif abs(delta) <= 15.0:
                maneuver = "continue"
            elif abs(delta) <= 45.0:
                maneuver = "slight-left" if delta < 0.0 else "slight-right"
            elif abs(delta) <= 135.0:
                maneuver = "turn-left" if delta < 0.0 else "turn-right"
            elif abs(delta) <= 160.0:
                maneuver = "sharp-left" if delta < 0.0 else "sharp-right"
            else:
                maneuver = "uturn"
            instruction = _turn_copy(maneuver, road_name)
        distance = float(group["distance_m"])
        out.append(
            RouteStep(
                maneuver=maneuver,
                instruction=instruction,
                road_name=road_name,
                highway=group["highway"],
                mode=mode,
                distance_m=distance,
                duration_s=edge_travel_s(profile, group["edge"], distance),
                start=list(group["start"]),
                end=list(group["end"]),
                geometry=geometry,
            )
        )
        previous_bearing = _path_end_bearing(geometry)

    out.append(
        RouteStep(
            maneuver="arrive",
            instruction="Arrive at destination",
            road_name="",
            highway="",
            mode=mode,
            distance_m=0.0,
            duration_s=0.0,
            start=list(destination_snapped),
            end=list(destination_snapped),
            geometry=[list(destination_snapped)],
        )
    )
    return out


def compute_navigation(
    graph: NavigationGraph,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    profile: str,
    weighting: str = "time",
    hazards: Iterable[dict[str, Any]] | None = None,
    floods: Iterable[dict[str, Any]] | None = None,
    closures: Iterable[dict[str, Any]] | None = None,
    max_snap_distance_m: float = MAX_SNAP_DISTANCE_M,
) -> RouteResult:
    if profile not in ALLOWED_PROFILES:
        raise NavigationError("INVALID_PROFILE", f"Unsupported routing profile {profile!r}")
    if not graph.edges or not graph.nodes:
        raise NavigationError("OSM_GRAPH_EMPTY", "No OSM road network is available to route on")

    penalties = _edge_penalties(graph, profile, hazards, floods, closures)
    origin_candidates = find_candidates(
        graph, origin_lat, origin_lng, profile, max_distance_m=max_snap_distance_m
    )
    destination_candidates = find_candidates(
        graph, destination_lat, destination_lng, profile, max_distance_m=max_snap_distance_m
    )
    origin, destination, steps = _plan_route(
        graph,
        origin_candidates,
        destination_candidates,
        profile,
        weighting,
        penalties,
    )

    coords: list[list[float]] = []

    def add_point(point: list[float]) -> None:
        if not coords or coords[-1] != point:
            coords.append(list(point))

    add_point(origin.point)
    step_geometries: list[list[list[float]]] = []
    edge_ids: list[str] = []
    unverified_width = False
    for step in steps:
        oriented = step.edge.path if step.forward else list(reversed(step.edge.path))
        sliced = _slice_path(oriented, step.t_start, step.t_end)
        if len(sliced) < 2:
            sliced = []
        step_geometries.append(sliced)
        for point in sliced:
            add_point(point)
        if step.edge.id not in edge_ids:
            edge_ids.append(step.edge.id)
        if step.edge.width_m > 0 and not step.edge.width_verified:
            unverified_width = True
    add_point(destination.point)
    if len(coords) == 1:
        coords.append(list(coords[0]))

    violations = validate_route_geometry(coords, [step.edge for step in steps])
    if violations:
        raise NavigationError(
            "ROUTE_GEOMETRY_INVALID",
            "No road-aligned route geometry could be produced: " + "; ".join(violations[:3]),
            status_code=500,
        )

    road_distance = sum(_path_length(geometry) for geometry in step_geometries)
    road_duration = sum(
        edge_travel_s(profile, step.edge, _path_length(geometry))
        for step, geometry in zip(steps, step_geometries)
    )
    access_distance = float(origin.distance_m)
    egress_distance = float(destination.distance_m)
    access_duration = access_distance / CONNECTOR_WALK_SPEED_MPS
    egress_duration = egress_distance / CONNECTOR_WALK_SPEED_MPS
    total_distance = road_distance
    total_duration = road_duration

    route_steps = _build_route_steps(
        profile,
        steps,
        step_geometries,
        destination.point,
    )

    warnings: list[str] = [
        "Route follows imported OpenStreetMap geometry, not the synthetic demo grid.",
        "Route geometry is road-only; off-road gaps are reported as snap distances.",
        "Turn-by-turn instructions are derived from OSM way geometry and highway class.",
    ]
    hazard_list = list(hazards or ())
    flood_list = list(floods or ())
    closure_list = list(closures or ())
    if hazard_list:
        warnings.append("Route avoids active fire hazard zones.")
    if flood_list:
        warnings.append("Route avoids or slows through waterlogged zones.")
    if closure_list:
        warnings.append(
            f"Route avoids {len(closure_list)} active road closure(s) reported by field operators."
        )
    if access_distance > ACCESS_WARN_DISTANCE_M:
        warnings.append(
            f"Start point is {access_distance:.0f} m off the OSM road network; "
            "the route starts at the nearest OSM road point."
        )
    if egress_distance > ACCESS_WARN_DISTANCE_M:
        warnings.append(
            f"Destination is {egress_distance:.0f} m off the OSM road network; "
            "the route ends at the nearest OSM road point."
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
        distance_m=total_distance,
        duration_s=total_duration,
        edge_ids=edge_ids,
        origin=origin,
        destination=destination,
        warnings=warnings,
        algorithm="astar_osm",
        weighting=weighting,
        steps=route_steps,
        road_distance_m=road_distance,
        road_duration_s=road_duration,
        access_distance_m=access_distance,
        access_duration_s=access_duration,
        egress_distance_m=egress_distance,
        egress_duration_s=egress_duration,
    )
