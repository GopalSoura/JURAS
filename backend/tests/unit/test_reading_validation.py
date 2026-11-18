import math

import pytest
from pydantic import ValidationError

from app.schemas.reading import ReadingCreate

FIRE = {
    "sensor_id": "JM-014",
    "device_id": "JURAS-FIRE-001",
    "hazard": "fire",
    "values": {"smoke_level": 12.5, "smoke_ppm": 125, "temperature_c": 34.2},
    "source": "simulation",
    "simulation": True,
}

STRUCT = {
    "sensor_id": "JM-S07",
    "device_id": "JURAS-STRUCT-001",
    "hazard": "structural",
    "values": {"tilt_deg": 0.12, "crack_mm": 0.3, "vib_rms": 0.02, "deviation_mm": 4.1},
}

STORM = {
    "sensor_id": "JM-R01",
    "device_id": "JURAS-STORM-001",
    "hazard": "flood",
    "values": {"water_level_cm": 8.0, "rain_mmh": 2.5},
}


@pytest.mark.parametrize("payload", [FIRE, STRUCT, STORM])
def test_accepts_all_three_node_payloads(payload):
    parsed = ReadingCreate.model_validate(payload)
    assert parsed.hazard == payload["hazard"]
    assert parsed.values


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_values(value):
    payload = {**FIRE, "values": {"temperature_c": value, "smoke_level": 1}}
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate(payload)


def test_rejects_out_of_range_value():
    payload = {**FIRE, "values": {"temperature_c": 500, "smoke_level": 1}}
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate(payload)


def test_rejects_non_numeric_value():
    payload = {**FIRE, "values": {"temperature_c": "hot", "smoke_level": 1}}
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate(payload)


def test_rejects_empty_values():
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate({**FIRE, "values": {}})


def test_rejects_wrong_hazard_metrics():
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate({**FIRE, "values": {"water_level_cm": 12}})


def test_rejects_negative_water_level():
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate({**STORM, "values": {"water_level_cm": -1, "rain_mmh": 0}})


def test_rejects_unknown_hazard():
    with pytest.raises(ValidationError):
        ReadingCreate.model_validate({**FIRE, "hazard": "earthquake"})


def test_naive_timestamp_becomes_utc():
    parsed = ReadingCreate.model_validate({**STORM, "observed_at": "2026-11-18T10:00:00"})
    assert parsed.observed_at is not None
    assert parsed.observed_at.tzinfo is not None


def test_flood_accepts_level_alias():
    parsed = ReadingCreate.model_validate({**STORM, "values": {"level_cm": 4.5, "rain_mmh": 0}})
    assert math.isclose(parsed.values["level_cm"], 4.5)
