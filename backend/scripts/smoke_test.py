import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"

PASS = []
FAIL = []

def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name} {detail}")


def main() -> None:
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{BASE}/health")
        check("health", r.status_code == 200 and r.json().get("db") is True, str(r.json())[:80])

        r = c.get(f"{API}/buildings")
        feats = r.json().get("features", [])
        check("buildings geojson (14 demo + 76 osm)", r.status_code == 200 and len(feats) == 90, f"{len(feats)} features")

        b021 = next(f for f in feats if f["properties"]["id"] == "B-021")
        check("building shape", "center" in b021["properties"] and b021["geometry"]["type"] == "Polygon")

        r = c.get(f"{API}/buildings", params={"source": "demo"})
        demo_feats = r.json().get("features", [])
        check("buildings source=demo filter", r.status_code == 200 and len(demo_feats) == 14, f"{len(demo_feats)} features")

        r = c.get(f"{API}/buildings", params={"source": "osm"})
        osm_feats = r.json().get("features", [])
        osm_b = next((f for f in osm_feats if f["properties"]["id"] == "OSM-168164477"), None)
        check(
            "buildings source=osm filter + OSM feature",
            r.status_code == 200
            and len(osm_feats) == 76
            and osm_b is not None
            and osm_b["geometry"]["type"] == "Polygon"
            and osm_b["properties"]["source"] == "osm"
            and osm_b["properties"]["access_node"]
            and osm_b["geometry"]["coordinates"][0][0] == osm_b["geometry"]["coordinates"][0][-1],
            f"{len(osm_feats)} features, closed ring + access_node + source=osm",
        )

        r = c.get(f"{API}/buildings/OSM-168164477")
        check(
            "OSM building detail (unverified attrs)",
            r.status_code == 200
            and r.json()["code"] == "OSM-168164477"
            and r.json()["attributes"]["osm_id"] == "way/168164477"
            and r.json()["attributes"]["osm_tags"].get("name") == "Jammu & Kashmir Legislative Assembly",
        )

        r = c.get(f"{API}/buildings/B-021")
        check("building detail", r.status_code == 200 and r.json()["code"] == "B-021")

        r = c.get(f"{API}/lanes")
        lanes = r.json().get("features", [])
        check("lanes geojson (25 demo + 700 osm)", r.status_code == 200 and len(lanes) == 725, f"{len(lanes)} features")
        check("lane attrs", all(l["properties"].get("width_m") is not None for l in lanes))

        r = c.get(f"{API}/lanes", params={"source": "demo"})
        check("lanes source=demo filter", r.status_code == 200 and len(r.json()["features"]) == 25, f"{len(r.json()['features'])} features")

        r = c.get(f"{API}/lanes", params={"source": "osm"})
        osm_lanes = r.json().get("features", [])
        osm_lane_ok = all(
            l["properties"]["source"] == "osm" and l["properties"]["width_m"] is not None
            for l in osm_lanes
        )
        check(
            "lanes source=osm filter",
            r.status_code == 200 and len(osm_lanes) == 700 and osm_lane_ok,
            f"{len(osm_lanes)} features",
        )

        r = c.get(f"{API}/sensors")
        check("sensors", r.status_code == 200 and len(r.json()) == 14, f"{len(r.json())} sensors")

        r = c.get(f"{API}/readings/latest", params={"building_id": "B-014"})
        check("readings latest empty ok", r.status_code == 200)

        r = c.post(
            f"{API}/readings",
            json={
                "building_id": "B-014",
                "hazard": "fire",
                "values": {"temperature_c": 95, "smoke_level": 88, "smoke_ppm": 880},
                "source": "simulation",
                "simulation": True,
            },
        )
        body = r.json()
        check(
            "manual reading ingest + risk",
            r.status_code == 201 and body.get("risk", {}).get("category") == "critical",
            f"score={body.get('risk', {}).get('score')}",
        )
        incident_id = body.get("incident_id")
        check("incident auto-created", incident_id is not None, str(incident_id))

        r = c.get(f"{API}/incidents", params={"status": "open", "hazard": "fire"})
        open_fire = r.json().get("items", [])
        check("incident listed", any(i["id"] == incident_id for i in open_fire), f"{len(open_fire)} open")

        r = c.patch(f"{API}/incidents/{incident_id}", json={"status": "acknowledged", "note": "smoke test"})
        check("incident ack", r.status_code == 200 and r.json()["status"] == "acknowledged")
        r = c.patch(f"{API}/incidents/{incident_id}", json={"status": "resolved", "note": "done"})
        check("incident resolve", r.status_code == 200 and r.json()["status"] == "resolved")
        r = c.patch(f"{API}/incidents/{incident_id}", json={"status": "acknowledged"})
        check("invalid transition rejected", r.status_code == 400, str(r.status_code))

        r = c.get(f"{API}/incidents/{incident_id}")
        check("incident events audit", r.status_code == 200 and len(r.json()["events"]) >= 3)

        r = c.post(
            f"{API}/simulations",
            json={
                "scenario": "fire",
                "target_building_id": "B-021",
                "severity": "critical",
                "duration_sec": 60,
                "interval_ms": 1000,
                "seed": 42,
            },
        )
        check("simulation created", r.status_code == 201 and r.json()["status"] in ("running", "queued"), json.dumps(r.json())[:120])
        sim_id = r.json()["id"]

        time.sleep(6)
        r = c.get(f"{API}/simulations/{sim_id}")
        check("simulation running", r.json().get("status") == "running", f"elapsed={r.json().get('elapsed_sec')}")

        r = c.get(f"{API}/readings", params={"building_id": "B-021", "limit": 20})
        items = r.json().get("items", [])
        check("simulation readings persisted", len(items) >= 3, f"{len(items)} readings")
        vals = items[0]["values"] if items else {}
        check("reading tagged synthetic", all(it.get("simulation") for it in items) if items else False)
        check("smoke rising", vals.get("smoke_ppm", 0) > 40, f"smoke_ppm={vals.get('smoke_ppm')}")

        print("... waiting 42s for fire risk to reach incident threshold ...")
        time.sleep(42)

        r = c.get(f"{API}/incidents", params={"hazard": "fire", "status": "open"})
        code_match = [i for i in r.json().get("items", []) if i["code"].startswith("AL-FIRE-B-021")]
        check("sim incident opened", len(code_match) == 1, str([i["code"] for i in code_match]))
        check("incident dedupe (one active)", len(code_match) == 1)

        r = c.get(f"{API}/risks", params={"entity_type": "building"})
        risks = r.json().get("items", [])
        check("risk assessments listed", len(risks) >= 1, f"{len(risks)} items")

        r = c.post(
            f"{API}/routes",
            json={
                "origin": {"lat": 32.7270, "lon": 74.8546},
                "destination_building_id": "B-021",
                "responder_type": "fire_vehicle",
            },
        )
        route = r.json()
        check("route computed", r.status_code == 200 and route.get("geometry", {}).get("type") == "LineString", f"dist={route.get('distance_m')}m")
        check("route has warnings", len(route.get("warnings", [])) >= 1, str(route.get("warnings", []))[:80])

        r = c.post(f"{API}/simulations/{sim_id}/stop")
        check("simulation stopped", r.status_code == 200 and r.json()["status"] in ("stopped", "completed"), r.json().get("status", ""))
        n_before = len(c.get(f"{API}/readings", params={"building_id": "B-021", "limit": 500}).json()["items"])
        time.sleep(3)
        n_after = len(c.get(f"{API}/readings", params={"building_id": "B-021", "limit": 500}).json()["items"])
        check("no ticks after stop", n_after == n_before, f"{n_before} -> {n_after}")

        r = c.post(
            f"{API}/simulations",
            json={"scenario": "fire", "target_building_id": "B-021", "severity": "warning", "duration_sec": 30, "interval_ms": 1000},
        )
        check("re-sim allowed after stop", r.status_code == 201, str(r.status_code))
        sim2 = r.json()["id"]
        r = c.post(f"{API}/simulations", json={"scenario": "fire", "target_building_id": "B-021"})
        check("duplicate active sim rejected", r.status_code == 409, str(r.status_code))
        c.post(f"{API}/simulations/{sim2}/stop")

        r = c.get(f"{API}/buildings", params={"bbox": "74.85,32.72,74.87,32.74"})
        check("bbox filter", r.status_code == 200 and len(r.json()["features"]) >= 1)

    asyncio.run(ws_tests())


async def ws_tests() -> None:
    import websockets

    async with websockets.connect("ws://127.0.0.1:8000/ws/live") as ws:

        async def trigger_reading() -> None:
            await asyncio.sleep(0.7)

            def post() -> None:
                with httpx.Client(timeout=10) as c:
                    c.post(
                        f"{API}/readings",
                        json={
                            "building_id": "B-014",
                            "hazard": "fire",
                            "values": {"temperature_c": 95, "smoke_level": 88},
                            "source": "simulation",
                            "simulation": True,
                        },
                    )

            await asyncio.to_thread(post)

        asyncio.create_task(trigger_reading())
        got_reading = got_risk = False
        sample = ""
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=12)
            except asyncio.TimeoutError:
                break
            ev = json.loads(raw)
            sample = raw[:160]
            if ev.get("event") == "reading.updated":
                got_reading = True
            if ev.get("event") == "risk.updated":
                got_risk = True
            if got_reading and got_risk:
                break
        check("ws/live reading.updated", got_reading)
        check("ws/live risk.updated", got_risk)
        print("[INFO] envelope sample:", sample)

    async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
        snap = json.loads(await ws.recv())
        check(
            "ui snapshot keys",
            snap.get("t") == "snapshot"
            and len(snap.get("buildings", [])) == 90
            and len(snap.get("lane_nodes", [])) == 1093
            and len(snap.get("lane_edges", [])) == 725
            and len(snap.get("sensors", [])) == 14,
            f"b={len(snap.get('buildings', []))} n={len(snap.get('lane_nodes', []))}",
        )
        demo_b = next(b for b in snap["buildings"] if b["id"] == "B-021")
        osm_b = next(b for b in snap["buildings"] if b["id"] == "OSM-168164477")
        check(
            "ui building shapes (demo + OSM footprints)",
            all(k in demo_b for k in ("id", "center", "footprint", "priority", "access_node", "status"))
            and all(k in osm_b for k in ("id", "center", "footprint", "access_node", "status"))
            and len(osm_b["footprint"]) >= 4,
        )
        await ws.send(json.dumps({"cmd": "scenario", "name": "crack"}))
        deadline = time.time() + 8
        saw_telemetry = saw_building = False
        while time.time() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            except asyncio.TimeoutError:
                break
            if msg.get("t") == "telemetry" and msg.get("items"):
                saw_telemetry = True
                st = [i for i in msg["items"] if i["kind"] == "structure"]
                if st and st[0]["values"]["tilt_deg"] > 0.1:
                    saw_building = True
            if msg.get("t") == "building":
                saw_building = True
        check("ui telemetry stream", saw_telemetry)
        check("ui structural sim affects sensors", saw_building)
        await ws.send(json.dumps({"cmd": "alert_action", "id": "AL-STR-B-007", "action": "ack"}))

    print(f"\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)


if __name__ == "__main__":
    main()
