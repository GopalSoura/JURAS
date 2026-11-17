import asyncio
import logging
import math
import random
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models import Building, Lane, LaneNode, Sensor, Incident, IncidentEvent
from app.core.constants import IncidentStatus, Hazard
from app.repositories import building_repo, incident_repo
from app.services import incident_service
from app.services.navigation_service import lane_inputs
from app.services.simulation_navigation_service import plan_osm_routes_for_building
from app.routing.graph import Graph, LaneEdgeData, LaneNodeData, dist_m_sqrt
from app.routing.osm_graph import build_navigation_graph
from app.state import app_state

logger = logging.getLogger("juras.ws_adapter")

M_LAT = 110574.0
M_LON = 111320.0 * 0.84119298

FLOOD_FACTOR_DEFAULT = 0.5

INTERVENTION_DEFS = [
    {"id": "IV-1", "name": "Rain garden and bioswale", "where": "Open plot near Junction I", "pos": None, "reduces_pct": 28, "cost_lakh": 6},
    {"id": "IV-2", "name": "Desilt and upsize drain", "where": "Junction K", "pos": None, "reduces_pct": 22, "cost_lakh": 3},
    {"id": "IV-3", "name": "Permeable paving", "where": "Lane I-L", "pos": None, "reduces_pct": 18, "cost_lakh": 4.5},
    {"id": "IV-4", "name": "Recharge pit", "where": "Assembly AP-1 ground", "pos": None, "reduces_pct": 15, "cost_lakh": 2.4},
]

FIRE_PICK = ["B-014", "B-052", "B-066", "B-073", "B-095", "B-021"]
CRACK_PICK = ["B-007", "B-073", "B-052"]


def clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def r1(v: float) -> float:
    return round(v, 1)


def r2(v: float) -> float:
    return round(v, 2)


def now_ms() -> float:
    return time.time() * 1000.0


class FrontendWorld:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], manager) -> None:
        self.session_factory = session_factory
        self.manager = manager
        self.ui_connections: set[WebSocket] = set()
        self.buildings: dict[str, dict[str, Any]] = {}
        self.base_buildings: dict[str, dict[str, Any]] = {}
        self.building_by_id: dict[str, str] = {}
        self.sensors: list[dict[str, Any]] = []
        self.graph: Graph | None = None
        self.osm_graph = None
        self.alerts: dict[str, dict[str, Any]] = {}
        self.routes: dict[str, list[dict[str, Any]]] = {}
        self.hazards: dict[str, dict[str, Any]] = {}
        self.zones: list[dict[str, Any]] = []
        self.interventions: list[dict[str, Any]] = []
        self.last_key: dict[str, str] = {}
        self.incident_links: dict[str, str] = {}
        self.fires: dict[str, dict[str, Any]] = {}
        self.cracks: dict[str, float] = {}
        self.flood_t0: float | None = None
        self.rain = 0.0
        self.levels: dict[str, float] = {}
        self.battery: dict[str, float] = {}
        self.zone_key = ""
        self._lock = asyncio.Lock()
        self._load_lock = asyncio.Lock()
        self._telemetry_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> bool:
        await ws.accept()
        if self._telemetry_task is None or self._telemetry_task.done():
            self._telemetry_task = asyncio.create_task(self.telemetry_loop())
        if not self.buildings:
            async with self._load_lock:
                if not self.buildings:
                    await self.load_world()
        if not await self.send_raw(ws, await self.build_snapshot()):
            return False
        self.ui_connections.add(ws)
        return True

    def disconnect(self, ws: WebSocket) -> None:
        self.ui_connections.discard(ws)

    async def send_raw(self, ws: WebSocket, payload: dict[str, Any]) -> bool:
        try:
            await ws.send_json(payload)
        except Exception:
            self.disconnect(ws)
            return False
        return True

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.ui_connections):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def load_world(self) -> None:
        async with self.session_factory() as session:
            buildings = await building_repo.list_buildings(session)
            nodes = await session.execute(select(LaneNode).order_by(LaneNode.code))
            lanes = await session.execute(select(Lane))
            sensors = await session.execute(select(Sensor))
            self.building_by_id = {str(b.id): b.code for b in buildings}
            self.buildings = {}
            self.base_buildings = {}
            for b in buildings:
                attrs = b.attributes or {}
                shape = {
                    "id": b.code,
                    "name": b.name,
                    "center": b.center,
                    "footprint": b.footprint,
                    "floors": b.floors,
                    "height_m": b.height_m,
                    "year_built": b.year_built,
                    "use": b.building_type,
                    "construction": b.construction,
                    "occupancy": b.occupancy,
                    "priority": b.priority,
                    "status": b.status,
                    "tilt_deg": float(attrs.get("tilt_deg", 0.06)),
                    "crack_mm": float(attrs.get("crack_mm", 0.1)),
                    "last_inspection": attrs.get("last_inspection", ""),
                    "access_node": b.access_node_code,
                }
                self.buildings[b.code] = dict(shape)
                self.base_buildings[b.code] = dict(shape)
            node_data = [
                LaneNodeData(id=n.code, pos=n.pos, label=n.label, kind=n.kind)
                for n in nodes.scalars().all()
            ]
            lane_rows = list(lanes.scalars().all())
            edge_data = [
                LaneEdgeData(id=l.code, a=l.node_a_code, b=l.node_b_code, width_m=l.width_m, stairs=l.stairs)
                for l in lane_rows
            ]
            self.graph = Graph.build(node_data, edge_data)
            osm_lanes = [
                lane for lane in lane_rows if (lane.attributes or {}).get("source") == "osm"
            ]
            self.osm_graph = build_navigation_graph(lane_inputs(osm_lanes)) if osm_lanes else None
            self.sensors = [
                {
                    "node_id": s.code,
                    "kind": s.kind,
                    "pos": s.pos,
                    "label": s.label,
                    "building_id": self.building_by_id.get(str(s.building_id)) if s.building_id else None,
                    "node_code": s.node_code,
                    "flood_factor": float((s.attributes or {}).get("flood_factor", FLOOD_FACTOR_DEFAULT)),
                }
                for s in sensors.scalars().all()
            ]
            self.levels = {s["node_id"]: 0.0 for s in self.sensors if s["kind"] == "rain_level"}
            self.battery = {s["node_id"]: 72.0 + random.random() * 24.0 for s in self.sensors}
            incidents = await incident_repo.list_incidents(session)
            for i in incidents:
                if i.status in (IncidentStatus.open.value, IncidentStatus.acknowledged.value):
                    self.alerts[i.code] = self._alert_from_incident(i)
                elif i.status == IncidentStatus.resolved.value and i.code not in self.alerts:
                    self.alerts.setdefault(i.code, self._alert_from_incident(i))
            for iv in INTERVENTION_DEFS:
                iv["pos"] = self._pos_for_intervention(iv["where"])
            self.interventions = []

    def _pos_for_intervention(self, where: str) -> list[float]:
        positions = {
            "Open plot near Junction I": [-175, 95],
            "Junction K": [0, -60],
            "Lane I-L": [-75, 60],
            "Assembly AP-1 ground": [-300, 140],
        }
        local = positions.get(where, [0, 0])
        return [
            74.8575 + local[0] / M_LON,
            32.7285 + local[1] / M_LAT,
        ]

    def _alert_from_incident(self, i: Incident) -> dict[str, Any]:
        module = {"fire": "fire", "flood": "flood", "structural": "structure"}.get(i.hazard, "map")
        status = {"open": "new", "acknowledged": "ack", "resolved": "resolved"}.get(i.status, "new")
        bcode = self.building_by_id.get(str(i.building_id)) if i.building_id else None
        return {
            "id": i.code,
            "module": module,
            "severity": i.severity,
            "status": status,
            "title": i.title,
            "detail": i.description[:180],
            "building_id": bcode,
            "pos": i.pos,
            "confidence": 0.7,
            "sources": [],
            "created_at": i.opened_at.timestamp() * 1000.0,
            "updated_at": (i.acknowledged_at or i.opened_at).timestamp() * 1000.0,
            "recommendation": None,
        }

    async def build_snapshot(self) -> dict[str, Any]:
        return {
            "t": "snapshot",
            "buildings": list(self.buildings.values()),
            "lane_nodes": [
                {"id": n.id, "pos": n.pos, "label": n.label, "kind": n.kind}
                for n in (self.graph.nodes.values() if self.graph else [])
            ],
            "lane_edges": [
                {"id": e.id, "a": e.a, "b": e.b, "width_m": e.width_m, "stairs": e.stairs}
                for e in self.graph_edges()
            ],
            "sensors": [
                {k: s[k] for k in ("node_id", "kind", "pos", "label", "building_id")}
                for s in self.sensors
            ],
            "alerts": list(self.alerts.values()),
            "routes": dict(self.routes),
            "hazards": [h for h in self.hazards.values() if h.get("active", True)],
            "flood_zones": self.zones,
            "interventions": self.interventions,
        }

    def graph_edges(self) -> list[LaneEdgeData]:
        seen = set()
        out = []
        for arcs in (self.graph.adj.values() if self.graph else []):
            for a in arcs:
                if a.edge.id not in seen:
                    seen.add(a.edge.id)
                    out.append(a.edge)
        return out

    async def handle_event(self, name: str, data: dict[str, Any]) -> None:
        async with self._lock:
            if name == "simulation.started":
                scenario = data.get("scenario")
                if scenario == "fire":
                    bcode = data.get("target_building_code") or self._code_of(data.get("target_building_id"))
                    if bcode:
                        self.fires[bcode] = {"t0": now_ms(), "auto": False, "sim_id": data.get("simulation_id")}
                elif scenario == "structural":
                    bcode = data.get("target_building_code") or self._code_of(data.get("target_building_id"))
                    if bcode:
                        self.cracks[bcode] = now_ms()
                elif scenario == "flood":
                    self.flood_t0 = now_ms()
            elif name == "incident.created":
                self._link_incident(data)
            elif name == "incident.updated":
                self._on_incident_updated(data)

    def _code_of(self, building_id: str | None) -> str | None:
        return self.building_by_id.get(building_id or "") if building_id else None

    def _link_incident(self, data: dict[str, Any]) -> None:
        code = data.get("code", "")
        hazard = data.get("hazard")
        bcode = self.building_by_id.get(data.get("building_id") or "")
        alert_id = self._alert_id_for(hazard, bcode or data.get("node_code"))
        if alert_id:
            self.incident_links[code] = alert_id

    def _alert_id_for(self, hazard: str | None, target: str | None) -> str | None:
        if not target:
            return None
        prefix = {"fire": "AL-FIRE-", "flood": "AL-FLOOD-", "structural": "AL-STR-"}.get(hazard or "", "")
        if hazard == "flood":
            return None
        return f"{prefix}{target}" if prefix else None

    def _on_incident_updated(self, data: dict[str, Any]) -> None:
        code = data.get("code", "")
        new_status = data.get("status")
        alert_id = self.incident_links.get(code)
        if alert_id is None:
            return
        alert = self.alerts.get(alert_id)
        if alert is None:
            return
        status_map = {"open": "new", "acknowledged": "ack", "resolved": "resolved", "false_alarm": "resolved"}
        alert["status"] = status_map.get(new_status, alert["status"])
        alert["updated_at"] = now_ms()
        self.alerts[alert_id] = alert
        asyncio.get_event_loop().create_task(self.broadcast({"t": "alert", "alert": alert}))
        if new_status == "resolved":
            asyncio.get_event_loop().create_task(self._on_resolved(alert))

    async def _on_resolved(self, alert: dict[str, Any]) -> None:
        if alert["module"] == "fire" and alert.get("building_id"):
            bid = alert["building_id"]
            self.fires.pop(bid, None)
            hz = self.hazards.get(f"HZ-{bid}")
            if hz:
                hz = {**hz, "active": False}
                self.hazards[hz["id"]] = hz
                app_state.deactivate_hazard(hz["id"])
                await self.broadcast({"t": "hazard", "hazard": hz})
            self.routes.pop(alert["id"], None)
            await self.broadcast({"t": "routes", "alert_id": alert["id"], "routes": []})
            self._patch_building(bid, {"status": "ok"})
        if alert["module"] == "structure" and alert.get("building_id"):
            self.cracks.pop(alert["building_id"], None)
            self._patch_building(alert["building_id"], {"status": "watch"})
        if alert["module"] == "flood":
            self.flood_t0 = None

    def _patch_building(self, bcode: str, patch: dict[str, Any]) -> None:
        b = self.buildings.get(bcode)
        if b is None:
            return
        b.update(patch)
        asyncio.get_event_loop().create_task(self.broadcast({"t": "building", "id": bcode, "patch": patch}))

    async def handle_cmd(self, ws: WebSocket, cmd: dict[str, Any]) -> None:
        kind = cmd.get("cmd")
        if kind == "scenario":
            name = cmd.get("name")
            if name == "reset":
                await self.reset_world()
            elif name == "fire":
                bcode = next((b for b in FIRE_PICK if b not in self.fires), None)
                if bcode:
                    await self._start_sim("fire", target_building_code=bcode)
            elif name == "crack":
                bcode = next((b for b in CRACK_PICK if b not in self.cracks), None)
                if bcode:
                    await self._start_sim("structural", target_building_code=bcode)
            elif name == "flood":
                if self.flood_t0 is None:
                    await self._start_sim("flood", target_node_code="I")
            return
        if kind == "alert_action":
            await self.handle_alert_action(cmd.get("id", ""), cmd.get("action", ""))

    async def _start_sim(self, scenario: str, target_building_code: str | None = None, target_node_code: str | None = None) -> None:
        async with self.session_factory() as session:
            if target_building_code:
                b = await building_repo.get_by_code(session, target_building_code)
                if b is None:
                    return
                await self.manager.start(
                    {
                        "scenario": scenario,
                        "target_building_id": str(b.id),
                        "severity": "warning",
                        "duration_sec": 90,
                        "actor": "ws:scenario",
                    }
                )
            else:
                await self.manager.start(
                    {
                        "scenario": scenario,
                        "target_node_code": target_node_code,
                        "severity": "warning",
                        "duration_sec": 90,
                        "actor": "ws:scenario",
                    }
                )

    async def handle_alert_action(self, alert_id: str, action: str) -> None:
        async with self.session_factory() as session:
            hazard_of = {"AL-FIRE-": "fire", "AL-FLOOD-": "flood", "AL-STR-": "structural"}
            incident = None
            for prefix, hazard in hazard_of.items():
                if alert_id.startswith(prefix):
                    active = await incident_repo.list_incidents(session, status="open", hazard=hazard)
                    candidates = [
                        i for i in active
                        if alert_id.endswith(self._target_suffix(i))
                    ]
                    if not candidates:
                        candidates = [
                            i for i in await incident_repo.list_incidents(session, status="acknowledged", hazard=hazard)
                            if alert_id.endswith(self._target_suffix(i))
                        ]
                    if candidates:
                        incident = candidates[0]
                    break
            if incident is None:
                incident = await incident_repo.get_by_code(session, alert_id)
            if incident is None:
                return
            events: list[tuple[str, dict[str, Any]]] = []
            if action == "ack" and incident.status == "open":
                await incident_service.transition(session, incident, "acknowledged", "operator:ui", "Acknowledged from dashboard", events)
            elif action == "dispatch" and incident.status in ("open", "acknowledged"):
                if incident.status == "open":
                    await incident_service.transition(session, incident, "acknowledged", "operator:ui", "Dispatched from dashboard", events)
                else:
                    await incident_repo.add_event(
                        session,
                        IncidentEvent(
                            incident_id=incident.id,
                            action="dispatched",
                            old_status=incident.status,
                            new_status=incident.status,
                            actor="operator:ui",
                            note="Responder dispatched",
                        ),
                    )
            elif action == "resolve":
                await incident_service.transition(session, incident, "resolved", "operator:ui", "Resolved from dashboard", events)
            await session.commit()
        from app.realtime.bus import bus

        for name, data in events:
            await bus.broadcast_event(name, data)

    def _target_suffix(self, incident: Incident) -> str:
        bcode = self.building_by_id.get(str(incident.building_id)) if incident.building_id else None
        return bcode or incident.node_code or ""

    async def reset_world(self) -> None:
        await self.manager.shutdown()
        self.alerts.clear()
        self.routes.clear()
        self.hazards.clear()
        app_state.clear_hazards()
        self.zones = []
        self.interventions = []
        app_state.set_flood_zones([])
        self.last_key.clear()
        self.incident_links.clear()
        self.fires.clear()
        self.cracks.clear()
        self.flood_t0 = None
        self.rain = 0.0
        self.levels = {s["node_id"]: 0.0 for s in self.sensors if s["kind"] == "rain_level"}
        for code, base in self.base_buildings.items():
            self.buildings[code] = dict(base)
        async with self.session_factory() as session:
            from sqlalchemy import update

            from app.models import Incident

            await session.execute(
                update(Incident).values(status=IncidentStatus.resolved.value, resolved_at=datetime.now(timezone.utc)).where(
                    Incident.status.in_([IncidentStatus.open.value, IncidentStatus.acknowledged.value])
                )
            )
            await session.commit()
        await self.broadcast(await self.build_snapshot())

    async def telemetry_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
                async with self._lock:
                    items = self._telemetry()
                    await self.broadcast({"t": "telemetry", "items": items})
                    await self._fusion_step(items)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("telemetry loop error")

    def _telemetry(self) -> list[dict[str, Any]]:
        t = now_ms()
        self._step_weather(t)
        items = []
        for s in self.sensors:
            bat = clamp((self.battery.get(s["node_id"], 80.0)) - random.random() * 0.002, 5, 100)
            self.battery[s["node_id"]] = bat
            base = {"node_id": s["node_id"], "kind": s["kind"], "ts": int(t), "battery": r1(bat)}
            if s["kind"] == "smoke_temp":
                smoke = 35 + random.uniform(-5, 5)
                temp = 31.5 + random.uniform(-0.4, 0.4)
                for bid, f in self.fires.items():
                    age = (t - f["t0"]) / 1000.0 - (5 if s["node_id"].endswith("b") else 0)
                    if age <= 0:
                        continue
                    fb = self.buildings.get(bid)
                    if fb is None:
                        continue
                    inf = 0.0
                    if s["building_id"] == bid:
                        inf = 1.0
                    else:
                        d = dist_m_sqrt(s["pos"], fb["center"])
                        if d < 130:
                            inf = 0.06 * (1 - d / 130)
                    smoke += min(900.0, age * 14) * inf
                    temp += min(110.0, age * 1.1) * inf
                items.append({**base, "values": {"smoke_ppm": round(smoke), "temp_c": r1(temp)}})
            elif s["kind"] == "structure":
                b0 = self.base_buildings.get(s.get("building_id") or "")
                base_tilt = (b0 or {}).get("tilt_deg", 0.06)
                base_crack = (b0 or {}).get("crack_mm", 0.1)
                tilt = base_tilt + random.uniform(-0.01, 0.01)
                crack = base_crack + random.uniform(-0.01, 0.01)
                vib = 0.02 + random.uniform(-0.004, 0.004)
                t0 = self.cracks.get(s.get("building_id") or "")
                if t0 is not None:
                    age = (t - t0) / 1000.0
                    tilt += min(1.1, age * 0.012)
                    crack += min(1.2, age * 0.02)
                    vib += age * 0.0004
                items.append(
                    {**base, "values": {"tilt_deg": r2(tilt), "crack_mm": r2(crack), "vib_rms": r2(vib * 10) / 10}}
                )
            else:
                rain_val = max(0.0, self.rain + (random.uniform(-1.5, 1.5) if self.rain > 0 else 0.0))
                items.append(
                    {**base, "values": {"rain_mmh": r1(rain_val), "level_cm": r1(self.levels.get(s["node_id"], 0.0))}}
                )
        return items

    def _step_weather(self, t: float) -> None:
        if self.flood_t0 is not None:
            self.rain = min(75.0, (t - self.flood_t0) / 1000.0 * 2)
        else:
            self.rain = max(0.0, self.rain - 3)
        for node_id, lvl in self.levels.items():
            factor = self._flood_factor(node_id)
            nxt = lvl + (self.rain - 18) * 0.012 * factor if self.rain > 18 else max(0.0, lvl - 0.25)
            self.levels[node_id] = max(0.0, nxt)

    def _flood_factor(self, node_id: str) -> float:
        for s in self.sensors:
            if s["node_id"] == node_id:
                return s.get("flood_factor", FLOOD_FACTOR_DEFAULT)
        return FLOOD_FACTOR_DEFAULT

    async def _fusion_step(self, items: list[dict[str, Any]]) -> None:
        by = {i["node_id"]: i for i in items}
        self._detect_fire(now_ms(), by)
        self._detect_structure(now_ms(), by)
        await self._detect_flood(now_ms(), by)

    def _put_alert(self, alert: dict[str, Any], key: str, dedupe_id: str) -> None:
        if self.last_key.get(dedupe_id) != key:
            self.last_key[dedupe_id] = key
            self.alerts[alert["id"]] = alert
            asyncio.get_event_loop().create_task(self.broadcast({"t": "alert", "alert": alert}))
        else:
            self.alerts[alert["id"]] = alert

    def _detect_fire(self, t: float, by: dict[str, dict[str, Any]]) -> None:
        if self.graph is None:
            return
        for b in self.buildings.values():
            nodes = [s for s in self.sensors if s["kind"] == "smoke_temp" and s.get("building_id") == b["id"]]
            if not nodes:
                continue
            alert_id = f"AL-FIRE-{b['id']}"
            prev = self.alerts.get(alert_id)
            if prev and prev.get("status") == "resolved":
                continue
            ps: list[tuple[float, dict[str, Any]]] = []
            for n in nodes:
                v = by[n["node_id"]]["values"]
                score = clamp(v["smoke_ppm"] / 400, 0, 1) * 0.6 + clamp((v["temp_c"] - 45) / 40, 0, 1) * 0.4
                if score >= 0.12:
                    ps.append(
                        (
                            min(0.9, score),
                            {
                                "kind": "sensor",
                                "label": f"{n['node_id']}: smoke {v['smoke_ppm']} ppm, {v['temp_c']:.0f} °C",
                                "ts": int(t),
                            },
                        )
                    )
            scn = self.fires.get(b["id"])
            age = (t - scn["t0"]) / 1000.0 if scn else 0.0
            if scn and age >= 14:
                ps.append((0.55, {"kind": "citizen", "label": "Citizen report: smoke from upper floor", "ts": int(scn["t0"] + 14000)}))
            if scn and age >= 22:
                ps.append((0.6, {"kind": "camera", "label": "CAM-03: smoke plume detected", "ts": int(scn["t0"] + 22000)}))
            conf = 1 - 1
            for p, _ in ps:
                conf *= 1 - p
            conf = 1 - conf
            if conf < 0.35 and prev is None:
                continue
            if conf < 0.2:
                continue
            confirmed = conf >= 0.8
            status = prev["status"] if prev else "new"
            dispatched_at = prev.get("dispatched_at") if prev else None
            if scn and scn.get("auto") and confirmed and not dispatched_at:
                status = "dispatched"
                dispatched_at = t - 6000
                scn["auto"] = False
            routes = self.routes.get(alert_id)
            if confirmed:
                radius = min(42.0, 18.0 + age * 0.35)
                hz = {
                    "id": f"HZ-{b['id']}",
                    "kind": "fire",
                    "pos": b["center"],
                    "radius_m": r1(radius),
                    "active": True,
                }
                step = int(radius / 1.5)
                if routes is None or (scn and step != scn.get("step")):
                    if scn:
                        scn["step"] = step
                    self.hazards[hz["id"]] = hz
                    app_state.set_hazard(hz["id"], hz)
                    asyncio.get_event_loop().create_task(self.broadcast({"t": "hazard", "hazard": hz}))
                    asyncio.get_event_loop().create_task(self._plan_fire_routes(alert_id, b, hz))
                if b["status"] != "fire":
                    self._patch_building(b["id"], {"status": "fire"})
            alert = {
                "id": alert_id,
                "module": "fire",
                "severity": "critical" if confirmed else "high",
                "status": status,
                "title": f"Fire confirmed, {b['id']}" if confirmed else f"Possible fire, {b['id']}",
                "detail": f"{b['name']}, {b['floors']} floors, about {b['occupancy']} occupants. Simulated data.",
                "building_id": b["id"],
                "pos": b["center"],
                "confidence": round(conf * 100) / 100,
                "sources": [x[1] for x in ps],
                "created_at": (prev or {}).get("created_at") or (scn["t0"] if scn else t),
                "updated_at": int(t),
                "dispatched_at": dispatched_at,
                "recommendation": "Evacuate via the route shown. Simulated demo, not a real emergency."
                if confirmed
                else "Waiting for a second independent signal before dispatch.",
            }
            key = f"{alert['severity']}|{round(conf * 50)}|{len(alert['sources'])}|{alert['status']}"
            self._put_alert(alert, key, alert_id)

    async def _plan_fire_routes(self, alert_id: str, b: dict[str, Any], hz: dict[str, Any]) -> None:
        async with self.session_factory() as session:
            building = await building_repo.get_by_code(session, b["id"])
            if building is None:
                return
            app_state.set_hazard(hz["id"], hz)
            ctx = app_state.routing_ctx()
            fire_post = self._post_pos("A")
            medical_post = self._post_pos("E")
            assemblies = [self._post_pos("G"), self._post_pos("Q")]
            routes = plan_osm_routes_for_building(
                self.osm_graph,
                building_center=list(b["center"]),
                building_name=b["name"],
                fire_post=fire_post,
                medical_post=medical_post,
                assemblies=assemblies,
                fire_label=self._post_label("A", "Fire post"),
                medical_label=self._post_label("E", "Medical post"),
                assembly_labels=[
                    self._post_label("G", "Assembly G"),
                    self._post_label("Q", "Assembly Q"),
                ],
                hazards=ctx["hazards"],
                floods=ctx["floods"],
                closures=ctx["closures"],
            )
            self.routes[alert_id] = routes
            await self.broadcast({"t": "routes", "alert_id": alert_id, "routes": routes})

    def _post_pos(self, code: str) -> list[float]:
        if self.graph is not None and code in self.graph.nodes:
            return list(self.graph.nodes[code].pos)
        return list(self.buildings.get(code, {}).get("center", [74.8575, 32.7285]))

    def _post_label(self, code: str, fallback: str) -> str:
        if self.graph is not None and code in self.graph.nodes:
            return self.graph.nodes[code].label
        return fallback

    def _detect_structure(self, t: float, by: dict[str, dict[str, Any]]) -> None:
        for s in self.sensors:
            if s["kind"] != "structure":
                continue
            b = self.buildings.get(s.get("building_id") or "")
            if b is None:
                continue
            base = self.base_buildings.get(b["id"], b)
            v = by[s["node_id"]]["values"]
            alert_id = f"AL-STR-{b['id']}"
            prev = self.alerts.get(alert_id)
            if prev and prev.get("status") == "resolved":
                continue
            high = v["tilt_deg"] >= 0.8 or v["crack_mm"] >= 1.0
            med = v["tilt_deg"] >= 0.45 or v["crack_mm"] >= 0.55
            scn_t0 = self.cracks.get(b["id"])
            age = (t - scn_t0) / 1000.0 if scn_t0 else 0.0
            cv = scn_t0 is not None and age >= 10
            priority = int(clamp(round(base["priority"] + v["tilt_deg"] * 14 + v["crack_mm"] * 8), 0, 99))
            status = "inspect" if high else "watch" if med else "ok"
            if b["status"] != "fire" and (abs(priority - b["priority"]) >= 2 or status != b["status"]):
                self._patch_building(
                    b["id"],
                    {"priority": priority, "status": status, "tilt_deg": v["tilt_deg"], "crack_mm": v["crack_mm"]},
                )
            if not high and not med:
                continue
            sources = [
                {
                    "kind": "sensor",
                    "label": f"{s['node_id']}: tilt {v['tilt_deg']:.2f}°, crack {v['crack_mm']:.2f} mm",
                    "ts": int(t),
                }
            ]
            if cv:
                sources.append(
                    {"kind": "cv", "label": "Photo analysis: 3 crack candidates, widest 1.4 mm", "ts": int(scn_t0 + 10000)}
                )
            conf = min(0.96, 0.35 + v["tilt_deg"] * 0.35 + v["crack_mm"] * 0.2 + (0.1 if cv else 0.0))
            severity = "high" if high else "medium"
            alert = {
                "id": alert_id,
                "module": "structure",
                "severity": severity,
                "status": prev["status"] if prev and prev.get("severity") == severity else "new",
                "title": f"Tilt and crack growth, {b['id']}" if high else f"Tilt watch, {b['id']}",
                "detail": f"{b['name']}, built {b['year_built']}, {b['construction']}. Simulated deviation, no safety verdict.",
                "building_id": b["id"],
                "pos": b["center"],
                "confidence": round(conf * 100) / 100,
                "sources": sources,
                "created_at": (prev or {}).get("created_at", int(t)),
                "updated_at": int(t),
                "recommendation": "Queue for engineer inspection within 24 h. Demo ranking only."
                if high
                else "Keep on weekly review. Engineer to validate if tilt passes 0.8°.",
            }
            key = f"{severity}|{round(conf * 40)}|{len(sources)}|{alert['status']}"
            self._put_alert(alert, key, alert_id)

    async def _detect_flood(self, t: float, by: dict[str, dict[str, Any]]) -> None:
        zones: list[dict[str, Any]] = []
        for s in self.sensors:
            if s["kind"] != "rain_level":
                continue
            v = by[s["node_id"]]["values"]
            lvl = v["level_cm"]
            if lvl >= 3:
                rx = 14 + lvl * 0.9
                polygon = self._ellipse(s["pos"], rx, 7 + lvl * 0.45, 20)
                zones.append(
                    {
                        "id": f"FZ-{s['node_id']}",
                        "node_id": s["node_id"],
                        "polygon": polygon,
                        "center": s["pos"],
                        "radius_m": rx,
                        "depth_cm": r1(lvl),
                        "label": f"{lvl:.0f} cm",
                    }
                )
            alert_id = f"AL-FLOOD-{s['node_id']}"
            prev = self.alerts.get(alert_id)
            if (prev and prev.get("status") == "resolved") or lvl < 10:
                continue
            high = lvl >= 25
            conf = min(0.95, 0.4 + lvl / 60 + v["rain_mmh"] / 200)
            severity = "high" if high else "medium"
            alert = {
                "id": alert_id,
                "module": "flood",
                "severity": severity,
                "status": prev["status"] if prev and prev.get("severity") == severity else "new",
                "title": f"Waterlogging risk, {s['label']}",
                "detail": f"Water level {lvl:.0f} cm, rainfall {v['rain_mmh']:.0f} mm/h. Simulated rain event.",
                "pos": s["pos"],
                "confidence": round(conf * 100) / 100,
                "sources": [
                    {
                        "kind": "sensor",
                        "label": f"{s['node_id']}: level {lvl:.0f} cm, rain {v['rain_mmh']:.0f} mm/h",
                        "ts": int(t),
                    }
                ],
                "created_at": (prev or {}).get("created_at", int(t)),
                "updated_at": int(t),
                "recommendation": "Avoid this lane for tenders. Pre-position a pump. Simulated scenario."
                if high
                else "Watch level. Check the drain at the nearest junction.",
            }
            key = f"{severity}|{round(lvl / 4)}|{alert['status']}"
            self._put_alert(alert, key, alert_id)
        zk = "|".join(f"{z['node_id']}:{round(z['depth_cm'] / 2)}" for z in zones)
        if zk != self.zone_key:
            self.zone_key = zk
            self.zones = zones
            self.interventions = self._rank_interventions() if zones else []
            app_state.set_flood_zones(
                [
                    {"pos": z["center"], "radius_m": z["radius_m"], "depth_cm": z["depth_cm"]}
                    for z in zones
                ]
            )
            await self.broadcast({"t": "flood", "zones": zones, "interventions": self.interventions})
            for aid in list(self.routes.keys()):
                alert = self.alerts.get(aid)
                b = self.buildings.get((alert or {}).get("building_id") or "")
                hz = self.hazards.get(f"HZ-{b['id']}") if b else None
                if alert and b and hz and hz.get("active", True):
                    await self._plan_fire_routes(aid, b, hz)

    def _ellipse(self, center: list[float], rx: float, ry: float, n: int = 28) -> list[list[float]]:
        pts = []
        for i in range(n):
            a = (i / n) * 2 * math.pi
            pts.append(
                [
                    center[0] + (math.cos(a) * rx) / M_LON,
                    center[1] + (math.sin(a) * ry) / M_LAT,
                ]
            )
        pts.append(list(pts[0]))
        return pts

    def _rank_interventions(self) -> list[dict[str, Any]]:
        defs = [dict(iv) for iv in INTERVENTION_DEFS]
        defs.sort(key=lambda x: x["reduces_pct"] / x["cost_lakh"], reverse=True)
        return [{**iv, "rank": i + 1} for i, iv in enumerate(defs)]
