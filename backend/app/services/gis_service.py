from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import building_repo, lane_repo, incident_repo, risk_repo


LABEL_ALL = "mixed: illustrative demo data + OpenStreetMap import (not field-verified)"
LABEL_DEMO = "illustrative demo data"
LABEL_OSM = "OpenStreetMap import, geometry not field-verified"


def _collection_label(source: str | None) -> str:
    if source == "osm":
        return LABEL_OSM
    if source == "demo":
        return LABEL_DEMO
    return LABEL_ALL


async def buildings_geojson(
    session: AsyncSession, bbox: str | None = None, limit: int = 200, source: str | None = None
) -> dict[str, Any]:
    buildings = await building_repo.list_buildings(session, bbox=bbox, limit=limit, source=source)
    risk_map = await risk_repo.latest_map(session)
    features = []
    for b in buildings:
        ra = risk_map.get(b.id)
        features.append(
            building_repo.building_feature(
                b,
                {"score": ra.score, "category": ra.category, "hazard": ra.hazard} if ra else None,
            )
        )
    return {"type": "FeatureCollection", "features": features, "label": _collection_label(source)}


async def lanes_geojson(
    session: AsyncSession,
    blocked: bool | None = None,
    accessible_to: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    lanes = await lane_repo.list_lanes(session, blocked=blocked, accessible_to=accessible_to, source=source)
    return {
        "type": "FeatureCollection",
        "features": [lane_repo.lane_feature(l) for l in lanes],
        "label": _collection_label(source),
    }


async def nodes_geojson(session: AsyncSession, source: str | None = None) -> dict[str, Any]:
    nodes = await lane_repo.list_nodes(session)
    if source:
        nodes = [n for n in nodes if (n.attributes or {}).get("source", "demo") == source]
    return {
        "type": "FeatureCollection",
        "features": [lane_repo.node_feature(n) for n in nodes],
        "label": _collection_label(source),
    }


async def incidents_geojson(
    session: AsyncSession, status: str | None = None, hazard: str | None = None, severity: str | None = None
) -> dict[str, Any]:
    incidents = await incident_repo.list_incidents(session, status=status, hazard=hazard, severity=severity)
    return {
        "type": "FeatureCollection",
        "features": [incident_repo.incident_feature(i) for i in incidents],
    }
