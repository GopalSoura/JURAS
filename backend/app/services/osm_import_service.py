"""OSM GeoJSON import pipeline for JURAS.

Imports cleaned OpenStreetMap building polygons and road line geometries
(backend/buildings.geojson, backend/roads_lanes.geojson) into the existing
PostGIS buildings/lanes/lane_nodes tables without touching synthetic demo rows.

Data rules (hard):
- Demo rows keep their codes ("B-021", "A-B", "A" ...). OSM rows use
  "OSM-<way id>" and lane nodes "OSMN-<n>", so the two sources never collide.
- attributes["source"] = "osm" on every imported row (normalized from any
  "os m" style variant). Original OSM tags are preserved verbatim under
  attributes["osm_tags"].
- Addresses are never fabricated: the dataset contains no addr:* tags, so no
  address data is written anywhere.
- Lane widths are never claimed as verified: widths use conservative
  highway-class defaults (or the OSM `lanes` count x 3.0 m when tagged) and are
  flagged attributes["width_verified"] = False with the basis recorded.
- Idempotent: re-running refreshes OSM rows in place; demo rows and sensors,
  incidents, readings, simulations are never modified or deleted.
"""

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Building, Lane, LaneNode
from app.routing.graph import dist_m_sqrt

logger = logging.getLogger("juras.osm_import")

OSM_SOURCE = "osm"
OSM_BUILDING_PREFIX = "OSM-"
OSM_NODE_PREFIX = "OSMN-"

# Conservative clear-carriageway defaults per OSM highway class (metres).
# These are engineering assumptions, NOT surveyed widths:
# every imported lane carries width_verified=False and width_source.
HIGHWAY_CLASS_WIDTHS = {
    "trunk": 12.0,
    "primary": 10.0,
    "secondary": 8.0,
    "secondary_link": 5.0,
    "tertiary": 6.5,
    "residential": 5.5,
    "unclassified": 5.0,
    "service": 4.0,
    "footway": 1.5,
}
DEFAULT_WAY_WIDTH = 3.0
LANE_TAG_WIDTH = 3.0  # metres per tagged lane (assumption, flagged unverified)

# OSM helper keys produced by the cleaning step; not part of the original tags.
_JURAS_HELPER_KEYS = {"juras_type", "juras_id", "display_name", "road_class"}
_NEUTRAL_BUILDING_TAG_VALUES = {"yes", "no", None, ""}

LABEL_OSM = "OpenStreetMap import, geometry not field-verified"


def normalize_source(value: Any) -> str | None:
    """Normalize a provenance string. "os m"/"OSM"/"osm " all become "osm".

    Other non-empty values (e.g. imagery provenance "maxar", "bing") are
    returned lowercased and trimmed, never rewritten to "osm".
    """
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    collapsed = " ".join(v.split())
    if collapsed in ("os m", "osm", "open street map", "openstreetmap"):
        return OSM_SOURCE
    return collapsed


def original_osm_tags(props: dict[str, Any]) -> dict[str, Any]:
    """Copy raw OSM properties verbatim, minus the importer's helper keys."""
    return {k: v for k, v in props.items() if k not in _JURAS_HELPER_KEYS}


def clean_ring(ring: list[list[float]]) -> list[list[float]] | None:
    """Dedupe consecutive points and force closure. None if not a valid ring.

    A valid ring needs at least 3 unique vertices plus the closing repeat.
    """
    pts = [[float(x), float(y)] for x, y in ring]
    dedup: list[list[float]] = []
    for p in pts:
        if not dedup or p[0] != dedup[-1][0] or p[1] != dedup[-1][1]:
            dedup.append(p)
    if len(dedup) < 4:
        return None
    if dedup[0] != dedup[-1]:
        dedup.append(list(dedup[0]))
    return dedup


def clean_linestring(points: list[list[float]]) -> list[list[float]] | None:
    """Dedupe consecutive points. None if fewer than 2 remain."""
    pts = [[float(x), float(y)] for x, y in points]
    dedup: list[list[float]] = []
    for p in pts:
        if not dedup or p[0] != dedup[-1][0] or p[1] != dedup[-1][1]:
            dedup.append(p)
    return dedup if len(dedup) >= 2 else None


def ring_centroid(ring: list[list[float]]) -> list[float]:
    """Area-weighted centroid (shoelace) in lon/lat using the shared local metric."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    if not pts:
        return [0.0, 0.0]
    area = 0.0
    cx = 0.0
    cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-12:
        return [sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n]
    area *= 0.5
    return [cx / (6.0 * area), cy / (6.0 * area)]


def linestring_length_m(path: list[list[float]]) -> float:
    return sum(dist_m_sqrt(path[i], path[i + 1]) for i in range(len(path) - 1))


def way_numeric_id(props: dict[str, Any]) -> str | None:
    for key in ("juras_id", "@id"):
        raw = props.get(key)
        if isinstance(raw, str) and raw.startswith("way/"):
            return raw.split("/", 1)[1]
    return None


def building_name(props: dict[str, Any], way_id: str) -> str:
    for key in ("name", "display_name"):
        v = props.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:255]
    return f"OSM way {way_id}"


def building_type(props: dict[str, Any]) -> str:
    for key in ("building", "office", "amenity", "historic"):
        v = props.get(key)
        if isinstance(v, str) and v.strip() and v.strip().lower() not in _NEUTRAL_BUILDING_TAG_VALUES:
            return v.strip().lower()[:64]
    return "unspecified"


def way_name(props: dict[str, Any], way_id: str, highway: Any) -> str:
    for key in ("name", "display_name"):
        v = props.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:255]
    label = highway if isinstance(highway, str) and highway.strip() else "road"
    return f"OSM {label} way {way_id}"


def way_width(props: dict[str, Any]) -> tuple[float, str]:
    """Return (width_m, width_source). Never verified; callers flag that."""
    lanes = props.get("lanes")
    if isinstance(lanes, (int, float)) or (isinstance(lanes, str) and lanes.strip().isdigit()):
        n = int(lanes)  # type: ignore[arg-type]
        if 1 <= n <= 12:
            return round(n * LANE_TAG_WIDTH, 2), "osm_lanes_tag_x3m"
    highway = props.get("highway")
    return HIGHWAY_CLASS_WIDTHS.get(highway, DEFAULT_WAY_WIDTH), "highway_class_default"


def iter_building_records(features: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield normalized building records; skip features with unusable rings."""
    for f in features:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        way_id = way_numeric_id(props)
        if geom.get("type") != "Polygon" or way_id is None:
            logger.warning("skip building feature without polygon geometry/way id: %s", props.get("@id"))
            continue
        ring = clean_ring((geom.get("coordinates") or [[None]])[0])
        if ring is None:
            logger.warning("skip degenerate building ring %s", way_id)
            continue
        levels_raw = props.get("building:levels")
        levels = None
        if isinstance(levels_raw, (int, float)):
            levels = int(levels_raw)
        elif isinstance(levels_raw, str) and levels_raw.strip().isdigit():
            levels = int(levels_raw.strip())
        center = ring_centroid(ring)
        height = round(levels * 3.3, 2) if levels else 3.3
        yield {
            "code": f"{OSM_BUILDING_PREFIX}{way_id}",
            "name": building_name(props, way_id),
            "floors": levels if levels else 1,
            "building_type": building_type(props),
            "construction": "",
            "occupancy": 0,
            "year_built": 0,
            "height_m": height,
            "priority": 0,
            "status": "ok",
            "center": center,
            "footprint": ring,
            "attributes": {
                "source": OSM_SOURCE,
                "osm_id": f"way/{way_id}",
                "osm_type": "way",
                "osm_tags": original_osm_tags(props),
                "label_data": LABEL_OSM,
                "demo": False,
                "verified": False,
                "height_basis": "osm_building_levels_x3m" if levels else "default_single_storey_assumption",
                "has_interior_rings": len((geom.get("coordinates") or [])) > 1,
            },
        }


def iter_lane_records(features: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield normalized lane records; skip features with unusable linestrings."""
    for f in features:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        way_id = way_numeric_id(props)
        if geom.get("type") != "LineString" or way_id is None:
            logger.warning("skip lane feature without linestring geometry/way id: %s", props.get("@id"))
            continue
        path = clean_linestring(geom.get("coordinates") or [])
        if path is None:
            logger.warning("skip degenerate lane linestring %s", way_id)
            continue
        highway = props.get("highway")
        width, width_source = way_width(props)
        surface = props.get("surface")
        attrs = {
            "source": OSM_SOURCE,
            "osm_id": f"way/{way_id}",
            "osm_type": "way",
            "osm_tags": original_osm_tags(props),
            "road_class": props.get("road_class"),
            "label_data": LABEL_OSM,
            "demo": False,
            "verified": False,
            "width_verified": False,
            "width_source": width_source,
        }
        yield {
            "code": f"{OSM_BUILDING_PREFIX}{way_id}",
            "name": way_name(props, way_id, highway),
            "width_m": width,
            "stairs": False,
            "slope_pct": 0.0,
            "vehicle_access": highway != "footway",
            "blocked": False,
            "surface": (surface if isinstance(surface, str) and surface.strip() else "paved")[:32],
            "length_m": round(linestring_length_m(path), 2),
            "path": path,
            "attributes": attrs,
        }


def allocate_lane_nodes(lane_records: list[dict[str, Any]]) -> tuple[dict[tuple[float, float], str], dict[str, list[float]]]:
    """One LaneNode per unique endpoint coordinate, shared across ways.

    Keys are rounded to 7 decimals (~1 cm) so ways meeting at the same OSM
    vertex become connected. Codes are assigned in sorted coordinate order for
    deterministic, idempotent re-runs.
    """
    key_of: dict[tuple[float, float], str] = {}
    positions: dict[str, list[float]] = {}
    endpoints: set[tuple[float, float]] = set()
    for rec in lane_records:
        endpoints.add((round(rec["path"][0][0], 7), round(rec["path"][0][1], 7)))
        endpoints.add((round(rec["path"][-1][0], 7), round(rec["path"][-1][1], 7)))
    for i, key in enumerate(sorted(endpoints), start=1):
        code = f"{OSM_NODE_PREFIX}{i:04d}"
        key_of[key] = code
        positions[code] = [key[0], key[1]]
    for rec in lane_records:
        rec["node_a_code"] = key_of[(round(rec["path"][0][0], 7), round(rec["path"][0][1], 7))]
        rec["node_b_code"] = key_of[(round(rec["path"][-1][0], 7), round(rec["path"][-1][1], 7))]
    return key_of, positions


def assign_building_access_nodes(
    building_records: list[dict[str, Any]], node_positions: dict[str, list[float]]
) -> None:
    """Access node = nearest imported lane-network node (real OSM road node)."""
    if not node_positions:
        return
    for rec in building_records:
        best_code = None
        best_d = float("inf")
        for code, pos in node_positions.items():
            d = dist_m_sqrt(rec["center"], pos)
            if d < best_d:
                best_d = d
                best_code = code
        rec["access_node_code"] = best_code or ""
        rec["attributes"] = {
            **rec["attributes"],
            "access_node_distance_m": round(best_d, 2) if best_code else None,
        }


def point_wkt(pos: list[float]) -> str:
    return f"POINT({pos[0]:.8f} {pos[1]:.8f})"


def line_wkt(path: list[list[float]]) -> str:
    pts = ", ".join(f"{p[0]:.8f} {p[1]:.8f}" for p in path)
    return f"LINESTRING({pts})"


def poly_wkt(footprint: list[list[float]]) -> str:
    pts = ", ".join(f"{p[0]:.8f} {p[1]:.8f}" for p in footprint)
    return f"POLYGON(({pts}))"


async def _upsert_nodes(session: AsyncSession, positions: dict[str, list[float]]) -> dict[str, LaneNode]:
    codes = list(positions.keys())
    existing_rows = (await session.execute(select(LaneNode).where(LaneNode.code.in_(codes)))).scalars().all()
    existing = {n.code: n for n in existing_rows}
    created = 0
    for code, pos in positions.items():
        if code in existing:
            continue
        session.add(
            LaneNode(
                code=code,
                label=f"OSM node {code.split('-')[1]}",
                kind="junction",
                pos=pos,
                attributes={"source": OSM_SOURCE, "demo": False},
                geom=point_wkt(pos),
            )
        )
        created += 1
    await session.flush()
    if created:
        logger.info("lane nodes created: %d", created)
    return existing


async def _upsert_lanes(session: AsyncSession, lane_records: list[dict[str, Any]]) -> tuple[int, int]:
    codes = [r["code"] for r in lane_records]
    existing_rows = (await session.execute(select(Lane).where(Lane.code.in_(codes)))).scalars().all()
    existing = {l.code: l for l in existing_rows}
    created = 0
    updated = 0
    for r in lane_records:
        row = existing.get(r["code"])
        if row is None:
            session.add(
                Lane(
                    code=r["code"],
                    name=r["name"],
                    width_m=r["width_m"],
                    stairs=r["stairs"],
                    slope_pct=r["slope_pct"],
                    vehicle_access=r["vehicle_access"],
                    blocked=r["blocked"],
                    surface=r["surface"],
                    length_m=r["length_m"],
                    node_a_code=r["node_a_code"],
                    node_b_code=r["node_b_code"],
                    path=r["path"],
                    attributes=r["attributes"],
                    geom=line_wkt(r["path"]),
                )
            )
            created += 1
        else:
            row.name = r["name"]
            row.width_m = r["width_m"]
            row.vehicle_access = r["vehicle_access"]
            row.surface = r["surface"]
            row.length_m = r["length_m"]
            row.node_a_code = r["node_a_code"]
            row.node_b_code = r["node_b_code"]
            row.path = r["path"]
            row.attributes = r["attributes"]
            row.geom = line_wkt(r["path"])
            updated += 1
    await session.flush()
    return created, updated


async def _upsert_buildings(session: AsyncSession, building_records: list[dict[str, Any]]) -> tuple[int, int]:
    codes = [r["code"] for r in building_records]
    existing_rows = (await session.execute(select(Building).where(Building.code.in_(codes)))).scalars().all()
    existing = {b.code: b for b in existing_rows}
    created = 0
    updated = 0
    for r in building_records:
        row = existing.get(r["code"])
        if row is None:
            session.add(
                Building(
                    code=r["code"],
                    name=r["name"],
                    floors=r["floors"],
                    building_type=r["building_type"],
                    construction=r["construction"],
                    occupancy=r["occupancy"],
                    year_built=r["year_built"],
                    height_m=r["height_m"],
                    priority=r["priority"],
                    status=r["status"],
                    center=r["center"],
                    footprint=r["footprint"],
                    access_node_code=r.get("access_node_code", ""),
                    attributes=r["attributes"],
                    geom=poly_wkt(r["footprint"]),
                    center_point=point_wkt(r["center"]),
                )
            )
            created += 1
        else:
            row.name = r["name"]
            row.floors = r["floors"]
            row.building_type = r["building_type"]
            row.height_m = r["height_m"]
            row.center = r["center"]
            row.footprint = r["footprint"]
            row.access_node_code = r.get("access_node_code", "")
            row.attributes = r["attributes"]
            row.geom = poly_wkt(r["footprint"])
            row.center_point = point_wkt(r["center"])
            updated += 1
    await session.flush()
    return created, updated


def _dataset_bbox(features: list[dict[str, Any]]) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for f in features:
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if geom.get("type") == "Polygon":
            pts = coords[0] if coords else []
        elif geom.get("type") == "LineString":
            pts = coords
        else:
            pts = []
        for p in pts:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


async def import_osm(
    session: AsyncSession,
    buildings_path: str | Path,
    lanes_path: str | Path,
) -> dict[str, Any]:
    """Import both OSM datasets idempotently. Returns import statistics.

    The caller owns the transaction (commit/rollback).
    """
    buildings_path = Path(buildings_path)
    lanes_path = Path(lanes_path)
    buildings_fc = json.loads(buildings_path.read_text(encoding="utf-8"))
    lanes_fc = json.loads(lanes_path.read_text(encoding="utf-8"))

    building_records = list(iter_building_records(buildings_fc.get("features") or []))
    lane_records = list(iter_lane_records(lanes_fc.get("features") or []))
    _, node_positions = allocate_lane_nodes(lane_records)
    assign_building_access_nodes(building_records, node_positions)

    nodes_existing = await _upsert_nodes(session, node_positions)
    lanes_created, lanes_updated = await _upsert_lanes(session, lane_records)
    buildings_created, buildings_updated = await _upsert_buildings(session, building_records)

    await session.execute(
        text(
            "UPDATE buildings SET geom = ST_MakeValid(geom) "
            "WHERE code LIKE :prefix AND NOT ST_IsValid(geom)"
        ),
        {"prefix": f"{OSM_BUILDING_PREFIX}%"},
    )

    stats = {
        "buildings_created": buildings_created,
        "buildings_updated": buildings_updated,
        "buildings_skipped": len(buildings_fc.get("features") or []) - len(building_records),
        "lanes_created": lanes_created,
        "lanes_updated": lanes_updated,
        "lanes_skipped": len(lanes_fc.get("features") or []) - len(lane_records),
        "nodes_created": len(node_positions) - len(nodes_existing),
        "nodes_total": len(node_positions),
        "buildings_bbox": _dataset_bbox(buildings_fc.get("features") or []),
        "lanes_bbox": _dataset_bbox(lanes_fc.get("features") or []),
    }
    logger.info("OSM import: %s", stats)
    return stats
