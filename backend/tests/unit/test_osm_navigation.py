"""Unit tests for the real OSM navigation graph (no database required)."""

import math

import pytest

from app.routing.osm_graph import (
    NavigationError,
    OsmWayInput,
    build_navigation_graph,
    compute_navigation,
    find_candidates,
    validate_route_geometry,
)


def way(code: str, path, *, highway="residential", width=6.0, tags=None, blocked=False, vehicle_access=True):
    return OsmWayInput(
        code=code,
        name=f"Way {code}",
        path=path,
        width_m=width,
        highway=highway,
        tags={"highway": highway, **(tags or {})},
        blocked=blocked,
        vehicle_access=vehicle_access,
    )


def straight_two_way_graph():
    a = way("OSM-1", [[74.8575, 32.7285], [74.8580, 32.7285], [74.8590, 32.7285]], highway="secondary")
    b = way("OSM-2", [[74.8580, 32.7285], [74.8580, 32.7300]], width=4.0)
    return build_navigation_graph([a, b])


def test_shared_interior_vertex_connects_ways_and_returns_real_geometry():
    graph = straight_two_way_graph()
    result = compute_navigation(graph, 32.7285, 74.8576, 32.7300, 74.8580, "fire_truck")
    assert result.distance_m == pytest.approx(203.3, abs=1.5)
    assert result.edge_ids == ["OSM-1#1", "OSM-2#1"]
    assert [74.8580, 32.7285] in result.geometry
    assert result.geometry[-1] == pytest.approx([74.8580, 32.7300])
    assert result.duration_s and result.duration_s > 0


def test_geometry_follows_bend_vertices_not_straight_line():
    bent = way(
        "OSM-10",
        [[74.8575, 32.7285], [74.8580, 32.7285], [74.8580, 32.7290], [74.8590, 32.7290]],
    )
    graph = build_navigation_graph([bent])
    result = compute_navigation(graph, 32.7285, 74.8576, 32.7290, 74.8590, "walking")
    assert [74.8580, 32.7285] in result.geometry
    assert [74.8580, 32.7290] in result.geometry
    straight = math.hypot((74.8590 - 74.8576) * 93659.0, (32.7290 - 32.7285) * 110574.0)
    assert result.distance_m > straight


def test_oneway_forward_blocks_reverse_direction():
    one = way("OSM-11", [[74.8575, 32.7285], [74.8590, 32.7285]], tags={"oneway": "yes"})
    graph = build_navigation_graph([one])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 32.7285, 74.8588, 32.7285, 74.8576, "fire_truck")
    assert exc.value.code == "ROUTE_NOT_FOUND"
    ok = compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8588, "fire_truck")
    assert ok.distance_m > 0


def test_falls_back_to_another_routable_snap_pair():
    one = way(
        "OSM-80",
        [[74.8500, 32.7280], [74.8650, 32.7280]],
        highway="primary",
        tags={"oneway": "yes"},
    )
    parallel = way(
        "OSM-81",
        [[74.8500, 32.7280], [74.8500, 32.7250], [74.8650, 32.7250]],
    )
    graph = build_navigation_graph([one, parallel])
    result = compute_navigation(graph, 32.7270, 74.8649, 32.7280, 74.8550, "fire_truck")
    assert result.origin.edge.id == "OSM-81#1"
    assert result.destination.edge.id == "OSM-80#1"
    assert result.distance_m > 0


def test_walking_ignores_vehicle_oneway_restriction():
    one = way("OSM-82", [[74.8575, 32.7285], [74.8590, 32.7285]], tags={"oneway": "yes"})
    graph = build_navigation_graph([one])
    walked = compute_navigation(graph, 32.7285, 74.8588, 32.7285, 74.8576, "walking")
    assert walked.distance_m > 0
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 32.7285, 74.8588, 32.7285, 74.8576, "fire_truck")
    assert exc.value.code == "ROUTE_NOT_FOUND"


def test_oneway_terminal_destination_can_be_reached_from_another_road():
    one = way("OSM-72", [[74.8575, 32.7285], [74.8590, 32.7285]], tags={"oneway": "yes"})
    branch = way("OSM-73", [[74.8590, 32.7270], [74.8590, 32.7285]])
    graph = build_navigation_graph([one, branch])
    result = compute_navigation(graph, 32.7284, 74.8590, 32.7285, 74.8590, "fire_truck")
    assert result.destination.edge.id == "OSM-72#1"
    assert result.edge_ids == ["OSM-73#1"]
    assert result.distance_m == pytest.approx(11.1, abs=1.0)


def test_oneway_reverse_tag_is_honoured():
    one = way("OSM-12", [[74.8575, 32.7285], [74.8590, 32.7285]], tags={"oneway": "-1"})
    graph = build_navigation_graph([one])
    with pytest.raises(NavigationError):
        compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8588, "fire_truck")
    result = compute_navigation(graph, 32.7285, 74.8588, 32.7285, 74.8576, "fire_truck")
    assert result.distance_m > 0


def test_roundabout_is_implicit_oneway():
    ring = way(
        "OSM-13",
        [[74.8575, 32.7285], [74.8590, 32.7285], [74.8590, 32.7300]],
        tags={"junction": "roundabout"},
    )
    graph = build_navigation_graph([ring])
    assert all(edge.oneway == "forward" for edge in graph.edges.values())


def test_footway_only_reachable_on_foot_or_bike():
    main = way("OSM-20", [[74.8575, 32.7285], [74.8580, 32.7285]], highway="secondary")
    foot = way(
        "OSM-21",
        [[74.8580, 32.7285], [74.8580, 32.7400]],
        highway="footway",
        width=1.5,
        vehicle_access=False,
    )
    graph = build_navigation_graph([main, foot])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 32.7285, 74.8576, 32.7400, 74.8580, "fire_truck")
    assert exc.value.code == "DESTINATION_OUT_OF_NETWORK"
    walked = compute_navigation(graph, 32.7285, 74.8576, 32.7400, 74.8580, "walking")
    assert walked.distance_m > 0
    biked = compute_navigation(graph, 32.7285, 74.8576, 32.7400, 74.8580, "responder_bike")
    assert biked.distance_m > 0


def test_stairs_block_vehicles_but_allow_walking():
    main = way("OSM-22", [[74.8575, 32.7285], [74.8580, 32.7285]], highway="secondary")
    steps = way("OSM-23", [[74.8580, 32.7285], [74.8580, 32.7400]], highway="steps", width=2.0)
    graph = build_navigation_graph([main, steps])
    for profile in ("fire_truck", "responder_bike"):
        with pytest.raises(NavigationError) as exc:
            compute_navigation(graph, 32.7285, 74.8576, 32.7400, 74.8580, profile)
        assert exc.value.code == "DESTINATION_OUT_OF_NETWORK"
    result = compute_navigation(graph, 32.7285, 74.8576, 32.7400, 74.8580, "walking")
    assert result.distance_m > 0


def test_maxwidth_blocks_fire_truck():
    road = way(
        "OSM-24",
        [[74.8575, 32.7285], [74.8590, 32.7285]],
        highway="service",
        width=4.0,
        tags={"maxwidth": "2.0"},
    )
    graph = build_navigation_graph([road])
    with pytest.raises(NavigationError):
        compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8588, "fire_truck")
    result = compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8588, "responder_bike")
    assert result.distance_m > 0


def test_blocked_lane_is_not_routable():
    road = way("OSM-25", [[74.8575, 32.7285], [74.8590, 32.7285]], blocked=True)
    graph = build_navigation_graph([road])
    assert graph.edges
    with pytest.raises(NavigationError):
        compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8588, "walking")


def test_disconnected_components_raise_meaningful_error():
    left = way("OSM-30", [[74.8570, 32.7280], [74.8580, 32.7280]])
    right = way("OSM-31", [[74.8800, 32.7280], [74.8810, 32.7280]])
    graph = build_navigation_graph([left, right])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 32.7280, 74.8575, 32.7280, 74.8805, "fire_truck")
    assert exc.value.code == "ROUTE_NOT_FOUND"
    assert exc.value.status_code == 404
    assert "disconnected" in exc.value.message.lower()


def test_origin_and_destination_out_of_network_are_reported():
    graph = straight_two_way_graph()
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 33.5, 75.5, 32.7300, 74.8580, "fire_truck")
    assert exc.value.code == "ORIGIN_OUT_OF_NETWORK"
    with pytest.raises(NavigationError) as exc2:
        compute_navigation(graph, 32.7285, 74.8576, 33.5, 75.5, "fire_truck")
    assert exc2.value.code == "DESTINATION_OUT_OF_NETWORK"


def test_snapping_projects_to_road_and_reports_distance():
    graph = straight_two_way_graph()
    candidates = find_candidates(graph, 32.7287, 74.8577, "walking")
    assert candidates
    best = candidates[0]
    assert best.distance_m == pytest.approx(22.2, abs=1.5)
    assert best.point[1] == pytest.approx(32.7285, abs=1e-6)


def test_degenerate_and_invalid_geometry_is_skipped():
    graph = build_navigation_graph(
        [
            way("OSM-40", [[74.8575, 32.7285]]),
            way("OSM-41", [[74.8580, 32.7285], [74.8580, 32.7285]]),
            way("OSM-42", [[float("nan"), 32.7285], [74.8590, 32.7285]]),
            way("OSM-43", [[74.8575, 32.7285], [74.8590, 32.7285]]),
        ]
    )
    assert list(graph.edges) == ["OSM-43#1"]


def test_graph_construction_is_deterministic():
    def build():
        return build_navigation_graph(
            [
                way("OSM-50", [[74.8575, 32.7285], [74.8580, 32.7285]]),
                way("OSM-51", [[74.8580, 32.7285], [74.8580, 32.7300]]),
            ]
        )

    first, second = build(), build()
    assert list(first.nodes) == list(second.nodes)
    assert list(first.edges) == list(second.edges)
    assert first.components == second.components


def test_distance_weighting_returns_distance_but_still_reports_duration():
    graph = straight_two_way_graph()
    result = compute_navigation(
        graph, 32.7285, 74.8576, 32.7300, 74.8580, "walking", weighting="distance"
    )
    assert result.weighting == "distance"
    assert result.distance_m > 0
    assert result.duration_s and result.duration_s > 0


def test_profile_restriction_never_falls_back_to_nearest_reachable_node():
    main = way("OSM-60", [[74.8575, 32.7285], [74.8580, 32.7285]], highway="secondary")
    foot = way(
        "OSM-61",
        [[74.8580, 32.7285], [74.8580, 32.7380]],
        highway="footway",
        width=1.5,
        vehicle_access=False,
    )
    graph = build_navigation_graph([main, foot])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 32.7285, 74.8576, 32.7380, 74.8580, "fire_truck")
    assert exc.value.code in ("ROUTE_NOT_FOUND", "DESTINATION_OUT_OF_NETWORK")


def test_turn_by_turn_steps_follow_osm_ways():
    graph = straight_two_way_graph()
    result = compute_navigation(graph, 32.7285, 74.8576, 32.7300, 74.8580, "fire_truck")
    assert result.steps
    assert result.steps[0].maneuver == "depart"
    assert result.steps[-1].maneuver == "arrive"
    assert any(step.maneuver == "turn-left" for step in result.steps)
    assert all(step.instruction for step in result.steps)
    road_steps = [step for step in result.steps if step.mode != "walk"]
    assert sum(step.distance_m for step in road_steps) == pytest.approx(result.road_distance_m, abs=0.5)
    assert result.steps[0].geometry[0] == pytest.approx([74.8576, 32.7285])
    assert result.geometry[0] == pytest.approx([74.8576, 32.7285])
    assert result.geometry[-1] == pytest.approx([74.8580, 32.7300])


def test_offroad_connectors_are_excluded_from_geometry_and_totals():
    road = way("OSM-70", [[74.8575, 32.7285], [74.8600, 32.7285]], highway="secondary")
    graph = build_navigation_graph([road])
    origin = [74.8580, 32.7285 + 20.0 / 110574.0]
    destination = [74.8590, 32.7285 + 15.0 / 110574.0]
    result = compute_navigation(
        graph, origin[1], origin[0], destination[1], destination[0], "responder_bike"
    )
    assert result.geometry[0] == pytest.approx([74.8580, 32.7285])
    assert result.geometry[-1] == pytest.approx([74.8590, 32.7285])
    assert origin not in result.geometry
    assert destination not in result.geometry
    assert result.access_distance_m == pytest.approx(20.0, abs=1.0)
    assert result.egress_distance_m == pytest.approx(15.0, abs=1.0)
    assert result.steps[0].maneuver == "depart"
    assert all(step.mode != "walk" for step in result.steps)
    assert result.steps[-1].maneuver == "arrive"
    assert result.distance_m == pytest.approx(result.road_distance_m, abs=0.5)
    assert result.duration_s == pytest.approx(result.road_duration_s, abs=0.5)
    assert validate_route_geometry(result.geometry, list(graph.edges.values())) == []


def test_route_geometry_validation_flags_offroad_connector():
    road = way("OSM-74", [[74.8575, 32.7285], [74.8600, 32.7285]], highway="secondary")
    graph = build_navigation_graph([road])
    edge = next(iter(graph.edges.values()))
    offroad = [74.8580, 32.7285 + 50.0 / 110574.0]
    onroad = [74.8580, 32.7285]
    violations = validate_route_geometry([offroad, onroad], [edge])
    assert violations
    assert "off the OSM road network" in violations[0]
    assert validate_route_geometry([onroad, onroad], [edge]) == []


def test_near_but_disconnected_roads_are_not_joined():
    left = way("OSM-90", [[74.85750, 32.72850], [74.85800, 32.72850]])
    right = way("OSM-91", [[74.85809, 32.72850], [74.85850, 32.72850]])
    graph = build_navigation_graph([left, right])
    origin = (32.72850, 74.85760)
    destination = (32.72850, 74.85840)
    with pytest.raises(NavigationError) as exc:
        compute_navigation(
            graph, *origin, *destination, "fire_truck", max_snap_distance_m=4.0
        )
    assert exc.value.code == "ROUTE_NOT_FOUND"
    assert exc.value.status_code == 404
    assert "disconnected" in exc.value.message.lower()


def test_zero_length_snap_pair_reports_no_route():
    road = way("OSM-92", [[74.8575, 32.7285], [74.8600, 32.7285]], highway="secondary")
    graph = build_navigation_graph([road])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(
            graph, 32.7285, 74.8575, 32.7285, 74.8575 + 1e-9, "fire_truck"
        )
    assert exc.value.code == "ROUTE_NOT_FOUND"
    assert "same" in exc.value.message.lower()


def test_narrow_lane_blocks_fire_truck_but_not_bike_or_walking():
    narrow = way(
        "OSM-93",
        [[74.8575, 32.7285], [74.8600, 32.7285]],
        highway="service",
        width=2.0,
    )
    graph = build_navigation_graph([narrow])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8599, "fire_truck")
    assert exc.value.code == "ORIGIN_OUT_OF_NETWORK"
    biked = compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8599, "responder_bike")
    walked = compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8599, "walking")
    assert biked.distance_m > 0
    assert walked.distance_m > 0


def test_hazard_penalty_reroutes_around_blocked_zone():
    direct = way("OSM-71", [[74.8575, 32.7285], [74.8595, 32.7285]], highway="secondary")
    detour = way(
        "OSM-72",
        [
            [74.8575, 32.7285],
            [74.8575, 32.7295],
            [74.8595, 32.7295],
            [74.8595, 32.7285],
        ],
        highway="secondary",
    )
    graph = build_navigation_graph([direct, detour])
    plain = compute_navigation(graph, 32.7285, 74.8576, 32.7285, 74.8595, "fire_truck")
    hazard = [{"pos": [74.8585, 32.7285], "radius_m": 10.0}]
    avoided = compute_navigation(
        graph, 32.7285, 74.8576, 32.7285, 74.8595, "fire_truck", hazards=hazard
    )
    assert any("fire hazard" in warning for warning in avoided.warnings)
    assert avoided.distance_m > plain.distance_m * 1.5
    assert "OSM-72#1" in avoided.edge_ids


def test_deep_flood_blocks_fire_truck_but_not_walking():
    graph = straight_two_way_graph()
    floods = [{"pos": [74.8580, 32.7285], "radius_m": 10.0, "depth_cm": 30.0}]
    with pytest.raises(NavigationError) as exc:
        compute_navigation(
            graph, 32.7285, 74.8576, 32.7285, 74.8590, "fire_truck", floods=floods
        )
    assert exc.value.code == "ROUTE_NOT_FOUND"

    walked = compute_navigation(
        graph, 32.7285, 74.8576, 32.7285, 74.8590, "walking", floods=floods
    )
    assert walked.distance_m > 0
    assert any("waterlogged" in warning for warning in walked.warnings)


def test_operator_road_closure_forces_alternative_route():
    main = way(
        "CL-1",
        [[74.8575, 32.7285], [74.8585, 32.7285], [74.8595, 32.7285]],
        highway="secondary",
    )
    detour = way(
        "CL-2",
        [
            [74.8585, 32.7285],
            [74.8585, 32.7290],
            [74.8595, 32.7290],
            [74.8595, 32.7285],
        ],
        highway="secondary",
    )
    graph = build_navigation_graph([main, detour])
    origin = (32.7285, 74.8576)
    destination = (32.7285, 74.8594)

    baseline = compute_navigation(graph, *origin, *destination, "fire_truck")
    assert baseline.edge_ids == ["CL-1#1", "CL-1#2"]

    rerouted = compute_navigation(
        graph,
        *origin,
        *destination,
        "fire_truck",
        closures=[{"pos": [74.8590, 32.7285], "radius_m": 25.0}],
    )
    assert "CL-1#2" not in rerouted.edge_ids
    assert "CL-2#1" in rerouted.edge_ids
    assert rerouted.distance_m > baseline.distance_m
    assert any("road closure" in warning for warning in rerouted.warnings)


def test_road_closure_with_no_alternative_raises_route_not_found():
    only = way("CL-3", [[74.8575, 32.7285], [74.8595, 32.7285]], highway="secondary")
    graph = build_navigation_graph([only])
    with pytest.raises(NavigationError) as exc:
        compute_navigation(
            graph,
            32.7285,
            74.8576,
            32.7285,
            74.8594,
            "fire_truck",
            closures=[{"pos": [74.8585, 32.7285], "radius_m": 15.0}],
        )
    assert exc.value.code == "ROUTE_NOT_FOUND"
