from fastapi import APIRouter

from app.api.v1.endpoints import (
    buildings,
    health,
    incidents,
    lanes,
    readings,
    risks,
    routes,
    sensors,
    simulations,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(buildings.router)
api_router.include_router(lanes.router)
api_router.include_router(sensors.router)
api_router.include_router(readings.router)
api_router.include_router(simulations.router)
api_router.include_router(risks.router)
api_router.include_router(incidents.router)
api_router.include_router(routes.router)
