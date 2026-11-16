"""Emergency navigation service backed by the real OSM routing graph."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories import lane_repo
from app.routing.osm_graph import (
    DURATION_BASIS,
    NavigationError,
    OsmWayInput,
    build_navigation_graph,
    compute_navigation,
)


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


async def navigate(
    session: AsyncSession,
    *,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    profile: str,
    weighting: str = "time",
) -> dict[str, Any]:
    """Plan a route on imported OSM geometry only (never the demo grid)."""
    lanes = await lane_repo.list_lanes(session, source="osm")
    graph = build_navigation_graph(lane_inputs(lanes))
    try:
        result = compute_navigation(
            graph,
            origin_lat,
            origin_lng,
            destination_lat,
            destination_lng,
            profile,
            weighting,
        )
    except NavigationError as exc:
        if exc.code == "OSM_GRAPH_EMPTY":
            raise AppError(
                exc.code,
                "No OSM road network is imported. Run backend/scripts/import_osm_geojson.py first.",
                exc.status_code,
            ) from exc
        raise AppError(exc.code, exc.message, exc.status_code) from exc

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
    }
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
    }
