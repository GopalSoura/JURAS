"""Unit tests for the simulation-time OSM route planner (WS Route payloads)."""

import pytest

from app.routing.osm_graph import OsmWayInput, build_navigation_graph
from app.services.simulation_navigation_service import plan_osm_routes_for_building


def way(code: str, path, *, highway="secondary"):
    return OsmWayInput(
        code=code,
        name=f"Way {code}",
        path=path,
        width_m=6.0,
        highway=highway,
        tags={"highway": highway},
    )


def demo_graph():
    main = way(
        "OSM-1",
        [[74.8575, 32.7285], [74.8580, 32.7285], [74.8595, 32.7285]],
        highway="secondary",
    )
    branch = way("OSM-2", [[74.8580, 32.7285], [74.8580, 32.7295]], highway="residential")
    return build_navigation_graph([main, branch])


def test_plan_osm_routes_maps_profiles_and_keeps_ws_route_shape():
    routes = plan_osm_routes_for_building(
        demo_graph(),
        building_center=[74.8590, 32.7285],
        building_name="Block 14",
        fire_post=[74.8576, 32.7285],
        medical_post=[74.8594, 32.7285],
        assemblies=[[74.8580, 32.7295]],
        fire_label="Fire Post A",
        medical_label="Medical Post E",
        assembly_labels=["Assembly G"],
    )
    assert routes is not None
    assert [route["profile"] for route in routes] == ["fire_truck", "medical", "evacuation"]
    for route in routes:
        assert route["feasible"] is True
        assert route["length_m"] > 0
        assert route["eta_s"] >= route["travel_s"] > 0
        assert route["path"]
        assert route["from"]
        assert route["to"]
        assert route["steps"]
        assert route["steps"][0]["instruction"]
    fire = routes[0]
    assert fire["from"] == "Fire Post A"
    assert fire["to"] == "Block 14"
    assert fire["path"][0] == pytest.approx([74.8576, 32.7285])
    evacuation = routes[2]
    assert evacuation["to"] == "Assembly G"
    assert evacuation["path"][0] == pytest.approx([74.8590, 32.7285])
    assert evacuation["path"][-1] == pytest.approx([74.8580, 32.7295])


def test_plan_osm_routes_returns_empty_paths_without_osm_graph():
    routes = plan_osm_routes_for_building(
        None,
        building_center=[74.8590, 32.7285],
        building_name="Block 14",
        fire_post=[74.8576, 32.7285],
        medical_post=[74.8594, 32.7285],
        assemblies=[[74.8580, 32.7295]],
        fire_label="Fire Post A",
        medical_label="Medical Post E",
        assembly_labels=["Assembly G"],
    )
    assert [route["profile"] for route in routes] == ["fire_truck", "medical", "evacuation"]
    for route in routes:
        assert route["feasible"] is False
        assert route["path"] == []
        assert route["length_m"] == 0
        assert route["travel_s"] == 0
        assert route["eta_s"] == 0
        assert "No OSM road graph" in route["note"]
    assert routes[0]["from"] == "Fire Post A"
    assert routes[1]["from"] == "Medical Post E"
    assert routes[2]["to"] == "Assembly G"


def test_plan_osm_routes_reports_infeasible_profile_without_fabricated_path():
    only_road = way("OSM-3", [[74.8575, 32.7285], [74.8580, 32.7285]])
    graph = build_navigation_graph([only_road])
    routes = plan_osm_routes_for_building(
        graph,
        building_center=[74.8700, 32.7285],
        building_name="Block 14",
        fire_post=[74.8576, 32.7285],
        medical_post=[74.8594, 32.7285],
        assemblies=[[74.8580, 32.7295]],
    )
    assert all("feasible" in route for route in routes)
    assert all(route["feasible"] is False for route in routes)
    assert all(route["path"] == [] for route in routes)
    assert all(route["length_m"] == 0 for route in routes)
    assert all(route["note"] for route in routes)
