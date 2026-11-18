from app.iot.registry import (
    IOT_DEVICES,
    device_for_sensor_code,
    device_id_for_sensor_code,
    get_device,
)


def test_three_wokwi_devices_registered():
    assert set(IOT_DEVICES) == {"JURAS-FIRE-001", "JURAS-STRUCT-001", "JURAS-STORM-001"}


def test_verified_sensor_and_target_mappings():
    fire = IOT_DEVICES["JURAS-FIRE-001"]
    assert (fire.sensor_code, fire.hazard, fire.target_type, fire.target_code) == (
        "JM-014",
        "fire",
        "building",
        "B-014",
    )
    struct = IOT_DEVICES["JURAS-STRUCT-001"]
    assert (struct.sensor_code, struct.hazard, struct.target_type, struct.target_code) == (
        "JM-S07",
        "structural",
        "building",
        "B-007",
    )
    storm = IOT_DEVICES["JURAS-STORM-001"]
    assert (storm.sensor_code, storm.hazard, storm.target_type, storm.target_code) == (
        "JM-R01",
        "flood",
        "node",
        "I",
    )


def test_lookup_is_case_insensitive_and_whitespace_tolerant():
    assert get_device(" juras-fire-001 ") is IOT_DEVICES["JURAS-FIRE-001"]
    assert get_device("JURAS-UNKNOWN") is None
    assert get_device(None) is None


def test_reverse_sensor_lookup():
    assert device_for_sensor_code("JM-S07").device_id == "JURAS-STRUCT-001"
    assert device_id_for_sensor_code("JM-R01") == "JURAS-STORM-001"
    assert device_for_sensor_code("JM-UNKNOWN") is None
