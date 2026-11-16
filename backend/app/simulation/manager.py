import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.core.constants import (
    Scenario,
    SimulationStatus,
    HAZARD_SENSOR_KIND,
)
from app.core.config import settings
from app.core.exceptions import (
    NotFoundError,
    SimulationCapError,
    ConflictError,
    ValidationAppError,
)
from app.models import Simulation, Building, Sensor
from app.realtime.bus import bus
from app.simulation.models import get_model
from app.repositories import simulation_repo, sensor_repo, lane_repo

logger = logging.getLogger("juras.simulation")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class SimulationManager:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self.tasks: dict[str, dict[str, Any]] = {}
        self._stopping = False

    async def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        scenario = payload.get("scenario")
        if scenario not in Scenario.__members__:
            raise ValidationAppError(
                "INVALID_SCENARIO", "scenario must be one of fire, flood, structural"
            )
        severity = payload.get("severity", "warning")
        if severity not in ("normal", "warning", "critical"):
            raise ValidationAppError("INVALID_SEVERITY", "severity must be normal, warning or critical")
        interval_ms = int(payload.get("interval_ms") or settings.simulation_default_interval_ms)
        if interval_ms < settings.simulation_min_interval_ms:
            interval_ms = settings.simulation_min_interval_ms
        duration_sec = int(payload.get("duration_sec") or 60)
        if duration_sec > settings.simulation_max_duration_sec:
            duration_sec = settings.simulation_max_duration_sec
        seed = payload.get("seed")
        seed = int(seed) if seed is not None else int.from_bytes(uuid.uuid4().bytes[:4], "little") & 0x7FFFFFFF

        async with self.session_factory() as session:
            running = await simulation_repo.list_by_status(session, SimulationStatus.running.value)
            if len(running) >= settings.simulation_max_active:
                raise SimulationCapError(
                    f"Maximum {settings.simulation_max_active} active simulations allowed"
                )
            sim = Simulation(
                scenario=scenario,
                severity=severity,
                seed=seed,
                interval_ms=interval_ms,
                duration_sec=duration_sec,
                status=SimulationStatus.queued.value,
                actor=payload.get("actor", "dashboard"),
            )
            if scenario in ("fire", "structural"):
                target_id = payload.get("target_building_id")
                if not target_id:
                    raise ValidationAppError(
                        "TARGET_REQUIRED", f"{scenario} scenario requires target_building_id"
                    )
                from app.repositories import building_repo

                building = await building_repo.get_by_id(session, str(target_id))
                if building is None:
                    raise NotFoundError(
                        "BUILDING_NOT_FOUND", f"Target building {target_id} does not exist"
                    )
                duplicate = await simulation_repo.active_for_target(session, building.id, scenario)
                if duplicate is not None:
                    raise ConflictError(
                        code="SIMULATION_ALREADY_RUNNING",
                        message=f"{scenario} simulation already running for {building.code}",
                    )
                sim.target_building_id = building.id
                kind = HAZARD_SENSOR_KIND[Scenario(scenario)]
                sensor = await sensor_repo.find_for_building(session, building.id, kind.value)
                if sensor is None:
                    raise NotFoundError(
                        "SENSOR_NOT_FOUND",
                        f"No {kind.value} sensor attached to building {building.code}",
                    )
                sim.target_sensor_id = sensor.id
                config = {
                    "scenario": scenario,
                    "severity": severity,
                    "seed": seed,
                    "interval_ms": interval_ms,
                    "duration_sec": duration_sec,
                    "building_id": str(building.id),
                    "building_code": building.code,
                    "sensor_id": str(sensor.id),
                    "base_tilt_deg": building.attributes.get("tilt_deg", 0.06),
                    "base_crack_mm": building.attributes.get("crack_mm", 0.1),
                }
            else:
                node_code = payload.get("target_node_code")
                if node_code:
                    node = await lane_repo.get_node_by_code(session, str(node_code))
                    if node is None:
                        raise NotFoundError("NODE_NOT_FOUND", f"Lane node {node_code} does not exist")
                else:
                    raise ValidationAppError(
                        "TARGET_REQUIRED", "flood scenario requires target_node_code"
                    )
                kind = HAZARD_SENSOR_KIND[Scenario.flood]
                result = await session.execute(
                    select(Sensor)
                    .where(Sensor.kind == kind.value, Sensor.node_code == str(node_code))
                    .limit(1)
                )
                sensor = result.scalar_one_or_none()
                if sensor is None:
                    raise NotFoundError(
                        "SENSOR_NOT_FOUND", f"No rain_level sensor at node {node_code}"
                    )
                sim.target_node_code = str(node_code)
                sim.target_sensor_id = sensor.id
                config = {
                    "scenario": "flood",
                    "severity": severity,
                    "seed": seed,
                    "interval_ms": interval_ms,
                    "duration_sec": duration_sec,
                    "node_code": str(node_code),
                    "sensor_id": str(sensor.id),
                    "flood_factor": float(sensor.attributes.get("flood_factor", 0.8)),
                }
            await simulation_repo.insert(session, sim)
            await session.commit()

        sim_id = str(sim.id)
        config["simulation_id"] = sim_id
        handle = {
            "task": asyncio.create_task(self._run(sim_id, config)),
            "config": config,
            "started_mono": time.monotonic(),
        }
        self.tasks[sim_id] = handle
        await self._set_status(sim_id, SimulationStatus.running, started=True)
        target_code = config.get("building_code")
        if not target_code and config.get("node_code"):
            target_code = config["node_code"]
        await bus.broadcast_event(
            "simulation.started",
            {
                "simulation_id": sim_id,
                "scenario": scenario,
                "target_building_id": config.get("building_id"),
                "target_building_code": config.get("building_code"),
                "target_node_code": config.get("node_code"),
                "severity": severity,
                "status": SimulationStatus.running.value,
                "simulation": True,
            },
        )
        return await self.describe(sim_id)

    async def _run(self, sim_id: str, config: dict[str, Any]) -> None:
        model = get_model(config["scenario"])
        state = model.initial_state(config)
        interval = config["interval_ms"] / 1000.0
        start_mono = time.monotonic()
        try:
            while not model.is_finished(state, time.monotonic() - start_mono, config):
                await asyncio.sleep(interval)
                elapsed = time.monotonic() - start_mono
                values = model.next_reading(state, elapsed, config)
                await self._ingest_reading(sim_id, config, values)
            await self._set_status(sim_id, SimulationStatus.completed, ended=True)
            self.tasks.pop(sim_id, None)
            await bus.broadcast_event(
                "simulation.completed",
                {
                    "simulation_id": sim_id,
                    "scenario": config["scenario"],
                    "status": SimulationStatus.completed.value,
                    "ended_at": now_utc().isoformat(),
                },
            )
        except asyncio.CancelledError:
            await self._set_status(sim_id, SimulationStatus.stopped, ended=True)
            self.tasks.pop(sim_id, None)
            await bus.broadcast_event(
                "simulation.completed",
                {
                    "simulation_id": sim_id,
                    "scenario": config["scenario"],
                    "status": SimulationStatus.stopped.value,
                    "ended_at": now_utc().isoformat(),
                },
            )
        except Exception as exc:
            logger.exception("simulation %s failed", sim_id)
            await self._set_status(
                sim_id, SimulationStatus.failed, ended=True, error_code="SCENARIO_ERROR"
            )
            self.tasks.pop(sim_id, None)
            await bus.broadcast_event(
                "simulation.failed",
                {
                    "simulation_id": sim_id,
                    "scenario": config["scenario"],
                    "status": SimulationStatus.failed.value,
                    "error_code": "SCENARIO_ERROR",
                },
            )

    async def _ingest_reading(
        self, sim_id: str, config: dict[str, Any], values: dict[str, float]
    ) -> None:
        from app.services.reading_service import ingest
        from app.db.session import SessionFactory

        payload = {
            "sensor_id": config.get("sensor_id"),
            "building_id": config.get("building_id"),
            "simulation_id": sim_id,
            "hazard": config["scenario"],
            "values": values,
            "source": "simulation",
            "simulation": True,
        }
        async with SessionFactory() as session:
            result = await ingest(session, payload)
            await session.commit()
        for name, data in result.get("events", []):
            await bus.broadcast_event(name, data)

    async def _set_status(
        self,
        sim_id: str,
        status: SimulationStatus,
        started: bool = False,
        ended: bool = False,
        error_code: str | None = None,
    ) -> None:
        async with self.session_factory() as session:
            sim = await simulation_repo.get(session, sim_id)
            if sim is None:
                return
            sim.status = status.value
            if started and sim.started_at is None:
                sim.started_at = now_utc()
            if ended:
                sim.ended_at = now_utc()
            if error_code:
                sim.error_code = error_code
            await session.commit()

    async def stop(self, sim_id: str) -> dict[str, Any]:
        handle = self.tasks.get(sim_id)
        async with self.session_factory() as session:
            sim = await simulation_repo.get(session, sim_id)
        if sim is None:
            raise NotFoundError("SIMULATION_NOT_FOUND", f"Simulation {sim_id} does not exist")
        if sim.status not in (SimulationStatus.running.value, SimulationStatus.queued.value):
            return await self.describe(sim_id)
        if handle is not None:
            handle["task"].cancel()
            try:
                await handle["task"]
            except (asyncio.CancelledError, Exception):
                pass
        else:
            await self._set_status(sim_id, SimulationStatus.stopped, ended=True)
            await bus.broadcast_event(
                "simulation.completed",
                {
                    "simulation_id": sim_id,
                    "scenario": sim.scenario,
                    "status": SimulationStatus.stopped.value,
                    "ended_at": now_utc().isoformat(),
                },
            )
        return await self.describe(sim_id)

    async def describe(self, sim_id: str) -> dict[str, Any]:
        async with self.session_factory() as session:
            sim = await simulation_repo.get(session, sim_id)
            if sim is None:
                raise NotFoundError("SIMULATION_NOT_FOUND", f"Simulation {sim_id} does not exist")
            elapsed = 0.0
            handle = self.tasks.get(sim_id)
            if handle is not None and sim.started_at is not None:
                elapsed = time.monotonic() - handle["started_mono"]
            return {
                "id": str(sim.id),
                "scenario": sim.scenario,
                "status": sim.status,
                "severity": sim.severity,
                "seed": sim.seed,
                "interval_ms": sim.interval_ms,
                "duration_sec": sim.duration_sec,
                "target_building_id": str(sim.target_building_id) if sim.target_building_id else None,
                "target_node_code": sim.target_node_code,
                "started_at": sim.started_at.isoformat() if sim.started_at else None,
                "ended_at": sim.ended_at.isoformat() if sim.ended_at else None,
                "elapsed_sec": round(elapsed, 2),
                "actor": sim.actor,
                "error_code": sim.error_code,
            }

    async def list_sims(self, status: str | None = None) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            sims = await simulation_repo.list_by_status(session, status)
            out = []
            for sim in sims:
                handle = self.tasks.get(str(sim.id))
                elapsed = (
                    round(time.monotonic() - handle["started_mono"], 2)
                    if handle is not None
                    else 0.0
                )
                out.append(
                    {
                        "id": str(sim.id),
                        "scenario": sim.scenario,
                        "status": sim.status,
                        "severity": sim.severity,
                        "seed": sim.seed,
                        "interval_ms": sim.interval_ms,
                        "duration_sec": sim.duration_sec,
                        "target_building_id": str(sim.target_building_id)
                        if sim.target_building_id
                        else None,
                        "target_node_code": sim.target_node_code,
                        "started_at": sim.started_at.isoformat() if sim.started_at else None,
                        "ended_at": sim.ended_at.isoformat() if sim.ended_at else None,
                        "elapsed_sec": elapsed,
                        "actor": sim.actor,
                        "error_code": sim.error_code,
                    }
                )
            return out

    async def shutdown(self) -> None:
        self._stopping = True
        for sim_id, handle in list(self.tasks.items()):
            handle["task"].cancel()
        for sim_id, handle in list(self.tasks.items()):
            try:
                await handle["task"]
            except (asyncio.CancelledError, Exception):
                pass
        self.tasks.clear()
