from app.routing.algorithms import chain, dijkstra
from app.routing.graph import Ctx, Graph, LaneEdgeData, LaneNodeData

NODES = [
    LaneNodeData("A", [0, 0], "Fire Post", "fire_post"),
    LaneNodeData("B", [0.001, 0], "J", "junction"),
    LaneNodeData("C", [0.002, 0], "J", "junction"),
    LaneNodeData("D", [0.001, 0.001], "J", "junction"),
    LaneNodeData("E", [0.002, 0.001], "J", "junction"),
]


def graph() -> Graph:
    edges = [
        LaneEdgeData("A-B", "A", "B", 7.0, False),
        LaneEdgeData("B-C", "B", "C", 2.0, False),
        LaneEdgeData("A-D", "A", "D", 0.5, False),
        LaneEdgeData("D-E", "D", "E", 7.0, False),
        LaneEdgeData("B-E", "B", "E", 1.5, True),
    ]
    return Graph.build(NODES, edges)


def test_fire_truck_avoids_narrow_and_stairs():
    cost, _ = dijkstra(graph(), "A", "fire_truck", Ctx())
    assert "B" in cost
    assert "C" not in cost
    assert "E" not in cost


def test_medical_blocked_by_narrow_and_stairs():
    cost, _ = dijkstra(graph(), "A", "medical", Ctx())
    assert "B" in cost
    assert "E" not in cost
    assert "D" not in cost


def test_evacuation_uses_stairs():
    cost, prev = dijkstra(graph(), "A", "evacuation", Ctx())
    assert "E" in cost
    arc_ids = [a.edge.id for a in chain(prev, "E")[1]]
    assert "B-E" in arc_ids


def test_hazard_increases_cost():
    g = graph()
    clean, _ = dijkstra(g, "A", "evacuation", Ctx())
    hazard, _ = dijkstra(g, "A", "evacuation", Ctx(hazards=[{"pos": [0.0005, 0], "radius_m": 30}]))
    assert hazard["E"] > clean["E"]


def test_deep_flood_blocks_fire_truck():
    ctx = Ctx(floods=[{"pos": [0.001, 0], "radius_m": 60, "depth_cm": 30}])
    cost, _ = dijkstra(graph(), "A", "fire_truck", ctx)
    assert "B" not in cost


def test_no_path_disconnected():
    g = Graph.build(NODES, [LaneEdgeData("A-B", "A", "B", 7.0, False)])
    cost, prev = dijkstra(g, "A", "medical", Ctx())
    assert "C" not in cost
    assert "E" not in cost


def test_chain_reconstructs_path():
    cost, prev = dijkstra(graph(), "A", "evacuation", Ctx())
    ids, arcs = chain(prev, "E")
    assert ids[0] == "A"
    assert ids[-1] == "E"
    assert len(arcs) == len(ids) - 1
