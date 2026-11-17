# Old Jammu Risk Intelligence: frontend

React + Vite + TypeScript + Tailwind, Mapbox GL + deck.gl (flat Jammu map), Apache ECharts.

```bash
npm install
npm run dev          # http://localhost:5173, runs on the built-in hardware simulator
npm run sim:check    # headless test of simulator, fusion and routing
npm run build
```

Set `VITE_MAPBOX_ACCESS_TOKEN` in `frontend/.env.local` before starting Vite. The map uses Mapbox Streets and is centered on Jammu city.

## Simulator vs backend

`src/lib/feed.ts` picks the data source.

| `.env` | Source |
|---|---|
| `VITE_WS_URL=` (empty) | `SimFeed`: fake ESP32 nodes, sensor fusion and routing run in the browser |
| `VITE_WS_URL=ws://localhost:8000/ws` | `WsFeed`: a backend implementing the WebSocket contract below |

The UI defaults to the simulator. The repository's current FastAPI backend exposes REST endpoints, not this WebSocket contract, so leave `VITE_WS_URL` empty unless you connect a compatible WebSocket backend.

## Message contract (`src/types.ts`)

Server to client, one JSON object per WebSocket frame:

| `t` | Payload | When |
|---|---|---|
| `snapshot` | buildings, lane_nodes, lane_edges, sensors, alerts, routes, hazards, flood_zones, interventions | on connect and on reset |
| `telemetry` | `items: [{node_id, kind, ts, battery, values}]` | about 1 Hz, one batch for all nodes |
| `alert` | full `Alert`, upserted by `id` | fusion result or status change |
| `routes` | `alert_id`, `routes: Route[]` (empty list clears) | incident confirmed or lanes changed |
| `hazard` | `{id, pos, radius_m, active}` | fire danger zone |
| `building` | `id`, partial `Building` | status, priority, tilt, crack changes |
| `flood` | `zones`, `interventions` | waterlogging update |

Client to server: `{cmd:'scenario', name}` (demo only) and `{cmd:'alert_action', id, action:'ack'|'dispatch'|'resolve'}`.

`values` per sensor kind:
`smoke_temp {smoke_ppm, temp_c}`, `structure {tilt_deg, crack_mm, vib_rms}`, `rain_level {rain_mmh, level_cm}`.

### Hardware path (what the backend does)

```
ESP32 --MQTT--> broker --> FastAPI subscriber --> fusion/AI/routing --> WebSocket --> this UI
   topic: jammu/nodes/<node_id>/telemetry    payload: {"smoke_ppm":310,"temp_c":58,"battery":82,"ts":...}
```

Minimal FastAPI shape:

```python
@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    await sock.send_json({"t": "snapshot", ...})
    async for msg in bus.subscribe():      # Redis pub/sub or asyncio.Queue
        await sock.send_json(msg)          # telemetry, alert, routes, ...
```

## Replacing the demo data

* `src/lib/seed.ts` holds the 14 buildings, the lane graph and the sensor list. Coordinates sit on a local metre grid around Old Jammu and are not surveyed, so they will not line up with real OSM roads. In production, send these in the `snapshot` from PostGIS (JMC GIS, OSM-derived road graph with measured lane widths).
* The map is restricted to the Jammu urban area. Simulator buildings and road networks are illustrative Old Jammu demo data, not surveyed GIS data.
* Routing (`src/lib/routing.ts`) is a reference implementation of the responder rules: tender min lane width 3.5 m and no stairs, medical team 1.2 m and no stairs, pedestrians 0.9 m with stairs. Port the same rules to the backend (pgRouting or NetworkX).

## Layout

```
src/lib/simulator.ts   fake hardware + fusion + decisions (browser-side backend)
src/lib/routing.ts     Dijkstra with per-responder constraints
src/lib/layers.ts      deck.gl layers (buildings, lanes, routes, hazard, flood, sensors)
src/components/        MapView, AlertsPanel, OverviewPanel + cards, BottomNav, SimBar, TopBar
src/store.ts           zustand store, applies ServerMsg
```
