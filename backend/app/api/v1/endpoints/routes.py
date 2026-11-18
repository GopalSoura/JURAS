from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.db.session import get_session
from app.repositories import lane_repo
from app.schemas.route import ClosureCreate, NavigateRequest, NavigateResponse, RouteRequest
from app.services import navigation_service, routing_service, station_service
from app.state import app_state

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/closures")
async def list_closures() -> dict:
    closures = app_state.closures_snapshot()
    return {"count": len(closures), "closures": closures}


@router.post("/closures", status_code=201)
async def create_closure(payload: ClosureCreate) -> dict:
    return app_state.add_closure(
        lat=payload.lat,
        lng=payload.lng,
        radius_m=payload.radius_m,
        reason=payload.reason,
        source=payload.source,
    )


@router.delete("/closures/{closure_id}")
async def delete_closure(closure_id: str) -> dict:
    if not app_state.remove_closure(closure_id):
        raise AppError("CLOSURE_NOT_FOUND", f"Unknown road closure {closure_id!r}", 404)
    return {"removed": closure_id}


@router.delete("/closures")
async def clear_closures() -> dict:
    app_state.clear_closures()
    return {"removed": "all"}


@router.get("/stations")
async def list_stations(
    department: Literal["fire", "medical", "police"],
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    limit: int = Query(default=8, ge=1, le=10),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mapbox-listed emergency stations near a point, nearest first.

    The result is the same POI layer the Mapbox basemap displays. If Mapbox is
    unavailable, existing demo fire/medical posts are returned as a fallback.
    """
    nodes = await lane_repo.list_nodes(session)
    stations = await station_service.nearest_stations(
        department, lat, lng, limit=limit, fallback_nodes=nodes
    )
    return {
        "department": department,
        "count": len(stations),
        "source": stations[0]["source"] if stations else None,
        "stations": stations,
    }


@router.post("/navigate", response_model=NavigateResponse)
async def navigate(payload: NavigateRequest, session: AsyncSession = Depends(get_session)) -> dict:
    """Plan an emergency route on the imported OSM road network.

    The LineString starts at the requested origin (for nearest-station mode,
    the station itself) and ends at the incident, with short connectors to the
    mapped OSM roads in between. The synthetic demo lane grid is never used.
    """
    return await navigation_service.navigate(
        session,
        origin_lat=payload.origin.lat if payload.origin else None,
        origin_lng=payload.origin.lng if payload.origin else None,
        destination_lat=payload.destination.lat,
        destination_lng=payload.destination.lng,
        destination_building_id=payload.destination_building_id,
        profile=payload.profile,
        weighting=payload.weighting,
        avoid_hazards=payload.avoid_hazards,
        department=payload.department,
        origin_mode=payload.origin_mode,
    )


@router.post("")
async def compute_route(payload: RouteRequest, session: AsyncSession = Depends(get_session)) -> dict:
    return await routing_service.plan_route(
        session,
        origin=payload.origin.model_dump() if payload.origin else None,
        destination_building_id=payload.destination_building_id,
        destination_node_code=payload.destination_node_code,
        responder_type=payload.responder_type,
    )
