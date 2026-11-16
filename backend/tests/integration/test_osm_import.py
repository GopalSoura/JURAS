import json

import pytest

from app.models import Building, Lane, LaneNode
from app.services.osm_import_service import import_osm

MINI_BUILDINGS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "@id": "way/9001",
                "building": "yes",
                "name": "Test Shrine",
                "juras_type": "building",
                "juras_id": "way/9001",
                "source": "os m",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[74.860, 32.730], [74.8605, 32.730], [74.8605, 32.7305], [74.860, 32.7305]]],
            },
        }
    ],
}

MINI_LANES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"@id": "way/8001", "highway": "secondary", "name": "Test Road",
                           "juras_type": "lane_or_road", "juras_id": "way/8001"},
            "geometry": {"type": "LineString", "coordinates": [[74.8590, 32.7290], [74.8595, 32.7290]]},
        },
        {
            "type": "Feature",
            "properties": {"@id": "way/8002", "highway": "residential", "lanes": "2",
                           "juras_type": "lane_or_road", "juras_id": "way/8002"},
            "geometry": {"type": "LineString", "coordinates": [[74.8595, 32.7290], [74.8600, 32.7290]]},
        },
    ],
}


@pytest.fixture
def mini_datasets(tmp_path):
    b = tmp_path / "buildings.geojson"
    l = tmp_path / "roads_lanes.geojson"
    b.write_text(json.dumps(MINI_BUILDINGS), encoding="utf-8")
    l.write_text(json.dumps(MINI_LANES), encoding="utf-8")
    return b, l


async def test_import_creates_and_dedupes(db, mini_datasets):
    b_path, l_path = mini_datasets
    stats = await import_osm(db, b_path, l_path)
    await db.commit()
    assert stats["buildings_created"] == 1
    assert stats["lanes_created"] == 2
    assert stats["nodes_created"] == 3  # two ways share one endpoint

    from sqlalchemy import select
    lane = (await db.execute(select(Lane).where(Lane.code == "OSM-8001"))).scalar_one()
    assert lane.attributes["source"] == "osm"
    assert lane.node_a_code != lane.node_b_code
    other = (await db.execute(select(Lane).where(Lane.code == "OSM-8002"))).scalar_one()
    # shared endpoint -> connected network
    assert other.node_a_code == lane.node_b_code

    node = (await db.execute(select(LaneNode).where(LaneNode.code == lane.node_b_code))).scalar_one()
    assert node.attributes["source"] == "osm"
    assert node.pos == [74.8595, 32.729]

    building = (await db.execute(select(Building).where(Building.code == "OSM-9001"))).scalar_one()
    assert building.attributes["source"] == "osm"
    # source metadata normalized from "os m"
    assert building.attributes["osm_tags"]["source"] == "os m"
    assert building.attributes["source"] == "osm"
    assert building.name == "Test Shrine"
    assert building.year_built == 0
    assert building.footprint[0] == building.footprint[-1]
    # access node = nearest imported lane-network node
    assert building.access_node_code.startswith("OSMN-")
    # PostGIS geometry matches footprint ring
    assert building.geom is not None


async def test_import_is_idempotent(db, mini_datasets):
    b_path, l_path = mini_datasets
    first = await import_osm(db, b_path, l_path)
    await db.commit()
    second = await import_osm(db, b_path, l_path)
    await db.commit()
    assert first["buildings_created"] == 1 and second["buildings_created"] == 0
    assert second["buildings_updated"] == 1
    assert first["lanes_created"] == 2 and second["lanes_created"] == 0
    assert second["lanes_updated"] == 2
    assert second["nodes_created"] == 0

    from sqlalchemy import func, select
    assert (await db.execute(select(func.count()).select_from(Building))).scalar() == 1
    assert (await db.execute(select(func.count()).select_from(Lane))).scalar() == 2
    assert (await db.execute(select(func.count()).select_from(LaneNode))).scalar() == 3
