from fastapi import APIRouter, Depends, Query

from app.api.deps import get_manager
from app.schemas.simulation import SimulationCreate, SimulationOut

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", status_code=201)
async def create_simulation(payload: SimulationCreate, manager=Depends(get_manager)) -> dict:
    return await manager.start(
        {
            "scenario": payload.scenario,
            "target_building_id": payload.target_building_id,
            "target_node_code": payload.target_node_code,
            "severity": payload.severity,
            "duration_sec": payload.duration_sec,
            "interval_ms": payload.interval_ms,
            "seed": payload.seed,
            "actor": payload.actor,
        }
    )


@router.get("")
async def list_simulations(
    status: str | None = Query(default=None), manager=Depends(get_manager)
) -> list[dict]:
    return await manager.list_sims(status)


@router.get("/{simulation_id}")
async def get_simulation(simulation_id: str, manager=Depends(get_manager)) -> dict:
    return await manager.describe(simulation_id)


@router.post("/{simulation_id}/stop")
async def stop_simulation(simulation_id: str, manager=Depends(get_manager)) -> dict:
    return await manager.stop(simulation_id)
