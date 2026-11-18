"""Verified mappings for the three Wokwi ESP32 nodes.

The sensor codes and targets below are the records that already exist in the
seeded JURAS database (see ``backend/scripts/seed_demo_data.py`` and
``backend/scripts/ensure_iot_sensors.py``).  Keeping the mapping in one place
lets the ingestion service validate a device without inventing new buildings or
lanes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TargetType = Literal["building", "node"]


@dataclass(frozen=True)
class IoTDevice:
    device_id: str
    sensor_code: str
    sensor_kind: str
    hazard: str
    target_type: TargetType
    target_code: str


IOT_DEVICES: dict[str, IoTDevice] = {
    "JURAS-FIRE-001": IoTDevice(
        device_id="JURAS-FIRE-001",
        sensor_code="JM-014",
        sensor_kind="smoke_temp",
        hazard="fire",
        target_type="building",
        target_code="B-014",
    ),
    "JURAS-STRUCT-001": IoTDevice(
        device_id="JURAS-STRUCT-001",
        sensor_code="JM-S07",
        sensor_kind="structure",
        hazard="structural",
        target_type="building",
        target_code="B-007",
    ),
    "JURAS-STORM-001": IoTDevice(
        device_id="JURAS-STORM-001",
        sensor_code="JM-R01",
        sensor_kind="rain_level",
        hazard="flood",
        target_type="node",
        target_code="I",
    ),
}

IOT_DEVICE_BY_SENSOR: dict[str, IoTDevice] = {
    device.sensor_code: device for device in IOT_DEVICES.values()
}

IOT_SENSOR_KIND_TO_HAZARD = {
    "smoke_temp": "fire",
    "structure": "structural",
    "rain_level": "flood",
}


def get_device(device_id: str | None) -> IoTDevice | None:
    if not device_id:
        return None
    return IOT_DEVICES.get(device_id.strip().upper())


def device_for_sensor_code(sensor_code: str | None) -> IoTDevice | None:
    if not sensor_code:
        return None
    return IOT_DEVICE_BY_SENSOR.get(sensor_code)


def device_id_for_sensor_code(sensor_code: str) -> str | None:
    device = device_for_sensor_code(sensor_code)
    return device.device_id if device else None
