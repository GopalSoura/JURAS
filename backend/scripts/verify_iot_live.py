"""Live end-to-end check for the three Wokwi nodes.

This talks to a running JURAS backend (HTTP + WebSocket) and verifies that the
verified device -> sensor -> target mappings survive the *whole* pipeline:
validation, DB write, risk assessment, `reading.updated` / `risk.updated` bus
events, and the `/ws` dashboard frames (telemetry / risk).

It posts deliberately normal readings, so it does not open incidents or leave
alert state behind. Run it while the backend is up:

    python scripts/verify_iot_live.py
    python scripts/verify_iot_live.py --base-url http://127.0.0.1:8000

Exit code 0 means every check passed. Any failure prints the offending check
and returns 1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx
import websockets

PAYLOADS: list[dict[str, Any]] = [
    {
        "device_id": "JURAS-FIRE-001",
        "sensor_id": "JM-014",
        "building_id": "B-014",
        "hazard": "fire",
        "source": "simulation",
        "simulation": True,
        "values": {
            "smoke_level": 4.0,
            "smoke_ppm": 40.0,
            "temperature_c": 31.8,
            "humidity_pct": 48.0,
            "smoke_raw": 120.0,
            "flame": 0.0,
        },
    },
    {
        "device_id": "JURAS-STRUCT-001",
        "sensor_id": "JM-S07",
        "building_id": "B-007",
        "hazard": "structural",
        "source": "simulation",
        "simulation": True,
        "values": {
            "tilt_deg": 0.05,
            "crack_mm": 0.12,
            "vib_rms": 0.02,
            "deviation_mm": 2.9,
            "mpu_ok": 1.0,
            "crack_ok": 1.0,
        },
    },
    {
        "device_id": "JURAS-STORM-001",
        "sensor_id": "JM-R01",
        "node_code": "I",
        "hazard": "flood",
        "source": "simulation",
        "simulation": True,
        "values": {
            "water_level_cm": 2.0,
            "level_cm": 2.0,
            "distance_cm": 98.0,
            "rain_mmh": 0.0,
            "rain_pct": 0.0,
            "rain_raw": 4095.0,
        },
    },
]

EXPECTED = {
    "JURAS-FIRE-001": {
        "sensor_code": "JM-014",
        "building_code": "B-014",
        "node_code": None,
    },
    "JURAS-STRUCT-001": {
        "sensor_code": "JM-S07",
        "building_code": "B-007",
        "node_code": None,
    },
    "JURAS-STORM-001": {
        "sensor_code": "JM-R01",
        "building_code": None,
        "node_code": "I",
    },
}

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  PASS  {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


async def collect(ws: Any, sink: list[dict[str, Any]]) -> None:
    while True:
        try:
            raw = await ws.recv()
        except Exception:
            return
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if raw in ("pong", "ping"):
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        if isinstance(msg, dict):
            sink.append(msg)


async def main(base_url: str) -> int:
    base = base_url.rstrip("/")
    http_url = f"{base}/api/v1/readings"
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://") :]
    else:
        ws_base = base
    live_msgs: list[dict[str, Any]] = []
    front_msgs: list[dict[str, Any]] = []

    print(f"Connecting to {base} ...")
    async with (
        websockets.connect(f"{ws_base}/ws/live", max_size=None) as live,
        websockets.connect(f"{ws_base}/ws", max_size=None) as front,
    ):
        tasks = [
            asyncio.create_task(collect(live, live_msgs)),
            asyncio.create_task(collect(front, front_msgs)),
        ]
        await asyncio.sleep(1.5)

        print("\nPosting the three Wokwi payloads ...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            for payload in PAYLOADS:
                device = payload["device_id"]
                resp = await client.post(http_url, json=payload)
                check(resp.status_code == 201, f"{device}: HTTP 201 (got {resp.status_code})")
                if resp.status_code != 201:
                    print(f"        body: {resp.text[:500]}")
                    continue
                body = resp.json()
                expected = EXPECTED[device]
                check(body.get("accepted") is True, f"{device}: accepted")
                check(
                    body.get("sensor_code") == expected["sensor_code"],
                    f"{device}: sensor {expected['sensor_code']} "
                    f"(got {body.get('sensor_code')})",
                )
                check(
                    body.get("building_code") == expected["building_code"],
                    f"{device}: building {expected['building_code']} "
                    f"(got {body.get('building_code')})",
                )
                check(
                    body.get("node_code") == expected["node_code"],
                    f"{device}: node {expected['node_code']} "
                    f"(got {body.get('node_code')})",
                )
                check(
                    body.get("source") == "simulation" and body.get("simulation") is True,
                    f"{device}: stored as simulation",
                )
                risk = body.get("risk") or {}
                check(risk.get("score") is not None, f"{device}: risk assessed")
                check(
                    risk.get("device_id") == device,
                    f"{device}: risk carries device_id",
                )
                check(
                    "incident_created" in body and "incident_code" in body,
                    f"{device}: result carries incident linkage fields",
                )

            print("\nChecking invalid payloads are rejected (no writes) ...")
            bad_range = await client.post(
                http_url,
                json={**PAYLOADS[0], "values": {"temperature_c": 500, "smoke_level": 1}},
            )
            check(bad_range.status_code == 422, f"out-of-range payload -> 422 (got {bad_range.status_code})")
            bad_json = await client.post(
                http_url,
                json={**PAYLOADS[0], "values": {"temperature_c": "hot"}},
            )
            check(bad_json.status_code == 422, f"non-numeric payload -> 422 (got {bad_json.status_code})")
            unknown = await client.post(
                http_url,
                json={**PAYLOADS[0], "device_id": "JURAS-UNKNOWN-999"},
            )
            check(unknown.status_code == 404, f"unknown device -> 404 (got {unknown.status_code})")
            wrong_target = await client.post(
                http_url,
                json={**PAYLOADS[0], "building_id": "B-007"},
            )
            check(
                wrong_target.status_code == 400,
                f"wrong target -> 400 (got {wrong_target.status_code})",
            )

            print("\nPosting a partial fire payload (DHT unavailable) ...")
            partial = await client.post(
                http_url,
                json={
                    **PAYLOADS[0],
                    "values": {"smoke_level": 4.0, "smoke_ppm": 40.0, "smoke_raw": 120.0, "flame": 0.0},
                },
            )
            check(partial.status_code == 201, f"partial payload accepted (got {partial.status_code})")
            if partial.status_code == 201:
                pbody = partial.json()
                check(pbody.get("accepted") is True, "partial payload: accepted")
                # The ingest response carries no per-reading `values` blob, so
                # the omission is asserted against the `t: live` WebSocket
                # frame further below (live_values must not contain the keys).

        await asyncio.sleep(4.0)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    print("\nChecking /ws/live bus events ...")
    live_readings = {
        m["data"].get("sensor_code"): m
        for m in live_msgs
        if m.get("event") == "reading.updated" and isinstance(m.get("data"), dict)
    }
    live_risks = {
        m["data"].get("sensor_code"): m
        for m in live_msgs
        if m.get("event") == "risk.updated" and isinstance(m.get("data"), dict)
    }
    for device, expected in EXPECTED.items():
        sensor = expected["sensor_code"]
        check(sensor in live_readings, f"reading.updated for {sensor}")
        check(sensor in live_risks, f"risk.updated for {sensor}")
        if sensor in live_readings:
            event = live_readings[sensor]
            check(
                event.get("simulation") is True and event["data"].get("simulation") is True,
                f"reading.updated {sensor}: simulation envelope + payload",
            )
        if sensor in live_risks:
            event = live_risks[sensor]
            check(
                event.get("simulation") is True and event["data"].get("simulation") is True,
                f"risk.updated {sensor}: simulation envelope + payload",
            )
            check(
                event["data"].get("device_id") == device,
                f"risk.updated {sensor}: device_id {device}",
            )

    print("\nChecking /ws dashboard frames ...")
    snapshot = next((m for m in front_msgs if m.get("t") == "snapshot"), None)
    check(snapshot is not None, "snapshot received")
    if snapshot:
        sensors = {s.get("node_id"): s for s in snapshot.get("sensors", [])}
        for device, expected in EXPECTED.items():
            meta = sensors.get(expected["sensor_code"])
            check(meta is not None, f"snapshot lists {expected['sensor_code']}")
            if meta:
                check(meta.get("device_id") == device, f"snapshot {expected['sensor_code']}: device_id {device}")
                check(meta.get("simulation") is True, f"snapshot {expected['sensor_code']}: simulation=true")
        check("telemetry" in snapshot and "risks" in snapshot, "snapshot includes telemetry + risks")

    live_telemetry = {}
    for m in front_msgs:
        if m.get("t") != "telemetry":
            continue
        for item in m.get("items", []):
            if item.get("live"):
                live_telemetry[item.get("node_id")] = item
    for expected in EXPECTED.values():
        sensor = expected["sensor_code"]
        check(sensor in live_telemetry, f"/ws telemetry live item for {sensor}")
        if sensor in live_telemetry:
            item = live_telemetry[sensor]
            check(item.get("simulation") is True, f"/ws telemetry {sensor}: simulation=true")
            check(
                item.get("device_id") == next(d for d, e in EXPECTED.items() if e is expected),
                f"/ws telemetry {sensor}: device_id",
            )

    # The last fire reading posted was the DHT-less partial payload: the live
    # values must omit the unavailable keys instead of fabricating a zero.
    fire_live = live_telemetry.get("JM-014")
    check(fire_live is not None, "partial payload: live frame received for JM-014")
    if fire_live is not None:
        live_values = fire_live.get("live_values") or {}
        check(
            "temperature_c" not in live_values and "temp_c" not in live_values,
            "partial payload: temperature omitted, not zeroed",
        )
        check(
            "humidity_pct" not in live_values,
            "partial payload: humidity omitted, not zeroed",
        )
        check(
            "smoke_level" in live_values and "flame" in live_values,
            "partial payload: available smoke/flame values still delivered",
        )

    front_risks = {
        m["risk"].get("sensor_code")
        for m in front_msgs
        if m.get("t") == "risk" and isinstance(m.get("risk"), dict)
    }
    for expected in EXPECTED.values():
        check(expected["sensor_code"] in front_risks, f"/ws risk frame for {expected['sensor_code']}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        for item in failures:
            print(f" - {item}")
        return 1
    print("OK: all live ingestion + WebSocket checks passed")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(main(args.base_url)))
    except KeyboardInterrupt:
        sys.exit(130)
