"""Emergency navigation service backed by the real OSM routing graph."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories import building_repo, lane_repo
from app.routing.building_access import trim_route_to_entrance
from app.routing.osm_graph import (
    DURATION_BASIS,
    NavigationError,
    OsmWayInput,
    RouteStep,
    build_navigation_graph,
    compute_navigation,
)
from app.services import station_service
from app.state import app_state


def _osm_tags(lane: Any) -> dict[str, Any]:
    attrs = lane.attributes or {}
    tags = attrs.get("osm_tags")
    return tags if isinstance(tags, dict) else {}


def _highway(lane: Any, tags: dict[str, Any]) -> str:
    value = tags.get("highway")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    road_class = (lane.attributes or {}).get("road_class")
    if isinstance(road_class, str) and road_class.strip():
        return road_class.strip().lower()
    return "unclassified"


def lane_inputs(lanes: list[Any]) -> list[OsmWayInput]:
    inputs: list[OsmWayInput] = []
    for lane in lanes:
        tags = _osm_tags(lane)
        attrs = lane.attributes or {}
        inputs.append(
            OsmWayInput(
                code=lane.code,
                name=lane.name,
                path=lane.path,
                width_m=lane.width_m,
                highway=_highway(lane, tags),
                tags=tags,
                blocked=bool(lane.blocked),
                vehicle_access=bool(lane.vehicle_access),
                width_verified=bool(attrs.get("width_verified", False)),
            )
        )
    return inputs


async def load_navigation_graph(session: AsyncSession):
    """Build the OSM navigation graph once per caller (WS world load, API)."""
    lanes = await lane_repo.list_lanes(session, source="osm")
    return build_navigation_graph(lane_inputs(lanes))


def _step_payload(step: RouteStep) -> dict[str, Any]:
    return {
        "maneuver": step.maneuver,
        "instruction": step.instruction,
        "road_name": step.road_name,
        "highway": step.highway,
        "mode": step.mode,
        "distance_m": round(float(step.distance_m), 1),
        "duration_s": round(float(step.duration_s), 1),
        "start": step.start,
        "end": step.end,
        "geometry": step.geometry,
    }


def _snap_payload(candidate: Any, requested_lat: float, requested_lng: float) -> dict[str, Any]:
    return {
        "lat": requested_lat,
        "lng": requested_lng,
        "snapped": {
            "lat": round(float(candidate.point[1]), 7),
            "lng": round(float(candidate.point[0]), 7),
        },
        "snap_distance_m": round(float(candidate.distance_m), 1),
        "edge_id": candidate.edge.id,
        "way_id": candidate.edge.way_code,
        "road_name": candidate.edge.name,
        "highway": candidate.edge.highway,
        "oneway": candidate.edge.oneway,
    }


def _raise_navigation_error(exc: NavigationError) -> None:
    if exc.code == "OSM_GRAPH_EMPTY":
        raise AppError(
            exc.code,
            "No OSM road network is imported. Run backend/scripts/import_osm_geojson.py first.",
            exc.status_code,
        ) from exc
    raise AppError(exc.code, exc.message, exc.status_code) from exc


async def _route_from_station(
    session: AsyncSession,
    graph: Any,
    *,
    department: str,
    destination_lat: float,
    destination_lng: float,
    weighting: str,
    ctx: dict[str, list[dict[str, Any]]],
) -> tuple[Any, dict[str, Any], int]:
    nodes = await lane_repo.list_nodes(session)
    stations = await station_service.nearest_stations(
        department,
        destination_lat,
        destination_lng,
        limit=8,
        fallback_nodes=nodes,
    )
    if not stations:
        raise AppError(
            "STATION_DATA_UNAVAILABLE",
            "No Mapbox-listed emergency station was found near the incident. "
            "Set MAPBOX_ACCESS_TOKEN on the backend or provide an origin manually.",
            422,
        )

    route_profile = station_service.DEPARTMENT_PROFILE[department]
    best: tuple[float, Any, dict[str, Any]] | None = None
    errors: list[str] = []
    considered = 0
    for station in stations[:6]:
        considered += 1
        try:
            result = compute_navigation(
                graph,
                float(station["lat"]),
                float(station["lng"]),
                destination_lat,
                destination_lng,
                route_profile,
                weighting,
                hazards=ctx["hazards"],
                floods=ctx["floods"],
                closures=ctx["closures"],
            )
        except NavigationError as exc:
            errors.append(f"{station['name']}: {exc.message}")
            continue
        score = (result.duration_s or 0.0) if weighting == "time" else result.distance_m
        if best is None or score < best[0]:
            best = (score, result, station)

    if best is None:
        detail = "; ".join(errors[:3]) if errors else "no traversable OSM route"
        raise AppError(
            "STATION_ROUTE_NOT_FOUND",
            f"Mapbox returned {len(stations)} {department} station(s) but none can reach the incident "
            f"on the imported OSM road network ({detail}).",
            404,
        )
    _score, result, station = best
    result.warnings.append(
        f"Origin station auto-selected from Mapbox-listed {department} stations "
        f"({station['name']}, {station['distance_m']:.0f} m straight-line from the incident)."
    )
    return result, station, considered


async def navigate(
    session: AsyncSession,
    *,
    destination_lat: float,
    destination_lng: float,
    destination_building_id: str | None = None,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
    profile: str = "fire_truck",
    weighting: str = "time",
    avoid_hazards: bool = True,
    department: str | None = None,
    origin_mode: str = "coordinates",
) -> dict[str, Any]:
    """Plan a route on imported OSM geometry (never the demo grid).

    The drawn line starts at the requested origin and ends at the requested
    destination; only the middle follows OSM edges. Off-road gaps are short
    connectors and are reported as snap distances instead of being routed on.
    When ``destination_building_id`` names a building, the final connector is
    trimmed at its street-facing footprint edge so the route stops at the
    building front instead of driving to its centre.
    """
    ctx = (
        app_state.routing_ctx()
        if avoid_hazards
        else {"hazards": [], "floods": [], "closures": []}
    )
    graph = await load_navigation_graph(session)
    chosen_station: dict[str, Any] | None = None
    stations_considered = 0

    if origin_mode == "nearest_station":
        if department is None:
            raise AppError("DEPARTMENT_REQUIRED", "department is required for nearest-station routing", 422)
        result, chosen_station, stations_considered = await _route_from_station(
            session,
            graph,
            department=department,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            weighting=weighting,
            ctx=ctx,
        )
        origin_lat = float(chosen_station["lat"])
        origin_lng = float(chosen_station["lng"])
    else:
        if origin_lat is None or origin_lng is None:
            raise AppError("ORIGIN_REQUIRED", "origin is required for coordinate routing", 422)
        try:
            result = compute_navigation(
                graph,
                origin_lat,
                origin_lng,
                destination_lat,
                destination_lng,
                profile,
                weighting,
                hazards=ctx["hazards"],
                floods=ctx["floods"],
                closures=ctx["closures"],
            )
        except NavigationError as exc:
            _raise_navigation_error(exc)

    if destination_building_id:
        building = await building_repo.get_by_code(session, destination_building_id)
        if building is not None and building.footprint:
            gate = trim_route_to_entrance(
                result,
                building.footprint,
                [destination_lng, destination_lat],
                building.name,
            )
            if gate is not None:
                destination_lng, destination_lat = gate

    properties = {
        "distance_m": int(round(result.distance_m)),
        "duration_s": int(round(result.duration_s)) if result.duration_s is not None else None,
        "profile": result.profile,
        "weighting": result.weighting,
        "algorithm": result.algorithm,
        "duration_basis": DURATION_BASIS,
        "geometry_source": "openstreetmap",
        "edge_count": len(result.edge_ids),
        "edge_ids": result.edge_ids,
        "warnings": result.warnings,
        "origin_snap_distance_m": round(result.origin.distance_m, 1),
        "destination_snap_distance_m": round(result.destination.distance_m, 1),
        "road_distance_m": int(round(result.road_distance_m)),
        "road_duration_s": int(round(result.road_duration_s)),
        "access_distance_m": round(result.access_distance_m, 1),
        "access_duration_s": round(result.access_duration_s, 1),
        "egress_distance_m": round(result.egress_distance_m, 1),
        "egress_duration_s": round(result.egress_duration_s, 1),
        "closures_considered": len(ctx["closures"]),
        "steps": [_step_payload(step) for step in result.steps],
    }
    assert origin_lat is not None and origin_lng is not None
    return {
        "route": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": result.geometry,
            },
            "properties": properties,
        },
        "origin": _snap_payload(result.origin, origin_lat, origin_lng),
        "destination": _snap_payload(result.destination, destination_lat, destination_lng),
        "warnings": result.warnings,
        "origin_station": chosen_station,
        "stations_considered": stations_considered,
    }
