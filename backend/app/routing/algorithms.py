from __future__ import annotations

from typing import Any

from app.routing.graph import Arc, Ctx, Graph, dist_m_sqrt, midpoint

SPEC = {
    "fire_truck": {"min_width": 3.5, "stairs": False},
    "medical": {"min_width": 1.2, "stairs": False},
    "evacuation": {"min_width": 0.9, "stairs": True},
}


def speed(profile: str, edge: Arc.edge) -> float:
    if profile == "fire_truck":
        return 8.0 if edge.width_m >= 6 else 4.2
    if profile == "medical":
        return 5.5 if edge.width_m >= 2.4 else 1.5
    return 0.8 if edge.stairs else 1.3


def arc_cost(g: Graph, profile: str, arc: Arc, from_node: str, ctx: Ctx) -> float | None:
    e = arc.edge
    spec = SPEC[profile]
    if e.width_m < spec["min_width"]:
        return None
    if e.stairs and not spec["stairs"]:
        return None
    a_pos = g.nodes[from_node].pos
    b_pos = g.nodes[arc.to].pos
    mid = midpoint(a_pos, b_pos)
    mult = 1.0
    for c in ctx.closures:
        if dist_m_sqrt(mid, c["pos"]) <= c.get("radius_m", 15.0):
            return None
    for h in ctx.hazards:
        if dist_m_sqrt(mid, h["pos"]) <= h["radius_m"] + 10:
            mult *= 6
    for f in ctx.floods:
        if dist_m_sqrt(mid, f["pos"]) <= f["radius_m"] + 6:
            if profile == "fire_truck" and f["depth_cm"] >= 25:
                return None
            mult *= 1 + f["depth_cm"] / 30
    return (arc.len / speed(profile, e)) * mult


def dijkstra(g: Graph, src: str, profile: str, ctx: Ctx) -> tuple[dict[str, float], dict[str, tuple[str, Arc]]]:
    cost: dict[str, float] = {src: 0.0}
    prev: dict[str, tuple[str, Arc]] = {}
    done: set[str] = set()
    while True:
        u: str | None = None
        best = float("inf")
        for node_id, c in cost.items():
            if node_id not in done and c < best:
                best = c
                u = node_id
        if u is None:
            break
        done.add(u)
        for arc in g.adj.get(u, []):
            c = arc_cost(g, profile, arc, u, ctx)
            if c is None:
                continue
            nc = best + c
            if nc < cost.get(arc.to, float("inf")):
                cost[arc.to] = nc
                prev[arc.to] = (u, arc)
    return cost, prev


def chain(prev: dict[str, tuple[str, Arc]], to: str) -> tuple[list[str], list[Arc]]:
    ids = [to]
    arcs: list[Arc] = []
    cur = to
    while cur in prev:
        from_node, arc = prev[cur]
        arcs.insert(0, arc)
        ids.insert(0, from_node)
        cur = from_node
    return ids, arcs
