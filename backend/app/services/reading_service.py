import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RULE_VERSION
from app.core.exceptions import NotFoundError, ValidationAppError
from app.iot.registry import (
    IOT_SENSOR_KIND_TO_HAZARD,
    device_for_sensor_code,
    get_device,
)
from app.models import Reading, RiskAssessment
from app.repositories import (
    building_repo,
    lane_repo,
    reading_repo,
    risk_repo,
    sensor_repo,
)
from app.risk.rules import evaluate
from app.schemas.reading import ReadingCreate
from app.services import incident_service

logger = logging.getLogger("juras.ingest")


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = first.get("msg", "invalid reading")
    return f"{loc}: {msg}" if loc else str(msg)


async def _resolve_sensor(
    session: AsyncSession, payload: ReadingCreate
) -> tuple[Any, Any]:
    """Resolve the sensor and the Wokwi device, if one was declared."""
    device = get_device(payload.device_id)
    if payload.device_id and device is None:
        raise NotFoundError(
            "UNKNOWN_DEVICE",
            f"Device {payload.device_id!r} is not a registered JURAS sensor node",
        )

    sensor = None
    if payload.sensor_id:
        sensor = await sensor_repo.get_by_id(session, str(payload.sensor_id))
        if sensor is None:
            raise NotFoundError(
                "SENSOR_NOT_FOUND", f"Sensor {payload.sensor_id} does not exist"
            )

    if device is not None:
        if sensor is not None and sensor.code != device.sensor_code:
            raise ValidationAppError(
                "DEVICE_SENSOR_MISMATCH",
                f"Device {device.device_id} is mapped to sensor {device.sensor_code}, "
                f"not {sensor.code}",
            )
        if sensor is None:
            sensor = await sensor_repo.get_by_code(session, device.sensor_code)
        if sensor is None:
            raise NotFoundError(
                "SENSOR_NOT_FOUND",
                f"Device {device.device_id} expects sensor {device.sensor_code}, "
                "but that sensor is not registered. Run backend/scripts/ensure_iot_sensors.py.",
            )
        if device.hazard != payload.hazard:
            raise ValidationAppError(
                "DEVICE_HAZARD_MISMATCH",
                f"Device {device.device_id} reports hazard {device.hazard!r}, "
                f"not {payload.hazard!r}",
            )

    if sensor is None:
        kind_map = {"fire": "smoke_temp", "flood": "rain_level", "structural": "structure"}
        kind = kind_map[payload.hazard]
        if payload.node_code:
            sensor = await sensor_repo.find_for_node(session, payload.node_code, kind)
            if sensor is None:
                raise NotFoundError(
                    "SENSOR_NOT_FOUND",
                    f"Lane node {payload.node_code} has no {kind} sensor",
                )
        elif payload.building_id:
            building = await building_repo.get_by_id(session, str(payload.building_id))
            if building is None:
                raise NotFoundError(
                    "BUILDING_NOT_FOUND",
                    f"Target building {payload.building_id} does not exist",
                )
            sensor = await sensor_repo.find_for_building(session, building.id, kind)
            if sensor is None:
                raise NotFoundError(
                    "SENSOR_NOT_FOUND",
                    f"Building {building.code} has no {kind} sensor",
                )
        else:
            raise ValidationAppError(
                "TARGET_REQUIRED", "sensor_id, device_id, building_id or node_code required"
            )

    return sensor, device


async def ingest(
    session: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    events_out: list[tuple[str, dict[str, Any]]] = []

    # Validation also runs at the API boundary, but ingest() is called directly
    # by the simulation manager and tests.  Keeping it here means a bad reading
    # can never slip into the database as zeros.
    try:
        reading_in = ReadingCreate.model_validate(payload)
    except ValidationError as exc:
        raise ValidationAppError("INVALID_READING", _validation_message(exc)) from exc

    hazard = reading_in.hazard
    sensor, device = await _resolve_sensor(session, reading_in)

    sensor_hazard = IOT_SENSOR_KIND_TO_HAZARD.get(sensor.kind)
    if sensor_hazard is not None and sensor_hazard != hazard:
        raise ValidationAppError(
            "HAZARD_SENSOR_MISMATCH",
            f"Sensor {sensor.code} is a {sensor.kind} sensor and cannot record "
            f"hazard {hazard!r}",
        )

    building = None
    if reading_in.building_id:
        building = await building_repo.get_by_id(session, str(reading_in.building_id))
        if building is None:
            raise NotFoundError(
                "BUILDING_NOT_FOUND",
                f"Target building {reading_in.building_id} does not exist",
            )

    if sensor.building_id:
        sensor_building = await building_repo.get_by_id(session, str(sensor.building_id))
        if sensor_building is None:
            raise NotFoundError(
                "BUILDING_NOT_FOUND",
                f"Sensor {sensor.code} points at a building that no longer exists",
            )
        if building is not None and building.id != sensor_building.id:
            raise ValidationAppError(
                "SENSOR_TARGET_MISMATCH",
                f"Sensor {sensor.code} is mapped to building {sensor_building.code}, "
                f"not {building.code}",
            )
        building = sensor_building
    elif sensor.node_code:
        if building is not None:
            raise ValidationAppError(
                "SENSOR_TARGET_MISMATCH",
                f"Sensor {sensor.code} is mapped to lane node {sensor.node_code}, "
                f"not building {building.code}",
            )

    node = None
    node_code = reading_in.node_code or sensor.node_code
    if sensor.node_code and reading_in.node_code and reading_in.node_code != sensor.node_code:
        raise ValidationAppError(
            "SENSOR_TARGET_MISMATCH",
            f"Sensor {sensor.code} is mapped to lane node {sensor.node_code}, "
            f"not {reading_in.node_code}",
        )
    if node_code:
        node = await lane_repo.get_node_by_code(session, node_code)
        if node is None:
            raise NotFoundError(
                "NODE_NOT_FOUND", f"Target lane node {node_code!r} does not exist"
            )

    if device is not None:
        if device.target_type == "building":
            if building is None or building.code != device.target_code:
                raise ValidationAppError(
                    "DEVICE_TARGET_MISMATCH",
                    f"Device {device.device_id} is mapped to building "
                    f"{device.target_code}, but this reading targets "
                    f"{building.code if building else 'no building'}",
                )
        else:
            if node is None or node.code != device.target_code:
                raise ValidationAppError(
                    "DEVICE_TARGET_MISMATCH",
                    f"Device {device.device_id} is mapped to lane node "
                    f"{device.target_code}, but this reading targets "
                    f"{node.code if node else 'no lane node'}",
                )

    if not sensor.building_id and building is not None:
        sensor.building_id = building.id
        await session.flush()

    # A sensor that is registered to a Wokwi node is simulated hardware even
    # when the caller only sent a sensor/building code (older sketches).  This
    # keeps source=field/simulation=false from ever being stored for it.
    resolved_device = device or device_for_sensor_code(sensor.code)
    device_id = resolved_device.device_id if resolved_device else None

    source = reading_in.source
    simulation = reading_in.simulation
    if resolved_device is not None:
        if source != "simulation" or not simulation:
            logger.warning(
                "Device %s tried to report source=%s simulation=%s; "
                "forcing simulation flags for a Wokwi node",
                resolved_device.device_id,
                source,
                simulation,
            )
        source = "simulation"
        simulation = True
    elif source == "simulation" and not simulation:
        simulation = True

    # A reading is "realtime" when it comes from a registered Wokwi device and
    # is not part of a simulation run.  Wokwi counts as simulated hardware, so
    # source/simulation stay at their existing values; this flag only separates
    # live sensor-driven state from the simulation engine's output.
    realtime = resolved_device is not None and reading_in.simulation_id is None

    observed_at = reading_in.observed_at or datetime.now(timezone.utc)
    reading = Reading(
        sensor_id=sensor.id,
        building_id=building.id if building else None,
        simulation_id=None,
        hazard=hazard,
        values={k: float(v) for k, v in reading_in.values.items()},
        observed_at=observed_at,
        source=source,
        simulation=simulation,
    )

    simulation_id = reading_in.simulation_id
    if simulation_id:
        from app.repositories import simulation_repo

        simulation_row = await simulation_repo.get(session, str(simulation_id))
        if simulation_row is None:
            raise NotFoundError(
                "SIMULATION_NOT_FOUND", f"Simulation {simulation_id} does not exist"
            )
        reading.simulation_id = simulation_row.id

    await reading_repo.insert(session, reading)

    target_building_id = str(building.id) if building else None
    target_building_code = building.code if building else None
    target_node_code = node.code if node else None
    target_pos = (
        building.center
        if building is not None
        else (node.pos if node is not None else sensor.pos)
    )

    events_out.append(
        (
            "reading.updated",
            {
                "reading_id": str(reading.id),
                "sensor_id": str(sensor.id),
                "sensor_code": sensor.code,
                "device_id": device_id,
                "hazard": hazard,
                "building_id": target_building_id,
                "building_code": target_building_code,
                "node_code": target_node_code,
                "pos": target_pos,
                "values": reading.values,
                "observed_at": reading.observed_at.isoformat(),
                "received_at": reading.received_at.isoformat(),
                "source": reading.source,
                "simulation": reading.simulation,
                "realtime": realtime,
                "simulation_id": str(reading.simulation_id) if reading.simulation_id else None,
            },
        )
    )

    risk_out: dict[str, Any] | None = None
    incident_id: str | None = None
    incident_code: str | None = None
    incident_created = False
    incident_status: str | None = None
    risk_target = None
    if building is not None:
        risk_target = ("building", building.id, building.code, building.center)
    elif node is not None:
        risk_target = ("node", node.id, node.code, node.pos)

    if risk_target is not None:
        entity_type, entity_id, entity_code, pos = risk_target
        assessment = evaluate(hazard, reading.values)
        ra = RiskAssessment(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            hazard=hazard,
            score=int(assessment["score"]),
            category=assessment["category"],
            reasons=assessment["reasons"],
            assessed_at=reading.observed_at,
            simulation_id=reading.simulation_id,
            rule_version=RULE_VERSION,
        )
        await risk_repo.insert(session, ra)

        incident, created = await incident_service.upsert_for_risk(
            session,
            hazard=hazard,
            category=ra.category,
            building=building,
            node_code=node.code if node is not None else None,
            pos=pos,
            simulation_id=str(reading.simulation_id) if reading.simulation_id else None,
            source=reading.source,
            realtime=realtime,
            reasons=ra.reasons,
            events_out=events_out,
        )
        if incident is not None:
            incident_id = str(incident.id)
            incident_code = incident.code
            incident_status = incident.status
            incident_created = created

        risk_out = {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "entity_code": entity_code,
            "building_id": target_building_id,
            "building_code": target_building_code,
            "node_code": target_node_code,
            "device_id": device_id,
            "sensor_code": sensor.code,
            "hazard": hazard,
            "score": ra.score,
            "category": ra.category,
            "reasons": ra.reasons,
            "assessed_at": ra.assessed_at.isoformat(),
            "rule_version": ra.rule_version,
            "source": reading.source,
            "simulation": reading.simulation,
            "realtime": realtime,
            "simulation_id": str(reading.simulation_id) if reading.simulation_id else None,
            "incident_id": incident_id,
            "incident_code": incident_code,
            "incident_status": incident_status,
        }
        events_out.append(("risk.updated", risk_out))

    result = {
        "id": str(reading.id),
        "accepted": True,
        "hazard": hazard,
        "sensor_code": sensor.code,
        "device_id": device_id,
        "building_id": target_building_id,
        "building_code": target_building_code,
        "node_code": target_node_code,
        "source": reading.source,
        "simulation": reading.simulation,
        "risk": risk_out,
        "incident_id": incident_id,
        "incident_code": incident_code,
        "incident_created": incident_created,
        "events": events_out,
    }
    return result
