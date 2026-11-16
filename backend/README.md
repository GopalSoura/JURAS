# JURAS Backend

FastAPI + PostgreSQL/PostGIS backend for the JURAS (Jammu Urban Risk Intelligence System) hackathon prototype — Purani Mandi pilot. Implements the full JURAS Backend Engineering Blueprint: GeoJSON data layer, sensor-ingest → risk-scoring → incident pipeline, scenario simulations, route planning, and BOTH WebSocket contracts.

**Frontend contract is preserved exactly.** The UI needs zero code changes — just point it at this backend (see "Connect the frontend" below).

## Stack
- FastAPI, SQLAlchemy 2 (async) + asyncpg, GeoAlchemy2, Alembic, Pydantic v2
- PostgreSQL 17 + PostGIS 3.7 (local now; Supabase later — it is the same Postgres)
- Uvicorn (ASGI), asyncio simulation loop

## Setup (once)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

Create the database (PostgreSQL must be running):

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE juras;"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d juras -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Configure `backend/.env`:

```
DATABASE_URL=postgresql+asyncpg://postgres:juras123@localhost:5432/juras
CORS_ORIGINS=["http://localhost:5173"]
```

## Run

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head      # create tables
.\.venv\Scripts\python.exe scripts\seed_demo_data.py    # demo data (17 nodes / 25 lanes / 14 buildings / 14 sensors)
.\.venv\Scripts\python.exe scripts\import_osm_geojson.py  # OSM import: 76 buildings + 521 lanes + 789 shared nodes
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## OSM data import (`scripts/import_osm_geojson.py`)

Imports the cleaned OpenStreetMap datasets shipped in `backend/` (`buildings.geojson`: 76 building polygons; `roads_lanes.geojson`: 521 road/way lines, wider Jammu area — NOT a verified Purani Mandi survey) into the existing PostGIS tables, alongside — never replacing — the synthetic demo rows:

- Demo rows keep their codes (`B-0xx`, `A-B`, `A..Q`); OSM rows use `OSM-<way id>` buildings/lanes and `OSMN-<n>` lane nodes, so demo and OSM never collide. Shared OSM endpoints are deduplicated into shared nodes (789 nodes from 1042 way endpoints; 169 junctions connect ≥ 2 ways).
- Every OSM row carries `attributes.source = "osm"` (normalized from variants such as `os m`) plus the verbatim original OSM tags under `attributes.osm_tags` (incl. imagery provenance like `maxar`/`bing`).
- Nothing is fabricated: the dataset has no `addr:*` tags so no addresses are written; lane widths use conservative highway-class defaults (or OSM `lanes` tag × 3 m) and are flagged `width_verified: false` with the basis recorded; unknown building year → `year_built = 0`, no construction/occupancy claims.
- Each OSM building's `access_node` is its nearest imported real road node (distance recorded in attributes); geometry is cleaned (rings closed, consecutive duplicates removed) and re-validated with `ST_IsValid`/`ST_MakeValid` after insert.
- Idempotent: re-running refreshes `OSM-*` rows in place. `seed_demo_data.py` wipes all tables — re-run the import after re-seeding.
- API: `GET /buildings` and `GET /lanes` accept `?source=demo|osm` to filter by provenance (default: all). OSM features are labeled `OpenStreetMap import, geometry not field-verified`.

The `/ws` frontend adapter loads all buildings/lanes, so the MapLibre/deck.gl map automatically renders the 76 real OSM footprints (it already draws `footprint` polygons via its existing `PolygonLayer` contract) next to the 14 synthetic demo blocks. Routes/simulations/incidents keep operating on the demo grid; REST routing treats the OSM network as a separate (disconnected) graph component.

- REST docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Blueprint WS: `ws://localhost:8000/ws/live`
- Frontend contract WS: `ws://localhost:8000/ws`

## Connect the frontend (no code change)

Create `frontend/.env.local`:

```
VITE_WS_URL=ws://localhost:8000/ws
```

The `/ws` adapter implements the full frontend SimFeed contract: snapshot, 1 Hz telemetry, alert fusion, hazard zones, route planning, flood zones, and `scenario`/`alert_action` client commands.

## Verify

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py    # 41/41 end-to-end checks (server must be running)
.\.venv\Scripts\python.exe -m pytest -q             # 54/54 unit + integration tests (incl. OSM import pipeline)
```

## REST API (prefix `/api/v1`)

| Endpoint | Notes |
|---|---|
| `GET /health` | `{status, db, project}` |
| `GET /buildings` · `GET /buildings/{code}` | GeoJSON FeatureCollection / detail; `?bbox=`, `?source=demo\|osm` |
| `GET /lanes` · `GET /lanes/nodes` | GeoJSON lane network; `?source=demo\|osm`, `?blocked=`, `?accessible_to=` |
| `GET /sensors` | sensor registry |
| `POST /readings` (201) · `GET /readings/latest` | ingest → risk → auto-incident → WS events |
| `POST /simulations` · `GET /simulations[/{id}]` · `POST /simulations/{id}/stop` | fire/flood/structural scenarios; one active per target+scenario (409 on duplicate) |
| `GET /risks` | latest risk assessments |
| `GET /incidents[?status=]` · `GET /incidents/{id}` · `PATCH /incidents/{id}` · `GET /incidents/{id}/events` | lifecycle open → acknowledged → resolved/false_alarm (resolved is terminal) |
| `POST /routes` | dijkstra route with responder profile (fire_vehicle/ambulance/evacuation) |

Flood simulations require `target_node_code` (e.g. `"I"` — sensor JM-R01, flood_factor 1.0). Fire incidents auto-open when risk score ≥ 65.

## Switch to Supabase later

Supabase IS PostgreSQL — the architecture does not change. Create a Supabase project, enable PostGIS, run the same Alembic migration, and only replace `DATABASE_URL` in `backend/.env` with the Supabase session-pooler connection string. Firebase is reserved for a future FCM push-notification layer.

## Layout

```
backend/
├── app/
│   ├── core/          # config, constants, exceptions, logging
│   ├── db/            # engine, session, base
│   ├── models/        # 9 SQLAlchemy models (PostGIS geometry)
│   ├── schemas/       # pydantic v2 request/response
│   ├── repositories/  # DB access
│   ├── services/      # reading, incident, gis, routing, osm_import services
│   ├── risk/          # thresholds + rules (frontend-store port)
│   ├── simulation/    # scenario models + asyncio manager
│   ├── routing/       # graph + dijkstra (frontend-routing port)
│   ├── realtime/      # event envelope + bus
│   ├── api/v1/        # REST endpoints
│   └── ws/            # /ws/live (blueprint) + /ws (frontend adapter)
├── alembic/           # migrations (0001_initial applied)
├── scripts/           # seed_demo_data.py, import_osm_geojson.py, smoke_test.py
├── buildings.geojson  # OSM building polygons (76) — import source
├── roads_lanes.geojson # OSM road ways (521) — import source
└── tests/             # unit/ + integration/ (juras_test DB)
```

See `../graph.md` for the full work graph — a machine-readable map of what was built and why.
