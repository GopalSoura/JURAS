from app.services.osm_import_service import (
    building_name,
    building_type,
    clean_linestring,
    clean_ring,
    iter_building_records,
    normalize_source,
    original_osm_tags,
    ring_centroid,
    way_name,
    way_numeric_id,
    way_width,
)


def test_normalize_source_osm_variants():
    assert normalize_source("os m") == "osm"
    assert normalize_source("OS m") == "osm"
    assert normalize_source(" OSM ") == "osm"
    assert normalize_source("OpenStreetMap") == "osm"
    assert normalize_source("open street map") == "osm"


def test_normalize_source_preserves_other_provenance():
    assert normalize_source("maxar") == "maxar"
    assert normalize_source("Bing") == "bing"
    assert normalize_source("") is None
    assert normalize_source(None) is None


def test_clean_ring_closes_and_dedupes():
    ring = [[0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    out = clean_ring(ring)
    assert out[0] == out[-1]
    assert len(out) == 5
    assert [1.0, 0.0] in out


def test_clean_ring_rejects_degenerate():
    assert clean_ring([[0, 0], [1, 0], [1, 0]]) is None
    assert clean_ring([[0, 0]]) is None


def test_clean_linestring_dedupes():
    assert clean_linestring([[0, 0], [0, 0], [1, 1], [1, 1]]) == [[0.0, 0.0], [1.0, 1.0]]
    assert clean_linestring([[0, 0]]) is None


def test_ring_centroid_square():
    ring = clean_ring([[0, 0], [2, 0], [2, 2], [0, 2]])
    c = ring_centroid(ring)
    assert abs(c[0] - 1.0) < 1e-9
    assert abs(c[1] - 1.0) < 1e-9


def test_way_width_class_defaults_and_lanes_tag():
    w, src = way_width({"highway": "primary"})
    assert w == 10.0 and src == "highway_class_default"
    w, src = way_width({"highway": "residential", "lanes": "2"})
    assert w == 6.0 and src == "osm_lanes_tag_x3m"
    w, src = way_width({})
    assert w == 3.0 and src == "highway_class_default"
    w, _ = way_width({"highway": "footway"})
    assert w == 1.5


def test_way_numeric_id_and_names():
    props = {"@id": "way/123", "juras_id": "way/123", "display_name": "way/123"}
    assert way_numeric_id(props) == "123"
    assert building_name({"name": "Bahu Fort"}, "123") == "Bahu Fort"
    assert building_name({}, "123") == "OSM way 123"
    assert way_name({}, "9", "residential") == "OSM residential way 9"
    assert building_type({"building": "yes", "office": "government"}) == "government"
    assert building_type({"building": "yes"}) == "unspecified"


def test_original_osm_tags_strips_helper_keys_only():
    tags = original_osm_tags(
        {"@id": "way/1", "building": "yes", "juras_type": "building", "juras_id": "way/1",
         "display_name": "way/1", "source": "os m"}
    )
    assert tags == {"@id": "way/1", "building": "yes", "source": "os m"}


def test_iter_building_records_normalizes_and_preserves():
    fc = {
        "features": [
            {
                "type": "Feature",
                "properties": {"@id": "way/77", "building": "yes", "juras_id": "way/77",
                               "juras_type": "building", "building:levels": "3"},
                "geometry": {"type": "Polygon",
                             "coordinates": [[[74.86, 32.73], [74.861, 32.73], [74.861, 32.731], [74.86, 32.731]]]},
            },
            {"type": "Feature", "properties": {"@id": "way/78"},
             "geometry": {"type": "Point", "coordinates": [74.86, 32.73]}},
            {"type": "Feature", "properties": {"@id": "way/79", "building": "yes"},
             "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 1]]]}},
        ]
    }
    recs = list(iter_building_records(fc["features"]))
    assert len(recs) == 1
    r = recs[0]
    assert r["code"] == "OSM-77"
    assert r["attributes"]["source"] == "osm"
    assert r["attributes"]["osm_id"] == "way/77"
    assert r["attributes"]["osm_tags"] == {"@id": "way/77", "building": "yes", "building:levels": "3"}
    assert r["floors"] == 3
    assert r["year_built"] == 0
    assert "address" not in r["attributes"]
    assert "addr" not in r["attributes"]["osm_tags"]
    assert r["footprint"][0] == r["footprint"][-1]
