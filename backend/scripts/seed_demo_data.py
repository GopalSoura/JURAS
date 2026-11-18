import asyncio
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.db.session import SessionFactory, engine
from app.iot.registry import IOT_DEVICE_BY_SENSOR
from app.models import (
    Building,
    GraphEdge,
    Incident,
    IncidentEvent,
    Lane,
    LaneNode,
    Reading,
    RiskAssessment,
    Sensor,
    Simulation,
)

ORIGIN_LON = 74.8575
ORIGIN_LAT = 32.7285
M_LAT = 110574.0
M_LON = 111320.0 * math.cos(math.radians(32.7285))
DATA_LABEL = "Illustrative demo data, not surveyed Purani Mandi geometry"


def xy(x: float, y: float) -> list[float]:
    return [ORIGIN_LON + x / M_LON, ORIGIN_LAT + y / M_LAT]


def rect_polygon(center: list[float], w: float, d: float, rot_deg: float) -> list[list[float]]:
    hw, hd = w / 2, d / 2
    r = math.radians(rot_deg)
    pts = []
    for dx, dy in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)):
        x = dx * math.cos(r) - dy * math.sin(r)
        y = dx * math.sin(r) + dy * math.cos(r)
        pts.append([center[0] + x / M_LON, center[1] + y / M_LAT])
    pts.append(list(pts[0]))
    return pts


def dist_m(a: list[float], b: list[float]) -> float:
    return math.hypot((a[0] - b[0]) * M_LON, (a[1] - b[1]) * M_LAT)


LANE_NODES = [
    ("A", -300, -160, "fire_post", "Fire Post (demo)"),
    ("B", -150, -160, "junction", "Junction B"),
    ("C", 0, -160, "junction", "Junction C"),
    ("D", 160, -160, "junction", "Junction D"),
    ("E", 300, -160, "medical_post", "Medical Post (demo)"),
    ("F", -300, 0, "junction", "Junction F"),
    ("G", -300, 140, "assembly", "Assembly AP-1"),
    ("H", -150, -40, "junction", "Junction H"),
    ("I", -150, 70, "junction", "Junction I"),
    ("J", -150, 170, "junction", "Junction J"),
    ("K", 0, -60, "junction", "Junction K"),
    ("L", 0, 50, "junction", "Junction L"),
    ("M", 0, 160, "junction", "Junction M"),
    ("N", 160, -60, "junction", "Junction N"),
    ("O", 160, 60, "junction", "Junction O"),
    ("P", 160, 170, "junction", "Junction P"),
    ("Q", 300, 40, "assembly", "Assembly AP-2"),
]

LANE_EDGES = [
    ("A", "B", 7, False), ("B", "C", 7, False), ("C", "D", 7, False), ("D", "E", 7, False),
    ("A", "F", 6, False), ("F", "G", 5, False),
    ("B", "H", 3.2, False), ("H", "I", 3.8, False), ("I", "J", 4, False),
    ("C", "K", 4.2, False), ("K", "L", 2.4, False), ("L", "M", 2.4, False),
    ("D", "N", 3.6, False), ("N", "O", 1.8, True), ("O", "P", 1.8, False),
    ("H", "K", 3.6, False), ("K", "N", 3.6, False),
    ("I", "L", 3.2, False), ("L", "O", 1.6, True),
    ("J", "M", 3, False), ("M", "P", 2, False),
    ("G", "J", 4.5, False), ("F", "H", 2.8, False),
    ("E", "Q", 6, False), ("Q", "O", 2.8, False),
]

BUILDING_DEFS = [
    ("B-014", "Raghunath Bazaar Block 14", -60, -100, 22, 14, 8, 3, 1928, "Mixed use", "Brick masonry", 140, 62, None, None, "2025-11-14"),
    ("B-021", "Purani Mandi Timber Store", 30, 70, 18, 12, -6, 2, 1951, "Storage", "Timber frame", 12, 71, None, None, "2025-08-02"),
    ("B-007", "Mohalla Haveli Complex", -190, 100, 26, 20, 4, 4, 1910, "Residential", "Brick-lime masonry", 96, 82, 0.52, 0.6, "2025-03-21"),
    ("B-032", "Kanak Mandi Textile Shops", -110, -110, 24, 12, 0, 2, 1962, "Commercial", "Brick masonry", 60, 48, None, None, "2026-01-09"),
    ("B-045", "Rani Bagh Row Houses", -230, -60, 30, 12, -3, 3, 1974, "Residential", "RCC frame", 110, 39, None, None, "2026-02-17"),
    ("B-052", "Mubarak Dharamshala", 110, -110, 20, 20, 10, 3, 1936, "Institutional", "Stone masonry", 80, 77, 0.18, 0.2, "2025-05-30"),
    ("B-061", "Gole Market Arcade", 200, -105, 28, 14, 0, 2, 1968, "Commercial", "RCC frame", 90, 44, None, None, "2026-03-04"),
    ("B-066", "Bazaar Chowk Sweet Shops", 75, -35, 16, 12, 5, 2, 1955, "Food and commercial", "Mixed masonry", 45, 58, None, None, "2025-10-12"),
    ("B-073", "Shiv Gali Tenements", -80, 10, 18, 14, -8, 4, 1940, "Residential", "Brick-lime masonry", 88, 68, 0.21, 0.3, "2025-07-19"),
    ("B-081", "Old Post Office Annex", -45, 115, 22, 16, 0, 2, 1925, "Government", "Stone masonry", 35, 55, 0.12, 0.15, "2025-12-01"),
    ("B-088", "Chowk Residential Block", 215, 20, 20, 16, 6, 3, 1981, "Residential", "RCC frame", 74, 33, None, None, "2026-04-22"),
    ("B-095", "Lakhdata Bazaar Shops", 120, 130, 26, 14, 0, 2, 1948, "Commercial", "Brick masonry", 52, 64, None, None, "2025-09-08"),
    ("B-102", "Temple Lane Guest House", -235, 170, 18, 16, -4, 3, 1990, "Hospitality", "RCC frame", 40, 30, None, None, "2026-05-11"),
    ("B-109", "Mandi Warehouse", 245, -50, 24, 18, 0, 1, 1971, "Storage", "Steel and brick", 8, 52, None, None, "2025-06-26"),
]

SMOKE_SENSORS = [
    ("JM-014", "B-014", "Smoke + temp, B-014"),
    ("JM-021a", "B-021", "Smoke + temp, B-021 front"),
    ("JM-021b", "B-021", "Smoke + temp, B-021 rear"),
    ("JM-052", "B-052", "Smoke + temp, B-052"),
    ("JM-066", "B-066", "Smoke + temp, B-066"),
    ("JM-073", "B-073", "Smoke + temp, B-073"),
    ("JM-095", "B-095", "Smoke + temp, B-095"),
]

STRUCTURE_SENSORS = [
    ("JM-S07", "B-007", "Tilt + crack, B-007"),
    ("JM-S52", "B-052", "Tilt + crack, B-052"),
    ("JM-S73", "B-073", "Tilt + crack, B-073"),
    ("JM-S81", "B-081", "Tilt + crack, B-081"),
]

RAIN_SENSORS = [
    ("JM-R01", -75, 60, "Lane I-L low point", "I", 1.0),
    ("JM-R02", 160, 60, "Junction O", "O", 0.6),
    ("JM-R03", 0, 160, "Lane M sump", "M", 0.8),
]


def sensor_attrs(code: str, base: dict) -> dict:
    """Add Wokwi device metadata only to the three registered simulation nodes."""
    device = IOT_DEVICE_BY_SENSOR.get(code)
    if device is not None:
        base = {
            **base,
            "device_id": device.device_id,
            "wokwi": True,
            "simulation": True,
            "label_data": "Wokwi ESP32 simulation node, not a field sensor",
        }
    return base


def point_wkt(pos: list[float]) -> str:
    return f"POINT({pos[0]:.8f} {pos[1]:.8f})"


def line_wkt(path: list[list[float]]) -> str:
    pts = ", ".join(f"{p[0]:.8f} {p[1]:.8f}" for p in path)
    return f"LINESTRING({pts})"


def poly_wkt(footprint: list[list[float]]) -> str:
    pts = ", ".join(f"{p[0]:.8f} {p[1]:.8f}" for p in footprint)
    return f"POLYGON(({pts}))"


async def seed() -> None:
    async with SessionFactory() as session:
        for table in (IncidentEvent, Incident, Reading, RiskAssessment, Simulation, GraphEdge, Sensor, Lane, LaneNode, Building):
            await session.execute(delete(table))
        await session.flush()

        node_pos = {}
        for code, x, y, kind, label in LANE_NODES:
            pos = xy(x, y)
            node_pos[code] = pos
            session.add(
                LaneNode(
                    code=code, label=label, kind=kind, pos=pos,
                    attributes={"label_data": DATA_LABEL},
                    geom=point_wkt(pos),
                )
            )
        await session.flush()

        lane_by_pair = {}
        for a, b, width, stairs in LANE_EDGES:
            code = f"{a}-{b}"
            path = [node_pos[a], node_pos[b]]
            length = dist_m(node_pos[a], node_pos[b])
            lane_by_pair[(a, b)] = (code, length)
            session.add(
                Lane(
                    code=code, name=f"Lane {a}-{b}", width_m=width, stairs=stairs,
                    slope_pct=0.0, vehicle_access=not stairs and width >= 3.5,
                    blocked=False, surface="paved", length_m=length,
                    node_a_code=a, node_b_code=b, path=path,
                    attributes={"label_data": DATA_LABEL},
                    geom=line_wkt(path),
                )
            )
            session.add(
                GraphEdge(
                    from_node=a, to_node=b, lane_code=code, length_m=length,
                    cost=length, width_m=width, stairs=stairs,
                    slope_pct=0.0, vehicle_access=not stairs and width >= 3.5, blocked=False,
                )
            )
            session.add(
                GraphEdge(
                    from_node=b, to_node=a, lane_code=code, length_m=length,
                    cost=length, width_m=width, stairs=stairs,
                    slope_pct=0.0, vehicle_access=not stairs and width >= 3.5, blocked=False,
                )
            )
        await session.flush()

        node_codes = list(node_pos.keys())
        building_rows = {}
        for code, name, x, y, w, d, rot, floors, year, use, construction, occ, priority, tilt, crack, inspected in BUILDING_DEFS:
            center = xy(x, y)
            footprint = rect_polygon(center, w, d, rot)
            best, best_d = node_codes[0], float("inf")
            for nc in node_codes:
                dd = dist_m(node_pos[nc], center)
                if dd < best_d:
                    best, best_d = nc, dd
            attrs = {
                "tilt_deg": tilt if tilt is not None else 0.06,
                "crack_mm": crack if crack is not None else 0.1,
                "last_inspection": inspected,
                "label_data": DATA_LABEL,
                "demo": True,
            }
            b = Building(
                code=code, name=name, floors=floors, building_type=use,
                construction=construction, occupancy=occ, year_built=year,
                height_m=round(floors * 3.3, 1), priority=priority,
                status="watch" if (tilt or 0) >= 0.45 else "ok",
                center=center, footprint=footprint, access_node_code=best,
                attributes=attrs, geom=poly_wkt(footprint), center_point=point_wkt(center),
            )
            session.add(b)
            building_rows[code] = b
        await session.flush()

        for code, bcode, label in SMOKE_SENSORS:
            i = SMOKE_SENSORS.index((code, bcode, label))
            b = building_rows[bcode]
            offset = 0.00004 if i % 2 else -0.00004
            pos = [b.center[0] + offset, b.center[1]]
            session.add(
                Sensor(
                    code=code, label=label, kind="smoke_temp", building_id=b.id,
                    node_code=None, status="active", source="simulation", pos=pos,
                    attributes=sensor_attrs(code, {"label_data": DATA_LABEL}), geom=point_wkt(pos),
                )
            )
        for code, bcode, label in STRUCTURE_SENSORS:
            b = building_rows[bcode]
            pos = list(b.center)
            session.add(
                Sensor(
                    code=code, label=label, kind="structure", building_id=b.id,
                    node_code=None, status="active", source="simulation", pos=pos,
                    attributes=sensor_attrs(code, {"label_data": DATA_LABEL}), geom=point_wkt(pos),
                )
            )
        for code, x, y, label, node_code, factor in RAIN_SENSORS:
            pos = xy(x, y)
            session.add(
                Sensor(
                    code=code, label=label, kind="rain_level", building_id=None,
                    node_code=node_code, status="active", source="simulation", pos=pos,
                    attributes=sensor_attrs(code, {"flood_factor": factor, "label_data": DATA_LABEL}),
                    geom=point_wkt(pos),
                )
            )
        await session.flush()

        now = datetime.now(timezone.utc)
        b7 = building_rows["B-007"]
        b066 = building_rows["B-066"]
        demo_incidents = [
            Incident(
                code="AL-STR-B-007", hazard="structural", building_id=b7.id,
                node_code=None, severity="medium", status="acknowledged",
                title="Tilt watch, B-007",
                description="Mohalla Haveli Complex, built 1910, Brick-lime masonry. Illustrative demo alert.",
                source="simulation", simulation_id=None,
                opened_at=now - timedelta(minutes=180),
                acknowledged_at=now - timedelta(minutes=40),
                pos=b7.center, geom=point_wkt(b7.center),
            ),
            Incident(
                code="AL-RES-1", hazard="fire", building_id=b066.id,
                node_code=None, severity="low", status="resolved",
                title="Smoke spike cleared, JM-066",
                description="Cooking smoke at a sweet shop. Single sensor, not confirmed. Demo record.",
                source="simulation", simulation_id=None,
                opened_at=now - timedelta(minutes=300),
                resolved_at=now - timedelta(minutes=294),
                pos=b066.center, geom=point_wkt(b066.center),
            ),
            Incident(
                code="AL-RES-2", hazard="flood", building_id=None,
                node_code="K", severity="medium", status="resolved",
                title="Drain overflow, Junction K",
                description="Cleared after desilting crew visit. Demo record.",
                source="simulation", simulation_id=None,
                opened_at=now - timedelta(minutes=420),
                resolved_at=now - timedelta(minutes=360),
                pos=node_pos["K"], geom=point_wkt(node_pos["K"]),
            ),
        ]
        for inc in demo_incidents:
            session.add(inc)
        await session.flush()
        for inc in demo_incidents:
            session.add(
                IncidentEvent(
                    incident_id=inc.id, action="opened", old_status=None,
                    new_status=inc.status, actor="seed", note="Seeded demo record",
                )
            )
        await session.commit()
    print(f"Seeded {len(LANE_NODES)} nodes, {len(LANE_EDGES)} lanes, {len(BUILDING_DEFS)} buildings, {len(SMOKE_SENSORS) + len(STRUCTURE_SENSORS) + len(RAIN_SENSORS)} sensors. {DATA_LABEL}")


if __name__ == "__main__":
    asyncio.run(seed())
