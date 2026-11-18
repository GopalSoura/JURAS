import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RULE_VERSION
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models import Reading, RiskAssessment, Simulation
from app.repositories import building_repo, lane_repo, sensor_repo, reading_repo, risk_repo, simulation_repo
from app.risk.rules import evaluate
from app.services import incident_service


async def ingest(
    session: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    events_out: list[tuple[str, dict[str, Any]]] = []
    sensor = None
    building = None
    simulation = None

    sensor_id = payload.get("sensor_id")
    building_id = payload.get("building_id")
    if sensor_id:
        sensor = await sensor_repo.get_by_id(session, str(sensor_id))
        if sensor is None:
            raise NotFoundError("SENSOR_NOT_FOUND", f"Sensor {sensor_id} does not exist")
        if not building_id and sensor.building_id:
            building_id = str(sensor.building_id)

    if building_id:
        building = await building_repo.get_by_id(session, str(building_id))
        if building is None:
            raise NotFoundError(
                "BUILDING_NOT_FOUND", f"Target building {building_id} does not exist"
            )

    sim_id = payload.get("simulation_id")
    if sim_id:
        simulation = await simulation_repo.get(session, str(sim_id))
        if simulation is None:
            raise NotFoundError("SIMULATION_NOT_FOUND", f"Simulation {sim_id} does not exist")

    hazard = payload.get("hazard") or (simulation.scenario if simulation else "fire")
    if not sensor:
        kind_map = {"fire": "smoke_temp", "flood": "rain_level", "structural": "structure"}
        if building:
            sensor = await sensor_repo.find_for_building(session, building.id, kind_map[hazard])
            if sensor is None:
                raise NotFoundError(
                    "SENSOR_NOT_FOUND",
                    f"Building {building.code} has no {kind_map[hazard]} sensor",
                )
        else:
            raise ValidationAppError("TARGET_REQUIRED", "sensor_id or building_id required")

    if not sensor.building_id and building:
        sensor.building_id = building.id
        await session.flush()

    values = payload.get("values") or {}
    observed_at = payload.get("observed_at") or datetime.now(timezone.utc)
    if isinstance(observed_at, str):
        observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    reading = Reading(
        sensor_id=sensor.id,
        building_id=building.id if building else None,
        simulation_id=simulation.id if simulation else None,
        hazard=hazard,
        values={k: float(v) for k, v in values.items()},
        observed_at=observed_at,
        source=payload.get("source", "simulation"),
        simulation=bool(payload.get("simulation", True)),
    )
    await reading_repo.insert(session, reading)
    events_out.append(
        (
            "reading.updated",
            {
                "reading_id": str(reading.id),
                "building_id": str(building.id) if building else None,
                "building_code": building.code if building else None,
                "sensor_code": sensor.code,
                "type": hazard,
                "values": reading.values,
                "observed_at": reading.observed_at.isoformat(),
                "simulation": reading.simulation,
                "simulation_id": str(simulation.id) if simulation else None,
            },
        )
    )

    risk_out: dict[str, Any] | None = None
    incident_id: str | None = None
    incident_created = False
    risk_target = None
    if building and building.id:
        risk_target = ("building", building.id, building.code, building.center)
    elif sensor.node_code and hazard == "flood":
        node = await lane_repo.get_node_by_code(session, sensor.node_code)
        if node is not None:
            risk_target = ("node", node.id, node.code, sensor.pos)
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
            simulation_id=simulation.id if simulation else None,
            rule_version=RULE_VERSION,
        )
        await risk_repo.insert(session, ra)
        risk_out = {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "entity_code": entity_code,
            "building_id": str(building.id) if building else None,
            "building_code": building.code if building else None,
            "hazard": hazard,
            "score": ra.score,
            "category": ra.category,
            "reasons": ra.reasons,
            "assessed_at": ra.assessed_at.isoformat(),
            "rule_version": ra.rule_version,
            "simulation": True,
            "simulation_id": str(simulation.id) if simulation else None,
        }
        events_out.append(("risk.updated", risk_out))
        incident, created = await incident_service.upsert_for_risk(
            session,
            hazard=hazard,
            category=ra.category,
            building=building if entity_type == "building" else None,
            node_code=entity_code if entity_type == "node" else None,
            pos=pos,
            simulation_id=str(simulation.id) if simulation else None,
            source=reading.source,
            reasons=ra.reasons,
            events_out=events_out,
        )
        if incident:
            incident_id = str(incident.id)
            incident_created = created

    result = {
        "id": str(reading.id),
        "accepted": True,
        "risk": risk_out,
        "incident_id": incident_id,
        "incident_created": incident_created,
        "events": events_out,
    }
    return result
