import math
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RESPONDER_PROFILE, ResponderType, Profile
from app.core.exceptions import NotFoundError, ValidationAppError
from app.repositories import building_repo, lane_repo
from app.routing.graph import Ctx, Graph, LaneEdgeData, LaneNodeData, dist_m_sqrt
from app.routing.algorithms import SPEC, chain, dijkstra, speed
from app.state import app_state

POSTS = {"fire": "A", "medical": "E", "assemblies": ["G", "Q"]}


async def build_graph_from_db(session: AsyncSession) -> Graph:
    nodes = await lane_repo.list_nodes(session)
    lanes = await lane_repo.list_lanes(session)
    node_data = [LaneNodeData(id=n.code, pos=n.pos, label=n.label, kind=n.kind) for n in nodes]
    edge_data = [
        LaneEdgeData(id=l.code, a=l.node_a_code, b=l.node_b_code, width_m=l.width_m, stairs=l.stairs)
        for l in lanes
    ]
    return Graph.build(node_data, edge_data)


def _snap_to_node(g: Graph, lat: float, lon: float) -> str:
    best_id = None
    best = float("inf")
    for node_id, n in g.nodes.items():
        d = dist_m_sqrt([lon, lat], n.pos)
        if d < best:
            best = d
            best_id = node_id
    if best_id is None:
        raise ValidationAppError("GRAPH_EMPTY", "Lane graph is empty; seed demo data first")
    return best_id


async def plan_route(
    session: AsyncSession,
    origin: dict[str, float] | None,
    destination_building_id: str | None,
    destination_node_code: str | None,
    responder_type: str,
    route_id_prefix: str = "RT",
) -> dict[str, Any]:
    profile = RESPONDER_PROFILE[ResponderType(responder_type)].value
    g = await build_graph_from_db(session)
    if not g.nodes:
        raise ValidationAppError("GRAPH_EMPTY", "Lane graph is empty; seed demo data first")

    warnings: list[str] = ["Geometry is illustrative demo data, not surveyed."]
    ctx_data = app_state.routing_ctx()
    if ctx_data["hazards"]:
        warnings.append("Route avoids active fire hazard zones.")
    if ctx_data["floods"]:
        warnings.append("Route avoids or slows through waterlogged zones.")

    dest_node: str | None = None
    dest_pos: list[float] | None = None
    dest_name: str | None = None
    if destination_building_id:
        building = await building_repo.get_by_id(session, destination_building_id)
        if building is None:
            raise NotFoundError(
                "BUILDING_NOT_FOUND", f"Destination building {destination_building_id} does not exist"
            )
        dest_node = building.access_node_code
        dest_pos = building.center
        dest_name = building.name
    else:
        node = await lane_repo.get_node_by_code(session, destination_node_code)
        if node is None:
            raise NotFoundError("NODE_NOT_FOUND", f"Destination node {destination_node_code} not found")
        dest_node = node.code
        dest_pos = node.pos
        dest_name = node.label

    if origin:
        src = _snap_to_node(g, origin["lat"], origin["lon"])
    else:
        src = POSTS["fire"] if profile == "fire_truck" else POSTS["medical"]

    cost, prev = dijkstra(g, src, profile, Ctx(**ctx_data))
    if dest_node not in cost:
        reachable = [
            (dist_m_sqrt(g.nodes[nid].pos, dest_pos), nid) for nid in cost if nid != src
        ]
        if not reachable:
            return {
                "route_id": f"{route_id_prefix}-NONE",
                "responder_type": responder_type,
                "profile": profile,
                "geometry": {"type": "LineString", "coordinates": []},
                "distance_m": 0,
                "travel_s": 0,
                "eta_s": 0,
                "edge_ids": [],
                "warnings": ["No reachable path from origin to destination"],
                "algorithm": "dijkstra",
                "feasible": False,
                "last_mile_m": 0,
                "note": "No safe route found.",
            }
        reachable.sort()
        dest_node = reachable[0][1]
        warnings.append("Direct access blocked; vehicle stops at nearest reachable node.")

    ids, arcs = chain(prev, dest_node)
    if not arcs and src != dest_node:
        return {
            "route_id": f"{route_id_prefix}-NONE",
            "responder_type": responder_type,
            "profile": profile,
            "geometry": {"type": "LineString", "coordinates": []},
            "distance_m": 0,
            "travel_s": 0,
            "eta_s": 0,
            "edge_ids": [],
            "warnings": ["No reachable path from origin to destination"],
            "algorithm": "dijkstra",
            "feasible": False,
            "last_mile_m": 0,
            "note": "No safe route found.",
        }
    path = [g.nodes[i].pos for i in ids]
    length = sum(a.len for a in arcs)
    travel = sum(a.len / speed(profile, a.edge) for a in arcs)
    last_mile = dist_m_sqrt(g.nodes[dest_node].pos, dest_pos) if dest_pos else 0.0
    foot_speed = 1.2 if profile != "evacuation" else 1.3
    eta = travel + (last_mile / foot_speed if profile != "evacuation" else 0.0)
    tightest = min((a.edge.width_m for a in arcs), default=0.0)
    edge_ids = [a.edge.id for a in arcs]
    if tightest and tightest < 4.0:
        warnings.append(f"Tight lane on route: {tightest:.1f} m clear width")
    if any(a.edge.stairs for a in arcs):
        warnings.append("Route includes stairs segment")
    note = (
        f"Route to {dest_name}. Tightest lane {tightest:.1f} m."
        if tightest
        else f"Route to {dest_name}."
    )
    return {
        "route_id": f"{route_id_prefix}-{uuid.uuid4().hex[:8]}",
        "responder_type": responder_type,
        "profile": profile,
        "geometry": {"type": "LineString", "coordinates": path},
        "distance_m": int(round(length)),
        "travel_s": int(round(travel)),
        "eta_s": int(round(eta)),
        "edge_ids": edge_ids,
        "warnings": warnings,
        "algorithm": "dijkstra",
        "feasible": True,
        "last_mile_m": int(round(last_mile)),
        "note": note,
    }


async def plan_routes_for_building(
    session: AsyncSession, building: Any, graph: Graph
) -> list[dict[str, Any]]:
    """Three-profile plan mirroring the frontend routing rules (fire/medical/evacuation)."""
    ctx_data = app_state.routing_ctx()
    ctx = Ctx(**ctx_data)
    out: list[dict[str, Any]] = []
    b = building
    for profile, src in (
        ("fire_truck", POSTS["fire"]),
        ("medical", POSTS["medical"]),
        ("evacuation", None),
    ):
        if profile == "evacuation":
            src = b.access_node_code
        cost, prev = dijkstra(graph, src, profile, ctx)
        target = b.access_node_code
        if profile != "evacuation" and target not in cost:
            reachable = [
                (dist_m_sqrt(graph.nodes[nid].pos, b.center), nid)
                for nid in cost
                if nid != src
            ]
            if not reachable:
                out.append(
                    {
                        "profile": profile,
                        "path": [],
                        "foot_path": [],
                        "length_m": 0,
                        "travel_s": 0,
                        "eta_s": 0,
                        "feasible": False,
                        "last_mile_m": 0,
                        "note": "No reachable lane; blocked off.",
                        "from": graph.nodes[src].label,
                        "to": b.name,
                    }
                )
                continue
            reachable.sort()
            target = reachable[0][1]
        if profile == "evacuation":
            best = None
            best_cost = float("inf")
            for aid in POSTS["assemblies"]:
                c = cost.get(aid)
                if c is not None and c < best_cost:
                    best_cost = c
                    best = aid
            if best is None:
                out.append(
                    {
                        "profile": "evacuation",
                        "path": [b.center, graph.nodes[b.access_node_code].pos],
                        "foot_path": [],
                        "length_m": 0,
                        "travel_s": 0,
                        "eta_s": 0,
                        "feasible": False,
                        "last_mile_m": 0,
                        "note": "No safe route found. Shelter in place and call for rescue.",
                        "from": b.name,
                        "to": "assembly",
                    }
                )
                continue
            target = best
        ids, arcs = chain(prev, target)
        path = [graph.nodes[i].pos for i in ids]
        length = sum(a.len for a in arcs)
        travel = sum(a.len / speed(profile, a.edge) for a in arcs)
        if profile == "evacuation":
            first = dist_m_sqrt(b.center, graph.nodes[b.access_node_code].pos)
            out.append(
                {
                    "profile": "evacuation",
                    "path": [b.center] + path,
                    "foot_path": [],
                    "length_m": int(round(length + first)),
                    "travel_s": int(round(travel + first / 1.3)),
                    "eta_s": int(round(travel + first / 1.3)),
                    "feasible": True,
                    "last_mile_m": 0,
                    "note": f"To {graph.nodes[target].label}.",
                    "from": b.name,
                    "to": graph.nodes[target].label,
                }
            )
        else:
            last_mile = dist_m_sqrt(graph.nodes[target].pos, b.center)
            walk = 1.2 if profile == "fire_truck" else 1.3
            out.append(
                {
                    "profile": profile,
                    "path": path,
                    "foot_path": [graph.nodes[target].pos, b.center],
                    "length_m": int(round(length)),
                    "travel_s": int(round(travel)),
                    "eta_s": int(round(travel + last_mile / walk)),
                    "feasible": True,
                    "last_mile_m": int(round(last_mile)),
                    "note": f"To {graph.nodes[target].label}. Last {int(round(last_mile))} m on foot.",
                    "from": graph.nodes[src].label,
                    "to": graph.nodes[target].label,
                }
            )
    return out
