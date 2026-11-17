"""Emergency stations listed on the live Mapbox basemap.

Mapbox GL itself is a renderer, but the Mapbox Search Box category API exposes
the same POIs (fire stations, hospitals, police stations) that the map displays.
The backend queries that API so the browser token stays in the frontend and the
result can be routed on the imported OSM graph.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.routing.graph import dist_m_sqrt

logger = logging.getLogger("juras.stations")
logging.getLogger("httpx").setLevel(logging.WARNING)

DEPARTMENT_CATEGORY = {
    "fire": "fire_station",
    "medical": "hospital",
    "police": "police",
}
DEPARTMENT_PROFILE = {
    "fire": "fire_truck",
    "medical": "responder_bike",
    "police": "responder_bike",
}
FALLBACK_NODE_KIND = {
    "fire": "fire_post",
    "medical": "medical_post",
}
MAX_STATION_DISTANCE_M = 30_000.0
MAPBOX_SEARCHBOX_URL = "https://api.mapbox.com/search/searchbox/v1/category"

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _station_from_feature(feature: dict[str, Any], department: str, origin: list[float]) -> dict[str, Any] | None:
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    lng = float(coordinates[0])
    lat = float(coordinates[1])
    if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    distance = dist_m_sqrt(origin, [lng, lat])
    if distance > MAX_STATION_DISTANCE_M:
        return None
    name = props.get("name") or props.get("name_preferred") or "Unnamed station"
    address = props.get("full_address") or props.get("place_formatted") or ""
    category = props.get("poi_category") or DEPARTMENT_CATEGORY.get(department, "")
    if isinstance(category, list):
        category = category[0] if category else ""
    return {
        "id": props.get("mapbox_id") or f"{department}:{lat:.6f},{lng:.6f}",
        "department": department,
        "name": name,
        "address": address,
        "lat": round(lat, 7),
        "lng": round(lng, 7),
        "pos": [lng, lat],
        "distance_m": round(distance, 1),
        "source": "mapbox",
        "category": str(category or ""),
    }


async def mapbox_stations(
    department: str,
    lat: float,
    lng: float,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return Mapbox-listed stations of a department near a point."""
    category = DEPARTMENT_CATEGORY.get(department)
    if category is None:
        return []
    token = settings.mapbox_access_token
    if not token:
        logger.warning("MAPBOX_ACCESS_TOKEN is not configured; nearest-station search is unavailable")
        return []

    safe_limit = max(1, min(limit, 10))
    cache_key = f"{department}:{lat:.3f}:{lng:.3f}:{safe_limit}"
    now = time.time()
    cached = _cache.get(cache_key)
    if cached is not None and now - cached[0] < settings.mapbox_station_cache_seconds:
        return [dict(item) for item in cached[1]]

    params = {
        "access_token": token,
        "proximity": f"{lng:.6f},{lat:.6f}",
        "limit": str(safe_limit),
        "language": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{MAPBOX_SEARCHBOX_URL}/{category}", params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Mapbox station search failed for %s: HTTP %s", department, exc.response.status_code
        )
        return []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Mapbox station search failed for %s: %s", department, type(exc).__name__
        )
        return []

    origin = [float(lng), float(lat)]
    stations = [
        station
        for feature in payload.get("features", [])
        if (station := _station_from_feature(feature, department, origin)) is not None
    ]
    stations.sort(key=lambda item: (item["distance_m"], item["name"]))
    stations = stations[:safe_limit]
    _cache[cache_key] = (now, stations)
    return [dict(item) for item in stations]


async def nearest_stations(
    department: str,
    lat: float,
    lng: float,
    *,
    limit: int = 8,
    fallback_nodes: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Mapbox stations first; fall back to existing demo posts when offline."""
    stations = await mapbox_stations(department, lat, lng, limit=limit)
    if stations:
        return stations

    kind = FALLBACK_NODE_KIND.get(department)
    if not kind:
        return []
    origin = [float(lng), float(lat)]
    fallback: list[dict[str, Any]] = []
    for node in fallback_nodes or []:
        if getattr(node, "kind", "") != kind:
            continue
        pos = list(node.pos)
        fallback.append(
            {
                "id": f"node:{node.code}",
                "department": department,
                "name": node.label,
                "address": "Demo staging post (Mapbox unavailable)",
                "lat": round(float(pos[1]), 7),
                "lng": round(float(pos[0]), 7),
                "pos": pos,
                "distance_m": round(dist_m_sqrt(origin, pos), 1),
                "source": "demo",
                "category": kind,
            }
        )
    fallback.sort(key=lambda item: (item["distance_m"], item["name"]))
    return fallback[:limit]
