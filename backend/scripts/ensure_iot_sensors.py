"""Idempotently attach the three Wokwi nodes to existing JURAS sensor rows.

Run this once after deploying the backend (and after seeding a fresh database):

    python scripts/ensure_iot_sensors.py

It only updates the sensor rows named in ``app.iot.registry``.  Re-running is
safe: sensors are looked up by code and updated in place, so startup can never
create duplicate JM-014 / JM-S07 / JM-R01 records.  Buildings and lane nodes are
never created here - if a target is missing the script fails loudly instead of
inventing an ID.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.iot.registry import IOT_DEVICES, IoTDevice
from app.models import Building, LaneNode, Sensor


def _attrs(device: IoTDevice) -> dict:
    return {
        "device_id": device.device_id,
        "wokwi": True,
        "simulation": True,
        "source": "simulation",
        "sensor_code": device.sensor_code,
        "label_data": "Wokwi ESP32 simulation node, not a field sensor",
    }


async def _target(session, device: IoTDevice):
    if device.target_type == "building":
        building = (
            await session.execute(select(Building).where(Building.code == device.target_code))
        ).scalar_one_or_none()
        if building is None:
            raise SystemExit(
                f"{device.device_id}: target building {device.target_code!r} does not exist. "
                "Seed or import the building before running this script."
            )
        return building, None, list(building.center)
    node = (
        await session.execute(select(LaneNode).where(LaneNode.code == device.target_code))
    ).scalar_one_or_none()
    if node is None:
        raise SystemExit(
            f"{device.device_id}: target lane node {device.target_code!r} does not exist. "
            "Seed or import the lane network before running this script."
        )
    return None, node, list(node.pos)


async def ensure_sensors() -> int:
    changed = 0
    async with SessionFactory() as session:
        for device in IOT_DEVICES.values():
            building, node, pos = await _target(session, device)
            sensor = (
                await session.execute(select(Sensor).where(Sensor.code == device.sensor_code))
            ).scalar_one_or_none()

            if sensor is None:
                lon, lat = float(pos[0]), float(pos[1])
                sensor = Sensor(
                    code=device.sensor_code,
                    label=f"Wokwi {device.hazard} node, {device.target_code}",
                    kind=device.sensor_kind,
                    building_id=building.id if building else None,
                    node_code=node.code if node else None,
                    status="active",
                    source="simulation",
                    pos=pos,
                    attributes=_attrs(device),
                    geom=func.ST_GeomFromText(f"POINT({lon:.8f} {lat:.8f})", 4326),
                )
                session.add(sensor)
                await session.flush()
                print(f"created sensor {sensor.code} -> {device.target_type} {device.target_code}")
                changed += 1
                continue

            if sensor.kind != device.sensor_kind:
                raise SystemExit(
                    f"{device.device_id}: sensor {sensor.code} has kind {sensor.kind!r}, "
                    f"registry expects {device.sensor_kind!r}. Refusing to change it automatically."
                )

            before = (
                sensor.building_id,
                sensor.node_code,
                sensor.status,
                sensor.source,
                dict(sensor.attributes or {}),
            )
            sensor.building_id = building.id if building else None
            sensor.node_code = node.code if node else None
            sensor.status = "active"
            sensor.source = "simulation"
            sensor.attributes = {**(sensor.attributes or {}), **_attrs(device)}
            after = (
                sensor.building_id,
                sensor.node_code,
                sensor.status,
                sensor.source,
                dict(sensor.attributes or {}),
            )
            if before != after:
                print(
                    f"updated sensor {sensor.code} -> "
                    f"{device.target_type} {device.target_code} ({device.device_id})"
                )
                changed += 1
            else:
                print(f"ok sensor {sensor.code} already mapped to {device.target_code}")

        await session.commit()
    return changed


if __name__ == "__main__":
    n = asyncio.run(ensure_sensors())
    print(f"ensure_iot_sensors: {n} row(s) changed")
