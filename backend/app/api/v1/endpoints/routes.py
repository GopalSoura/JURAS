from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.route import NavigateRequest, NavigateResponse, RouteRequest
from app.services import navigation_service, routing_service

router = APIRouter(prefix="/routes", tags=["routes"])


@router.post("/navigate", response_model=NavigateResponse)
async def navigate(payload: NavigateRequest, session: AsyncSession = Depends(get_session)) -> dict:
    """Plan an emergency route on the imported OSM road network.

    The response geometry is a real LineString following OSM road vertices.
    The synthetic demo lane grid is never used here.
    """
    return await navigation_service.navigate(
        session,
        origin_lat=payload.origin.lat,
        origin_lng=payload.origin.lng,
        destination_lat=payload.destination.lat,
        destination_lng=payload.destination.lng,
        profile=payload.profile,
        weighting=payload.weighting,
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
