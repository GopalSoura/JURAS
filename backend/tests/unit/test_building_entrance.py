"""Building-entrance helpers keep response routes at the front of a building."""

from types import SimpleNamespace

import pytest

from app.routing.building_access import entrance_point, trim_route_to_entrance
from app.routing.graph import dist_m_sqrt

# B-052 (Mubarak Dharamshala) as seeded in the demo data.
B052_FOOTPRINT = [
    [74.85858800437144, 32.727400423613986],
    [74.85879832764586, 32.727431832114654],
    [74.85876124197792, 32.727609958573495],
    [74.8585509187035, 32.72757855007283],
    [74.85858800437144, 32.727400423613986],
]
B052_CENTRE = [74.85867462317468, 32.72750519109374]
B052_ROAD_APPROACH = [74.8593736, 32.7272826]


def test_b052_entrance_stops_on_the_approach_facing_edge():
    gate = entrance_point(B052_FOOTPRINT, B052_ROAD_APPROACH, B052_CENTRE)

    assert gate is not None
    assert gate == pytest.approx([74.8587908, 32.7274682], abs=1e-6)
    # The frontage gate is outside the building centre and before it when
    # arriving from the mapped road, so the line no longer cuts through it.
    assert dist_m_sqrt(B052_ROAD_APPROACH, gate) < dist_m_sqrt(
        B052_ROAD_APPROACH, B052_CENTRE
    )
    assert dist_m_sqrt(B052_CENTRE, gate) > 5.0
    # It lies on the east/front edge of the footprint.
    assert min(B052_FOOTPRINT[1][0], B052_FOOTPRINT[2][0]) <= gate[0] <= max(
        B052_FOOTPRINT[1][0], B052_FOOTPRINT[2][0]
    )
    assert min(B052_FOOTPRINT[1][1], B052_FOOTPRINT[2][1]) <= gate[1] <= max(
        B052_FOOTPRINT[1][1], B052_FOOTPRINT[2][1]
    )


def test_entrance_falls_back_to_the_nearest_frontage_for_inside_snaps():
    gate = entrance_point(B052_FOOTPRINT, B052_CENTRE, B052_CENTRE)

    # A snap already at the centre is degenerate; the helper must not invent
    # a point or crash. Callers keep the original destination in that case.
    assert gate is None or dist_m_sqrt(gate, B052_CENTRE) > 0.5


def test_entrance_requires_a_real_building_outline():
    assert entrance_point([], B052_ROAD_APPROACH, B052_CENTRE) is None
    assert entrance_point(B052_FOOTPRINT, B052_ROAD_APPROACH, B052_ROAD_APPROACH) is None


def test_trim_route_moves_the_last_point_to_the_frontage():
    result = SimpleNamespace(
        geometry=[list(B052_ROAD_APPROACH), list(B052_CENTRE)],
        destination=SimpleNamespace(point=list(B052_ROAD_APPROACH), distance_m=69.9),
        egress_distance_m=69.9,
        egress_duration_s=69.9 / 1.3,
        warnings=[
            "Destination is 70 m off the OSM road network; a short connector links the last mapped road to it."
        ],
    )

    gate = trim_route_to_entrance(
        result, B052_FOOTPRINT, B052_CENTRE, "Mubarak Dharamshala"
    )

    assert gate is not None
    assert result.geometry[-1] == gate
    assert result.geometry[-1] != pytest.approx(B052_CENTRE)
    assert result.egress_distance_m < 69.9
    assert result.destination.distance_m == pytest.approx(result.egress_distance_m)
    assert not any(warning.startswith("Destination is ") for warning in result.warnings)
    assert any(
        "street-facing entrance of Mubarak Dharamshala" in warning
        for warning in result.warnings
    )
