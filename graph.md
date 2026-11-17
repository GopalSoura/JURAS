# JURAS Backend â€” Work Graph (3D)

> **Purpose:** Machine-readable + human-readable record of ALL backend work done in this repo.
> Any AI agent (or human) reading this file can reconstruct the full state and resume without re-exploring.
>
> **How to read the 3 axes:**
> - **Z-axis (depth)** = Layer stack `L0..L6` â€” infrastructure â†’ verification.
> - **X-axis (breadth)** = Nodes inside each layer (components/files).
> - **Y-axis (status)** = `DONE` / `DONE` / `DONE` per node.
> - Edges (`-->`) = build/dependency order (an edge means: source was needed to build target).

---

## 1. ROOT CONTEXT (the "origin node")

| Field | Value |
|---|---|
| Project | JURAS â€” Jammu Urban Risk Intelligence System (Purani Mandi, Jammu) |
| Objective | Full backend + real OSM emergency navigation; the original backend-only scope was extended by an explicitly authorized frontend navigation session |
| Repo | `C:\Users\dassg\Downloads\JURAS_MVP_Starter` |
| Hard constraint | **`frontend/` is READ-ONLY â€” never modify anything inside it** |
| Frontend authorization | `frontend/` was READ-ONLY for original backend work, but the user explicitly authorized the UI redesign and the real navigation UI; the latest instruction wins for those files |
| Navigation constraint | Real imported OSM only; no synthetic demo-grid navigation; no invented connectivity or ETA; legacy `/routes` and WebSocket contracts preserved |
| DB decision | Local PostgreSQL 17 + PostGIS 3.7 NOW â†’ **Supabase later** (Supabase IS PostgreSQL; only `DATABASE_URL` in `backend/.env` changes) |
| Firebase | **KEPT** for a future FCM push-notification layer; out of MVP scope |
| WS contracts | BOTH must work: `/ws/live` (blueprint envelope) and `/ws` (frontend contract adapter) |
| Source of truth | Blueprint docx + `frontend/src/*` contract files (types.ts, seed.ts, feed.ts, store.ts, config.ts, geo.ts, simulator.ts, routing.ts) |

```
ROOT â”€â”€> L0 INFRA â”€â”€> L1 CONFIG â”€â”€> L2 DATA â”€â”€> L3 DOMAIN â”€â”€> â”¬â”€> L4 REST API â”€â”€â”¬â”€> L6 VERIFY
                                                            â””â”€> L5 REALTIME â”€â”€â”˜
```

---

## 2. LAYER STACK (Z-axis, ASCII 3D view)

```
 z=6  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L6 VERIFY      smoke_test.py (36/36 PASS) Â· tests/unit Â· tests/integ â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 z=5  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L5 REALTIME    realtime/events+bus Â· ws/ws_routes (/ws/live) Â·     â”‚
      â”‚                ws/frontend_adapter (/ws SimFeed port)              â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 z=4  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L4 REST        main.py (lifespan/CORS/errors) Â· api/deps Â·          â”‚
      â”‚                api/v1/router Â· 9 endpoint files Â· state.py          â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 z=3  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L3 DOMAIN      risk/rules Â· simulation/{models,manager} Â·           â”‚
      â”‚                routing/{graph,algorithms} Â· services (4) Â· repos (7)â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 z=2  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L2 DATA        db/{base,session} Â· models (9) Â· schemas (9) Â·       â”‚
      â”‚                alembic 0001_initial (migrated) Â· seed_demo_data.py  â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 z=1  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L1 CONFIG      .env + .env.example Â· requirements.txt Â· core/* Â·    â”‚
      â”‚                pytest.ini                                           â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
 z=0  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ L0 INFRA       PostgreSQL 17 (port 5432, pw=juras123) Â· PostGIS 3.7 â”‚
      â”‚                Â· DB juras + juras_test (postgis ext) Â· Python 3.14  â”‚
      â”‚                  venv backend/.venv                                 â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## 3. NODE REGISTRY (X-axis per layer, with status Y-axis)

### L0 â€” Infrastructure â€” ALL `DONE`
| ID | Node | Detail |
|---|---|---|
| N0.1 | PostgreSQL 17 | `winget install PostgreSQL.PostgreSQL.17`; port 5432; user `postgres`; password `juras123` |
| N0.2 | PostGIS 3.7 | silent bundle install; UAC click needed |
| N0.3 | DB `juras` | `CREATE DATABASE juras; CREATE EXTENSION postgis;` â€” verified `postgis_version()` |
| N0.4 | DB `juras_test` | same, for pytest suite |
| N0.5 | Python venv | `backend/.venv` (Python 3.14); deps: sqlalchemy 2.1.8, asyncpg 0.32.0, geoalchemy2 0.21.0, alembic 1.20.1, greenlet 3.5.6, pytest 9.2.0, pytest-asyncio 1.5.0, httpx 0.28.1 |

### L1 â€” Config & Core â€” ALL `DONE`
| ID | Node | Path |
|---|---|---|
| N1.1 | Env files | `backend/.env`, `backend/.env.example` â€” `DATABASE_URL=postgresql+asyncpg://postgres:juras123@localhost:5432/juras` |
| N1.2 | Frozen deps | `backend/requirements.txt` |
| N1.3 | Core modules | `backend/app/core/{config,constants,exceptions,logging}.py` (RULE_VERSION=`demo-v1`) |
| N1.4 | Pytest config | `backend/pytest.ini` (asyncio_mode=auto, testpaths=tests) |

### L2 â€” Data & Schema â€” ALL `DONE`
| ID | Node | Path |
|---|---|---|
| N2.1 | DB base | `backend/app/db/{base,session}.py` |
| N2.2 | Models (9) | `backend/app/models/{building,lane,lane_node,sensor,reading,simulation,risk_assessment,incident,incident_event}.py` (PostGIS Geometry + gist indexes) |
| N2.3 | Schemas (9) | `backend/app/schemas/*.py` (pydantic v2, snake_case in/out) |
| N2.4 | Alembic migration | `backend/alembic/versions/0001_initial.py` + async `env.py` â€” **applied** to `juras` |
| N2.5 | Demo seeder | `backend/scripts/seed_demo_data.py` â€” idempotent; ports frontend `seed.ts`: 17 lane nodes (A..Q), 25 lanes, 14 buildings (B-007..B-109), 14 sensors (7 smoke_temp / 4 structure / 3 rain_level: JM-R01@I f=1.0, JM-R02@O f=0.6, JM-R03@M f=0.8) + 3 demo incidents (AL-STR-B-007 acknowledged, AL-RES-1/2 resolved) |
| N2.6 | OSM import pipeline | `backend/app/services/osm_import_service.py` + CLI `backend/scripts/import_osm_geojson.py` â€” **imported** into `juras`: 76 OSM building polygons (codes `OSM-<way id>`) + 521 road ways as lanes (`OSM-<way id>`) + 789 deduplicated endpoint lane nodes (`OSMN-<n>`, 169 junctions shared by â‰¥2 ways). Idempotent (re-run = in-place update, 0 creates). Datasets: `backend/buildings.geojson`, `backend/roads_lanes.geojson` (wider Jammu, lon 74.8575â€“74.9078, lat 32.7156â€“32.7496 â€” **NOT a verified Purani Mandi survey**). Every OSM row: `attributes.source="osm"` (normalized from `os m` variants), verbatim OSM tags under `attributes.osm_tags` (imagery provenance maxar/bing preserved), `demo=False`, `verified=False`. No addresses fabricated (dataset has zero `addr:*` tags). Lane widths = conservative class defaults or OSM `lanes`Ã—3m, flagged `width_verified=False` + `width_source` basis. Building year unknown â†’ `year_built=0`. Access node = nearest real imported road node (distance recorded). Rings closed + deduped; `ST_IsValid`/`ST_MakeValid` post-fix; SRID 4326; 0 invalid geometries. Demo rows untouched (separate code namespaces). |

### L3 â€” Domain Logic â€” ALL `DONE`
| ID | Node | Path | Notes |
|---|---|---|---|
| N3.1 | Risk rules | `backend/app/risk/{thresholds,rules}.py` | evaluate_fire / flood / structural â†’ score+category+reasons; ports frontend store.ts thresholds |
| N3.2 | Scenario models | `backend/app/simulation/{base,models}.py` | FireModel / FloodModel / StructuralModel; seeded & deterministic; severity rates (critical 1.6 / high 1.2 / normal 1.0) |
| N3.3 | Sim manager | `backend/app/simulation/manager.py` | asyncio tick loop; caps: max 3 active, â‰¥500ms interval, â‰¤300s duration; one active per target+scenario (409); seed masking int32 |
| N3.4 | Routing engine | `backend/app/routing/{graph,algorithms}.py` | Dijkstra; arc filters: stairs blocked for vehicles, width â‰¥ profile min, deep-flood block; hazard multiplier; ports frontend `routing.ts` exactly |
| N3.5 | Services | `backend/app/services/{reading,incident,gis,routing}_service.py` | ingest pipeline (readingâ†’riskâ†’incidentâ†’events list); incident transitions openâ†’acknowledgedâ†’resolved/false_alarm (resolved terminal); route planning 3 profiles |
| N3.6 | Repositories (7) | `backend/app/repositories/*.py` | building, lane, lane_node, sensor, reading, simulation, risk, incident, incident_event; `list_buildings`/`list_lanes` accept `source` filter (`coalesce(attributes->>'source','demo')`); features carry per-feature `source` + provenance label |
| N3.7 | Real OSM navigation graph | `backend/app/routing/osm_graph.py` | DONE - builds routable graph from `lanes.path` (`source=osm`), splits at shared OSM vertices only, honours one-way/roundabout/access/maxwidth/maxheight/stairs/blocked, weak components, 500 m snapping, best snap-pair selection (non-zero route preferred), A* with time/distance weighting, hazard/flood penalties, access/egress walking connectors, turn-by-turn RouteStep list, full LineString geometry |
| N3.8 | Navigation service | `backend/app/services/navigation_service.py` | DONE - loads only OSM lanes, maps DB rows to graph inputs, converts `NavigationError` to existing `AppError` contract, injects live `app_state.routing_ctx()` hazard/flood data (`avoid_hazards`), returns GeoJSON Feature + snaps + connector totals + turn-by-turn steps + warnings |

### L4 â€” REST API â€” ALL `DONE`
| ID | Node | Path | Notes |
|---|---|---|---|
| N4.1 | App factory | `backend/app/main.py` | lifespan (manager+world+bus), CORS for `http://localhost:5173`, error handlers (`error.code/message` contract), `/health` at root + `/api/v1` |
| N4.2 | Deps/state | `backend/app/api/deps.py`, `backend/app/state.py` | runtime singletons set in lifespan |
| N4.3 | Endpoints (9) | `backend/app/api/v1/endpoints/{health,buildings,lanes,sensors,readings,simulations,risks,incidents,routes}.py` | GET/POST/PATCH per blueprint; `/buildings` + `/lanes` + `/lanes/nodes` accept optional `?source=demo|osm` (default: all) |
| N4.4 | Navigation endpoint | `POST /api/v1/routes/navigate` in `backend/app/api/v1/endpoints/routes.py` | DONE - exact origin/destination/profile request; GeoJSON LineString route, distance, model ETA, snap metadata, warnings; legacy `POST /routes` unchanged |

### L5 â€” Realtime / WebSocket â€” ALL `DONE`
| ID | Node | Path | Notes |
|---|---|---|---|
| N5.1 | Event bus | `backend/app/realtime/{events,bus}.py` | envelope `{event_id, event, version, occurred_at, simulation, data}`; events: simulation.started, reading.updated, risk.updated, incident.created, incident.updated, simulation.completed, simulation.failed |
| N5.2 | `/ws/live` | `backend/app/ws/ws_routes.py` | blueprint contract; post-commit broadcast pattern (db commit first, then events list) |
| N5.3 | `/ws` adapter | `backend/app/ws/frontend_adapter.py` | **Full port of frontend `SimFeed`**: snapshot/telemetry(1Hz)/alert fusion (citizen@14s, camera@22s)/hazard zones radius `min(42, 18+age*0.35)`/route planning (3 profiles, POSTS={fire:'A', medical:'E', assemblies:['G','Q']})/building patches/flood zones+ranked interventions; cmds: `{cmd:'scenario',name:'fire'|'crack'|'flood'|'reset'}`, `{cmd:'alert_action',id,action:'ack'|'dispatch'|'resolve'}` |

### L6 â€” Verification â€” ALL `DONE`
| ID | Node | Status | Result |
|---|---|---|---|
| N6.1 | Smoke test | `DONE` | `backend/scripts/smoke_test.py` â†’ **41 passed, 0 failed** (REST 31 incl. OSM source filters + /ws/live 2 + /ws UI 4 + misc) |
| N6.2 | Unit tests | `DONE` | `backend/tests/unit/{test_risk_rules,test_scenario_models,test_incident_transitions,test_routing,test_osm_import_helpers}.py` â€” pytest **54/54 total** |
| N6.3 | Integration tests | `DONE` | `backend/tests/integration/{test_ingest_pipeline,test_api_endpoints,test_osm_import}.py` + `tests/conftest.py` (juras_test engine, `get_session` dependency override, `seeded_world` fixture) |
| N6.5 | Navigation verification | `backend/tests/unit/test_osm_navigation.py`, `backend/tests/integration/test_navigation_api.py`, `frontend/scripts/nav-check.ts` | DONE - 19 graph unit tests + 6 REST integration tests; pytest total 79 passed; live uvicorn POST + CORS preflight verified; frontend build/sim/nav checks pass |
| N6.4 | README update | `DONE` | `backend/README.md`: setup, run, frontend connect (`VITE_WS_URL=ws://localhost:8000/ws`, NO code change), Supabase swap note |

**Test-run command:** `cd backend; .\.venv\Scripts\python.exe -m pytest -q` â†’ `79 passed`

---

## 4. EDGE LIST (dependencies / build order)

```
N0.1 --> N0.3 --> N2.4 --> N2.5
N0.5 --> L1 (all) --> L2 (all) --> L3 (all) --> L4 (all)
                                  L3 (all) --> L5 (all)
N0.3 --> N0.4 --> N6.3
N2.5 --> N6.1
L4 + L5 --> N6.1
N1.4 + N0.4 --> N6.2, N6.3
N6.1 + N6.3 --> N6.4 (README documents verified behavior)
```

## 5. MERMAID DEPENDENCY GRAPH (renders in GitHub/VS Code)

```mermaid
graph TB
    subgraph "L0 INFRA"
        PG["PostgreSQL 17<br/>port 5432, pw juras123"]
        GIS["PostGIS 3.7"]
        VENV["backend/.venv<br/>Python 3.14"]
    end
    subgraph "L1 CONFIG"
        ENV[".env DATABASE_URL"]
        CORE["core/* constants+config"]
    end
    subgraph "L2 DATA"
        MODELS["9 SQLAlchemy models<br/>+ alembic 0001 (applied)"]
        SEED["seed_demo_data.py<br/>17n/25l/14b/14s"]
    end
    subgraph "L3 DOMAIN"
        RISK["risk/rules"]
        SIM["simulation manager<br/>fire/flood/structural"]
        ROUTE["routing dijkstra<br/>3 responder profiles"]
        SVC["reading+incident services"]
    end
    subgraph "L4 REST"
        MAIN["main.py lifespan+CORS"]
        API["/api/v1/* 9 endpoints"]
    end
    subgraph "L5 REALTIME"
        BUS["realtime/event_bus"]
        WSLIVE["/ws/live envelope"]
        WSUI["/ws SimFeed adapter"]
    end
    subgraph "L6 VERIFY"
        SMOKE["smoke_test.py<br/>36/36 PASS"]
        PYTEST["tests/unit + integration<br/>written, pending run"]
    end
    PG --> GIS
    PG --> ENV
    VENV --> ENV
    ENV --> MODELS
    CORE --> MODELS
    MODELS --> SEED
    MODELS --> RISK
    MODELS --> SIM
    MODELS --> ROUTE
    RISK --> SVC
    SIM --> SVC
    SVC --> API
    ROUTE --> API
    SVC --> BUS
    SIM --> BUS
    BUS --> WSLIVE
    BUS --> WSUI
    API --> SMOKE
    WSLIVE --> SMOKE
    WSUI --> SMOKE
    SEED --> SMOKE
    PYTEST -.->|"pending"| SMOKE
```

---

## 6. VERIFICATION RESULTS (what is PROVEN working)

### Smoke test â€” `backend/scripts/smoke_test.py` â†’ 41/41 PASS (last run 2026-11-15, with OSM data loaded)
Full chain verified against real DB + live uvicorn:
1. `/health` healthy, db=True
2. Buildings GeoJSON: 90 features = 14 demo + 76 OSM (`?source=demo|osm` filters verified; OSM feature: closed ring, source=osm, access_node set); building detail with `access_node` (demo + OSM incl. raw `osm_tags`)
3. Lanes GeoJSON: 546 = 25 demo + 521 OSM (all `width_m` present, OSM `source=osm`); sensors: 14
4. Manual reading ingest â†’ risk **score=90 critical** â†’ incident **auto-created**
5. Incident lifecycle: list open â†’ ack â†’ resolve â†’ invalid transition â†’ **400** â†’ audit events
6. Fire sim on B-021 â†’ 5 persisted readings (simulation=true) â†’ smoke rising to 149 ppm
7. After ~42s: fire incident opens (AL-FIRE-B-021) â†’ **dedupe** (one active per building+hazard)
8. Risk assessments listed; route computed 400m **with warnings** (illustrative geometry, blocked access)
9. Sim stop â†’ no ticks after stop â†’ re-sim allowed (201) â†’ duplicate active sim â†’ **409**
10. Bbox filter works
11. `/ws/live`: `reading.updated` + `risk.updated` envelopes received
12. `/ws` (frontend adapter): snapshot keys b=90 n=806 e=546; demo + OSM building shapes with real footprints; telemetry stream; structural sim affects sensors
13. API GeoJSON sweep: 76 OSM building polygons + 521 lane linestrings + 789 node points all valid coords/ranges (lon 74.80â€“74.95, lat 32.70â€“32.76); `accessible_to=fire_vehicle` returns 516 OSM lanes; OSM buildings bbox filter returns 6 in a 200 m window (0 demo there â€” real geometry spatially distinct from synthetic)

### Pytest suite â€” `backend/tests/` â†’ **54 passed** (unit + integration)
- Unit: risk rule bands & bounds, scenario determinism/severity/finish, incident transition matrix, routing filters (stairs/width/flood/hazard/disconnect/path-chain), OSM import helpers (source normalization `os m`â†’`osm`, ring/linestring cleaning, centroid, class width table, tag preservation, no-address guarantee)
- Integration (juras_test DB): ingest pipeline persistence + dedupe + reopen-after-resolve, API endpoints (health/geojson/detail/201 readings/incident patch+events/route 200 + 404), OSM import pipeline (create + node dedupe + shared-endpoint connectivity + source normalization + idempotent re-import 0 creates)
- **Real bug caught & fixed during earlier testing:** `main.py` registered the `RequestValidationError` handler as a lambda returning an un-awaited coroutine (`TypeError: 'coroutine' object is not callable`); replaced with a proper `async def validation_error_handler`.
- Test infrastructure notes (for future agents): session-scoped engine requires `asyncio_default_fixture_loop_scope = session` + `asyncio_default_test_loop_scope = session` in pytest.ini; REST tests override the `get_session` dependency AND monkeypatch `SessionFactory` in endpoint modules that import it directly (readings, incidents); `async_sessionmaker` has no `close_all()`.

---

## 7. ENVIRONMENT FACTS & GOTCHAS (critical for any agent resuming)

1. **Child processes die** when a bash-tool session ends â†’ run server+test in ONE command:
   ```powershell
   $p = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--port","8000" -WindowStyle Hidden -PassThru; Start-Sleep 6; & ".\.venv\Scripts\python.exe" scripts\smoke_test.py; Stop-Process -Id $p.Id -Force
   ```
2. **Inline multi-line `python -c` with quotes hangs PowerShell** â†’ write temp `.py` files instead (temp dir: `C:\Users\dassg\AppData\Local\Temp\opencode`).
3. **Zombie uvicorn on port 8000** causes phantom 500s â†’ kill via:
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "uvicorn" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
   ```
4. PostGIS bundle installer shows UAC prompts â†’ user must click Yes manually.
5. Seed int32 overflow fixed with `& 0x7FFFFFFF`; `Incident.geom` NOT NULL needs `func.ST_GeomFromText` in incident_service.
6. `/ws` adapter is a SimFeed **port** â€” frontend only needs `VITE_WS_URL=ws://localhost:8000/ws` in `frontend/.env.local` (frontend code untouched).

---

## 8. FRONTIER (final state â€” nothing pending)

```
DONE:    N6.1 smoke 41/41 Â· N6.2+N6.3 pytest 79/79 Â· N6.4 backend/README.md
         N2.6 OSM import pipeline (76 buildings + 521 lanes + 789 nodes, idempotent, source=osm, unverified-width flags)
         N3.6/N4.3 source filters + provenance labels in GIS APIs
BUG FOUND BY TESTS (fixed): main.py RequestValidationError handler was a lambda
         returning an un-awaited coroutine â†’ replaced with async validation_error_handler
LATER:   Supabase (user creates project â†’ swap DATABASE_URL only)
LATER:   Firebase FCM push layer (kept, out of MVP)
NOT CLAIMED: Purani Mandi coverage â€” OSM dataset is wider Jammu (lon 74.857â€“74.908, lat 32.716â€“32.750);
         no field survey verification exists. OSM geometry is labeled unverified everywhere.
KNOWN LIMIT: frontend LaneEdge contract (id/a/b/width/stairs only) draws OSM roads as straight
         endpoint-to-endpoint segments; full LineString shapes available via REST /lanes GeoJSON.
         Building footprints DO render as true polygons (existing PolygonLayer contract).
NOTE:    seed_demo_data.py wipes all tables â†’ re-run scripts/import_osm_geojson.py after re-seeding.
```

---

## 10. UI REDESIGN SESSION â€” Premium Smart City EOC (COMPLETE, 2026-11-15)

> Frontend modification authorization granted (frontend/ was READ-ONLY for backend work; UI redesign is now permitted).
> Rules: keep architecture (Zustand store, feed contract, deck.gl layers, component tree), no rewrites, no backend changes unless a real compatibility break appears, preserve all features + real GIS geometry.

### N-U1 Frontend audit â€” `DONE`
| Area | Finding |
|---|---|
| Architecture | React 18 + Vite + Tailwind 3; Zustand store (`src/store.ts`); feed = `WsFeed` (backend `/ws`) or `SimFeed` (browser sim) via `lib/feed.ts`; deck.gl layers built per-frame in `lib/layers.ts` on MapLibre via `MapboxOverlay`; echarts for charts; components: TopBar / AlertsPanel / OverviewPanel(cards) / MapView / SimBar / BottomNav / Bottom tabs (mobile) |
| Contracts intact | `types.ts` ServerMsg/ClientCmd unchanged by design; store `apply()` handles snapshot/telemetry/building/alert/routes/hazard/flood â€” must not be touched |
| Data note | Backend now serves 90 buildings (14 demo + 76 OSM) â€” current copy "of 14 passports" in Kpis is stale â†’ make count-derived |
| Tooltip bug | `tooltipFor` shows "built 0" for OSM buildings (year_built=0 = unknown sentinel) â†’ suppress when 0, hide empty construction |

### N-U2 Cartoonish-element register (what creates the toy look) â€” `DONE`
1. `cards.tsx Kpis` â€” candy gradient tiles (blue/green/amber `linear-gradient(135deg,...)` backgrounds + colored borders)
2. `cards.tsx RoutesCard` â€” filled colored circles with bold F/M/E letters ("arcade badges")
3. `AlertsPanel` â€” 64px SVG ring gauge + 40px count â€” toy dashboard proportions
4. `BottomNav` â€” `rounded-xl` floating pill + neon glow `box-shadow` on active item
5. `index.css` `.mk-incident` â€” glow box-shadows (`0 0 18px rgba(255,77,94,.45)`), `.panel` gradient background, Chakra Petch sci-fi display font, blink glow
6. `lib/layers.ts` â€” fast pulsing hazard rings (radius `1+0.04*pulse` at t/80 triggers), saturated building fills, oversized 9px posts, bright route trails
7. `TopBar` â€” rounded logo plate, oversized title, glowing incident button style

### N-U3 Redesign implementation â€” `DONE`
- [x] N-U3.1 `index.css` â€” flat enterprise tokens: solid surfaces (no panel gradient), hairline borders, 2â€“3px radii, no glow shadows, flat map markers, thin scrollbars, label style on IBM Plex Sans (Chakra Petch dropped)
- [x] N-U3.2 `tailwind.config.js` + `index.html` â€” font-display â†’ IBM Plex Sans (600) with tracking; drop Chakra Petch load; title â†’ "JURAS â€” Emergency Operations Center"
- [x] N-U3.3 `lib/meta.ts` + `Chart.tsx` â€” muted ops palette (desaturated red/orange/amber/blue/green), rgb arrays kept in sync for deck.gl
- [x] N-U3.4 `TopBar.tsx` â€” 44px flat command bar: minimal geometric mark, ops-center title, compact incident ticker (no glow), flat status + clock chips
- [x] N-U3.5 `AlertsPanel.tsx` â€” compact incident console: small count + thin severity distribution bar (ring gauge removed), list rows with left severity strip, flat selection, unchanged ack/dispatch/resolve actions
- [x] N-U3.6 `cards.tsx` â€” Section flat card; Kpis â†’ flat stat blocks (hairline dividers, accent dot, no gradients, dynamic building count); RoutesCard â†’ flat rows with icon + hairline progress; SafetyCard compact score; BuildingCard flat passport with "â€”" for unknown year/construction (OSM-safe); StormCard/FeedCard flat + muted chart colors
- [x] N-U3.7 `BottomNav.tsx` â€” flat segmented control (no glow, small radius), kept as module switcher
- [x] N-U3.8 `SimBar.tsx` â€” flat "Scenario injection" strip (kept 4 commands + hint)
- [x] N-U3.9 `MapView.tsx` â€” flat square map controls, flat layer menu, flat legend; unchanged layers/picking/3D toggle
- [x] N-U3.10 `lib/layers.ts` â€” restrained visuals: calmer muted building fills (OSM blocks dimmer than demo passports), thinner lanes, smaller sensors/posts, slow subtle hazard pulse (no neon ring cycle), dimmer route trails, unchanged layer ids/picking/tooltip keys
- [x] N-U3.11 `App.tsx` â€” desktop grid 336px/1fr/360px, mobile tabs flat (function unchanged)

### N-U4 Verification â€” `DONE`
- [x] `npm run build` (tsc + vite) PASS
- [x] `npm run sim:check` (headless simulator/fusion/routing) ALL CHECKS PASSED
- [x] Backend up + `/ws` contract re-verified: smoke_test.py 41/41 PASS
- [x] `npm run nav:check` PASS
- [x] graph.md final status update

```
STATUS: N-U1 done Â· N-U2 done Â· N-U3 done Â· N-U4 done + NAV done
```

### Resume commands (from `backend/`)
```powershell
# 1. Run pytest suite  â†’ 54 passed
.\.venv\Scripts\python.exe -m pytest -q

# 2. Fresh DB state (demo data) â€” then re-import OSM
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
.\.venv\Scripts\python.exe scripts\import_osm_geojson.py

# 3. Start server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 4. Full smoke test (server must be running)  â†’ 41 passed
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

---

## 9. CONTRACT QUICK-REFERENCE (for agents wiring things up)

**REST (prefix `/api/v1`):** `/health` Â· `/buildings[?bbox=][?source=demo|osm]` Â· `/buildings/{code}` Â· `/lanes[?source=][?blocked=][?accessible_to=]` Â· `/lanes/nodes[?source=]` Â· `/sensors` Â· `/readings` (GET list, POST 201 ingest) Â· `/readings/latest` Â· `/simulations` (POST 201 / GET / GET {id} / POST {id}/stop) Â· `/risks` Â· `/incidents` (GET list+geojson, GET {id}, PATCH {id}, GET {id}/events) Â· `/routes` (POST plan); `/routes/navigate` (POST real OSM emergency route)

**`/ws/live`** (blueprint): server pushes envelope events; client receives only.
**`/ws`** (frontend contract): server â†’ `snapshot|telemetry|alert|routes|hazard|building|flood`; client â†’ `{cmd:'scenario'|'alert_action'}`.
**Flood sim** requires `target_node_code` (e.g. `"I"` â€” sensor JM-R01, flood_factor 1.0).
**Fire incident opens** when risk score â‰¥ 65 (high band); critical severity reaches it in ~25â€“40s.

## 11. REAL OSM EMERGENCY NAVIGATION - COMPLETE (2026-11-16)

> Scope note: this section supersedes the older N-U3/N-U4 done + NAV done markers above.
> The user explicitly authorized the redesigned frontend and this navigation UI;
> that authorization overrides the original `frontend/` READ-ONLY constraint for
> the files listed below. The legacy `/api/v1/routes` planner and all WebSocket
> contracts are unchanged.

### 11.1 Backend implementation

| File | Purpose |
|---|---|
| `backend/app/routing/osm_graph.py` | Real OSM graph builder, snapping, profile rules, A*, route geometry assembly. No demo-grid fallback. |
| `backend/app/services/navigation_service.py` | Loads `source=osm` lanes only, builds graph inputs, calls the planner, maps `NavigationError` to the existing `AppError` contract. |
| `backend/app/schemas/route.py` | `NavigateRequest`, `NavigateResponse`, route Feature/LineString and snap schemas. Legacy `RouteRequest`/`RouteOut` untouched. |
| `backend/app/api/v1/endpoints/routes.py` | Adds `POST /api/v1/routes/navigate`; existing `POST /api/v1/routes` remains the legacy demo planner. |
| `backend/tests/unit/test_osm_navigation.py` | 19 graph/algorithm tests. |
| `backend/tests/integration/test_navigation_api.py` | 6 REST integration tests. |

Graph behavior:

- Builds deterministically from imported OSM `lanes.path` geometry only.
- Splits ways only at shared OSM vertices/endpoints; keeps full LineStrings.
- Honours `oneway`, roundabout one-way semantics, `access`, `foot`, `bicycle`,
  `maxwidth`, `maxheight`, `width`, `stairs`, and blocked lanes.
- Profiles: `fire_truck`, `responder_bike`, `walking` with separate min-width,
  vehicle-size, speed and access rules.
- Walking ignores vehicle `oneway` by default, but honours explicit
  `oneway:foot=yes/-1`. Bikes honour `oneway:bicycle=no` as bidirectional.
- Weak components prevent fake connectivity; A* is used with time or distance
  weighting. Time weighting uses a documented highway-class speed table.
- Snapping is limited to 500 m. The planner searches up to 24 near candidates
  per endpoint and up to 128 candidate pairs, so an unroutable nearest pair
  does not hide a valid nearby pair.
- Every response carries honesty metadata: `geometry_source=openstreetmap`,
  `algorithm=astar_osm`, `duration_basis`, snap distances and warnings.
- Imported widths are class-based estimates (`width_verified=false`), so width
  restrictions are approximate and warned about. ETA has no live traffic.

### 11.2 Navigation API contract

```http
POST /api/v1/routes/navigate
Content-Type: application/json

{
  "origin": {"lat": 32.727053, "lng": 74.854296},
  "destination": {"lat": 32.729133, "lng": 74.857820},
  "profile": "fire_truck"
}
```

Optional `"weighting": "distance"` switches the cost function; default is
`"time"`. Invalid bodies return HTTP 422 with the existing error shape.

Success is a GeoJSON `Feature` with a `LineString` plus snap metadata:

```json
{
  "route": {
    "type": "Feature",
    "geometry": {"type": "LineString", "coordinates": [[74.8544, 32.7271], "..." ]},
    "properties": {
      "distance_m": 1565,
      "duration_s": 332,
      "profile": "fire_truck",
      "weighting": "time",
      "algorithm": "astar_osm",
      "duration_basis": "osm_highway_class_speed_table_no_live_traffic",
      "geometry_source": "openstreetmap",
      "edge_count": 18,
      "edge_ids": ["..."],
      "warnings": ["...", "..."],
      "origin_snap_distance_m": 462.5,
      "destination_snap_distance_m": 185.4
    }
  },
  "origin": {"lat": 32.727053, "lng": 74.854296, "snapped": {"lat": 32.7288, "lng": 74.8506}, "snap_distance_m": 462.5, "edge_id": "...", "way_id": "...", "road_name": "...", "highway": "..."},
  "destination": {"lat": 32.729133, "lng": 74.857820, "snapped": {"lat": 32.7297, "lng": 74.8571}, "snap_distance_m": 185.4, "edge_id": "...", "way_id": "...", "road_name": "...", "highway": "..."},
  "warnings": ["..."]
}
```

Error codes: `ROUTE_NOT_FOUND` (404), `ORIGIN_OUT_OF_NETWORK`,
`DESTINATION_OUT_OF_NETWORK`, `OSM_GRAPH_EMPTY`, `VALIDATION_ERROR` (422).
Errors keep the existing shape: `{"error": {"code", "message", "request_id"}}`.

### 11.3 Frontend workflow

- Navigation entry points: overview/routing card and fire-alert action
  (`Navigate` / `Recalculate route`).
- Destination defaults to the selected fire incident; origin defaults to the
  first fire post, with an alternative post selector and manual WGS84 input.
- Profiles are separate from legacy routing profiles and expose only
  `fire_truck`, `responder_bike`, `walking`.
- The map draws the real route casing/line plus origin and destination markers;
  `MapView` fits the route bounds. The route summary shows distance, modeled
  ETA, snap warnings and request errors.
- Changing the alert clears the old route. Requests are aborted and superseded
  when inputs change; a backend-unavailable message is shown instead of a
  silent failure.
- All layers, picking, tooltips, simulations and incident actions remain intact.

Files: `frontend/src/types.ts`, `config.ts`, `store.ts`, `lib/api.ts`,
`lib/navigation.ts`, `lib/meta.ts`, `lib/layers.ts`,
`components/MapView.tsx`, `NavigationCard.tsx`, `NavOverlay.tsx`,
`OverviewPanel.tsx`, `AlertsPanel.tsx`, `scripts/nav-check.ts`,
`package.json`.

### 11.4 Verification results

- Backend full suite: `79 passed` in 12.37 s.
  - Navigation unit tests: 19 passed.
  - Navigation API integration tests: 6 passed.
- Frontend: `npm run build` PASS, `npm run typecheck` PASS,
  `npm run nav:check` -> `ALL NAV CHECKS PASSED`,
  `npm run sim:check` -> `ALL CHECKS PASSED`.
- Smoke suite: 41/41 checks PASS on 2026-11-16.
- Live uvicorn + httpx probe: HTTP 200, CORS allow-origin
  `http://localhost:5173`, OPTIONS 200.
- Real imported graph: 804 nodes, 988 edges, 7 weakly connected components.
- Real demo route (fire post A -> B-021 centroid):
  - `fire_truck`: 1565 m, 332 s, 18 edges, 82 coordinates,
    snaps 462.5 m / 185.4 m.
  - `responder_bike`: 1565 m, 385 s, 18 edges, 82 coordinates.
  - `walking`: 89 m, 71 s, 1 edge, 5 coordinates,
    snaps 354.8 m / 35.3 m (walking reverses the vehicle one-way legally).
- Demo endpoints: origin `[74.85429648225089, 32.72705300522726]`,
  destination `[74.85782035268767, 32.72913306045382]`.

### 11.5 Known limitations

- No turn restrictions, live traffic, closures or time-dependent access.
- ETA is a class-speed model estimate, not a guaranteed arrival time.
- Widths and some access tags imported from OSM are approximate/unverified.
- Routes are limited to the imported OSM extract and the 500 m snap radius.
- The frontend build emits Rollup annotation warnings from `node_modules/zod`;
  they are non-blocking.
- The new navigation profiles are intentionally separate from the legacy
  `fire_truck` / `medical` / `evacuation` demo-routing profiles.

### 11.6 Reproduce

```powershell
# backend tests
cd backend
.\.venv\Scripts\python.exe -m pytest -q

# frontend checks
cd ..\frontend
npm run typecheck
npm run build
npm run sim:check
npm run nav:check
```

With the backend and frontend running, select a fire incident and press
`Navigate`, or open the navigation card in Overview/Routing and choose an
origin, destination and profile.

### 11.7 Manual testing guide

Prerequisites: PostgreSQL is running; the `juras` database has the Alembic
schema, demo seed data, and the OSM import. If OSM is missing, re-run
`backend/scripts/import_osm_geojson.py`.

Start the backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Check `http://localhost:8000/health` (database connected) and
`http://localhost:8000/docs` (navigation endpoint is under `routes`).

Point the frontend at the backend WebSocket. Create `frontend/.env.local`
(this file is gitignored):

```powershell
cd frontend
'VITE_WS_URL=ws://localhost:8000/ws' | Set-Content .env.local -Encoding ascii
npm run dev
```

Open `http://localhost:5173`. Manual UI flow:

1. Top-left Scenario injection -> `Fire`; wait 25-40 s for the incident.
2. Select the fire alert and click `Navigate`, or use the Emergency
   navigation card in Overview/Routing.
3. Confirm the real OSM route line, START/INCIDENT markers, camera fit,
   distance/ETA summary, warnings, and snap metadata.
4. Switch `Truck` / `Bike` / `Walk`; the route recalculates.
5. Change the fire-post origin or enter custom WGS84 coordinates; the route
   recalculates.
6. Clear the route and select a different alert; the previous route clears.

Direct API test in Swagger (`POST /api/v1/routes/navigate`):

```json
{
  "origin": {"lat": 32.727053, "lng": 74.854296},
  "destination": {"lat": 32.729133, "lng": 74.857820},
  "profile": "fire_truck"
}
```

Expected demo result: HTTP 200, 1565 m, 332 s, 18 edges. Change `profile` to
`walking` for 89 m / 71 s / 1 edge. `ORIGIN_OUT_OF_NETWORK` is returned for an
origin outside the 500 m snap radius; invalid payloads return
`VALIDATION_ERROR` (422). `OSM_GRAPH_EMPTY` means the OSM import has not run.

### 11.8 Final refinements and cleanup

- `frontend/src/config.ts` derives the REST base from `VITE_WS_URL` and strips
  both `/ws` and `/ws/live` before appending `/api/v1/...`.
- `NavigationCard` opens the custom-coordinate form automatically when no fire
  post exists, so manual origin entry is always reachable.
- Final checks after these edits: backend `79 passed`; frontend `typecheck`,
  `build`, `sim:check`, and `nav:check` all passed.
- Temporary smoke server logs were deleted.
- A leftover running structural simulation from an earlier smoke run was marked
  stopped in the local database; active simulations are now zero.
- No frontend `.env.local` is committed; it is local-only and gitignored.

### 11.9 Commit map

All work is grouped into small, reviewable commits so the file-level history is
easy to recover with `git log --oneline` and `git show <hash>`. The exact commit
hashes are appended below after the commits are created.


| Commit | Area | Files and purpose |
|---|---|---|
| `ee25d59` | Backend setup | `.env.example`, `requirements.txt`, `pytest.ini`, `alembic.ini`, `alembic/**`, `README.md` - config template, dependencies, initial PostGIS migration, setup docs |
| `a5c660c` | OSM data | `backend/buildings.geojson`, `backend/roads_lanes.geojson` - 76 buildings and 521 routable OSM ways |
| `ed3e300` | Backend core | `app/core/**`, `app/db/**`, `app/models/**`, `app/schemas/**` (except route), `app/repositories/**`, `app/state.py` - settings, async DB, models, contracts, repositories |
| `4709890` | Risk and simulation | `app/risk/**`, `app/simulation/**`, `app/realtime/**` - scoring rules, seeded scenario models/manager, event bus |
| `d74c269` | Routing and navigation | `app/routing/**`, `app/services/routing_service.py`, `app/services/navigation_service.py`, `app/schemas/route.py` - legacy Dijkstra plus real OSM graph, snapping, profile rules, A* |
| `fdf0ffc` | Data services | `app/services/{reading,incident,gis,osm_import}_service.py` - ingest pipeline, incident lifecycle, GeoJSON queries, OSM import |
| `63ed325` | REST API | `app/api/**` - health/buildings/lanes/sensors/readings/simulations/risks/incidents/routes; adds `/routes/navigate` |
| `41e3fc5` | WebSockets | `app/ws/**` - `/ws/live` blueprint envelope and `/ws` frontend snapshot/telemetry/alert/routes/hazard/building/flood adapter |
| `cfcb20a` | App wiring | `app/main.py` - lifespan, DB check, CORS, error envelope handlers, router registration |
| `2e6dd48` | CLI scripts | `scripts/{seed_demo_data,import_osm_geojson,smoke_test}.py` - seed, idempotent OSM import, 41-check smoke |
| `ed74fe8` | Backend tests | `tests/**` - unit and integration coverage including 19 OSM graph tests and 6 navigation API tests |
| `77cdab6` | Frontend nav foundation | `types.ts`, `config.ts`, `lib/api.ts`, `lib/navigation.ts`, `lib/meta.ts`, `scripts/nav-check.ts`, `package.json` - contracts, REST client, geometry validation, profile metadata, nav check |
| `93bb1ad` | Frontend nav state | `src/store.ts` - origin/profile/target state, request abort/supersede, auto-clear, errors |
| `eb1e834` | Frontend map | `lib/layers.ts`, `components/MapView.tsx` - route casing/line, START/INCIDENT markers, bounds fit, overlay mount |
| `05645df` | Frontend nav UI | `NavigationCard.tsx`, `NavOverlay.tsx`, `OverviewPanel.tsx`, `AlertsPanel.tsx` - destination/origin/profile controls, route summary, fire-alert action |
| `4b19860` | Frontend visual refresh | `index.html`, `tailwind.config.js`, `index.css`, `App.tsx`, `TopBar`, `BottomNav`, `SimBar`, `Chart`, `cards` - flat operations-center styling |
| `22198b4` | Repo hygiene | remove tracked `backend/app/__pycache__/main.cpython-314.pyc` |
| `959483b` | Repo hygiene | remove tracked `backend/app/__pycache__/__init__.cpython-314.pyc` |

The final docs commit (the commit that introduced this section) also adds
`JURAS_Backend_Engineering_Blueprint.docx` as the original requirements
reference. Use `git log -1 --stat` to see it.

---

## 12. 2026-11-17 - OSM pilot coverage + Google-Maps-style simulation navigation

### 12.1 Root cause fixed

The imported OSM bbox started at lon `74.8575`, but the demo/pilot area (Fire
Post A, Medical Post E, assemblies G/Q, buildings such as B-014) sits at
`74.8543-74.8607`. Navigation therefore snapped points 400-600 m onto the
nearest boundary road, producing 0 m / tiny simulation routes. Real OSM ways
for the pilot bbox `74.849,32.724,74.863,32.733` were fetched from the official
OSM API map endpoint (Overpass mirrors returned 406/502/timeout), merged, and
re-imported:

- `backend/roads_lanes.geojson`: 700 features (179 new pilot ways, 57
  overlapping ways tag-merged).
- Import stats: `lanes_created=179`, `lanes_updated=521`, `nodes_created=287`,
  `nodes_total=1076`; lane bbox now `74.8473731-74.9077558`,
  `32.715585-32.7496094`.
- Result: A -> B-014 is now ~563 m / 9 edges with 17 m and 1 m snaps, instead
  of a degenerate snap-pair route.

### 12.2 Backend changes (frontend untouched)

> **Superseded 2026-11-18:** section 15 replaced the connector geometry,
> total-distance/duration behavior, and the `None` simulation fallback described
> below. This section remains as a historical record of the first OSM pilot.

- `app/routing/osm_graph.py`
  - `_plan_route` now evaluates up to 24 near snap pairs (sorted by access
    distance, pruned with a lower bound), actually routes each pair, and picks
    the best combined road + access/egress cost. A non-zero road route is
    preferred over a zero-length snap pair. Route score includes connector
    walking time (`1.3 m/s`) for `time` weighting.
  - Hazards multiply edge cost x6 within `radius + 10 m`; floods block
    `fire_truck` at `depth_cm >= 25` and otherwise multiply by `1 + depth/30`,
    matching the legacy demo rules.
  - `RouteResult` adds `steps`, `road_distance_m`, `road_duration_s`,
    `access_distance_m`, `access_duration_s`, `egress_distance_m`,
    `egress_duration_s`. Route geometry starts at the requested origin and ends
    at the requested destination, including off-road walking connectors.
  - Turn-by-turn `RouteStep` generation: `walk`/`depart`/`continue`/
    `turn-left|right`/`slight-*`/`sharp-*`/`uturn`/`roundabout`/`arrive`, with
    compass headings, OSM road names, per-step geometry, and duration.
  - Degenerate zero-length steps no longer inflate route distance.
- `app/services/navigation_service.py`: `load_navigation_graph()`, live
  hazard/flood context (`avoid_hazards`, default true), connector totals and
  step payloads in `/routes/navigate` properties.
- `app/schemas/route.py`: `NavigateRequest.avoid_hazards`, `NavigateStep`, and
  additive `NavigateProperties` fields (`road_*`, `access_*`, `egress_*`,
  `steps`). Existing clients keep working.
- `app/api/v1/endpoints/routes.py`: forwards `avoid_hazards`.
- `app/services/simulation_navigation_service.py` (new):
  `plan_osm_routes_for_building()` maps the legacy simulation profiles onto OSM
  (`fire_truck` -> `fire_truck`, `medical` -> `responder_bike`, `evacuation` ->
  `walking`), returns the unchanged WS `Route` shape (`path`, `length_m`,
  `travel_s`, `eta_s`, `last_mile_m`, `note`, `from`, `to`) plus optional
  `steps`, and picks the fastest reachable assembly for evacuation. Returns
  `None` when no OSM graph exists so the caller falls back to the legacy grid.
- `app/ws/frontend_adapter.py`: caches the OSM graph at world load and plans
  fire/medical/evacuation routes on real roads during simulations (including
  re-planning when flood zones change). Route `path` now includes connectors;
  `foot_path` stays empty to avoid double drawing.

### 12.3 Verification

- `backend/tests/unit/test_osm_navigation.py`: 19 existing + 3 new tests
  (turn-by-turn steps, off-road connectors in geometry/totals, hazard reroute
  and deep-flood fire-truck block).
- `backend/tests/integration/test_navigation_api.py`: 6 existing + 1 new test
  (turn-by-turn steps, connector geometry, `avoid_hazards` contract).
- `backend/tests/unit/test_simulation_navigation.py` (new): 3 tests for profile
  mapping, legacy WS Route shape, `None` fallback, and offline-building
  infeasibility.
- Full backend suite: `87 passed` (`pytest -q`, ~10 s).
- Live-data probe for B-014: fire 581 m / 86 s road time / 100 s ETA with 9
  steps; medical 890 m / 208 s ETA with 12 steps; evacuation to Assembly Q
  525 m / 417 s with 9 steps.
- Frontend remains READ-ONLY: `/routes/navigate` and `/ws` payload changes are
  additive, so no frontend edit was required or made.

### 12.4 Operator commands

```powershell
# re-import the OSM dataset if the DB is reset (run from backend/)
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\import_osm_geojson.py
# navigation + full backend tests
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m pytest tests/unit/test_osm_navigation.py tests/integration/test_navigation_api.py -q
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m pytest -q
```

---

## 13. 2026-11-17 - Live location + nearest real station navigation

### 13.1 Problem

The navigation card always used the first demo `fire_post` lane node as the
responder origin and never asked the browser for a live location. It also had
no concept of dispatching the nearest fire/medical/police station, and there
was no backend source for real map-listed stations.

### 13.2 Backend changes

- `app/core/config.py` + `backend/.env.example`: new `MAPBOX_ACCESS_TOKEN`
  (same public token as `frontend/.env.local` -> `VITE_MAPBOX_ACCESS_TOKEN`)
  and `MAPBOX_STATION_CACHE_SECONDS` (default 600). Local `backend/.env` is
  gitignored and was populated from the existing frontend token.
- `app/services/station_service.py` (new): queries the Mapbox Search Box
  category API (`fire_station`, `hospital`, `police`) with the incident as
  proximity, keeps the same POIs the Mapbox basemap displays, sorts by
  straight-line distance, caches per rounded point for 10 minutes, and falls
  back to the existing demo `fire_post` / `medical_post` nodes when the token
  is missing or the API fails. `httpx` request logging is suppressed because
  its INFO lines include the token in the query string.
- `app/schemas/route.py`: `NavigateRequest` now accepts optional `origin`,
  `department` (`fire|medical|police`) and `origin_mode`
  (`coordinates|nearest_station`) with cross-field validation;
  `NavigateStation` and `origin_station` / `stations_considered` response
  fields are additive.
- `app/services/navigation_service.py`: `nearest_station` mode fetches up to 8
  Mapbox stations near the incident, routes the closest 6 on the imported OSM
  graph with the department profile (`fire` -> `fire_truck`, `medical`/`police`
  -> `responder_bike`), and returns the fastest reachable station. No station
  or no reachable station produces explicit `STATION_DATA_UNAVAILABLE` /
  `STATION_ROUTE_NOT_FOUND` errors instead of silently using a fake origin.
- `app/api/v1/endpoints/routes.py`:
  `GET /api/v1/routes/stations?department=&lat=&lng=&limit=` returns
  Mapbox-listed stations nearest first.

### 13.3 Frontend changes (user-approved minimal edits)

The previous "frontend READ-ONLY" rule was relaxed by the user for this
feature; only navigation-related files changed.

- `src/types.ts`: `NavDepartment`, `NavOriginMode`, `NavStation`, additive
  `NavResponse.origin_station` / `stations_considered`.
- `src/lib/api.ts`: `fetchNavigation` now takes a request object and sends
  `origin_mode`/`department`.
- `src/store.ts`: `navDepartment` (default `fire`), `navOriginMode` (default
  `nearest_station`), `navStation`; department/mode changes re-plan an active
  route; nearest mode does not require a manual origin.
- `src/components/NavigationCard.tsx`: "Nearest station" / "Manual origin"
  toggle, Fire/Medical/Police department buttons, "Use my location" via
  `navigator.geolocation`, and the chosen Mapbox station (name, address,
  source, straight-line distance) in the result card.
- `src/components/MapView.tsx`: Mapbox `GeolocateControl` at top-right; its
  `geolocate` event fills the navigation origin with the live browser
  position.

### 13.4 Verification

- New tests: `tests/unit/test_station_service.py` (nearest-first ordering,
  cache, missing token, demo fallback, police has no demo fallback) and 4 new
  integration tests (nearest-station success, missing department, unavailable
  station data, `GET /routes/stations`).
- Full backend suite: `96 passed`.
- Frontend: `npm run typecheck`, `npm run nav:check`, `npm run build` passed.
- Live Mapbox + DB probe at incident `74.8575,32.7285`:
  - fire: chose "Fire Station" (Residency Road, 1719.7 m straight-line,
    2603 m / 25-step OSM route);
  - medical: chose "Government Medical College Jammu" (320 m route);
  - police list: "Jewel Chowk-ITMS Jn" 318 m, "Nawabad Police Station" 406 m.
- `/routes/stations` returned `source=mapbox`, `count=5` fire stations.

### 13.5 Operator commands

```powershell
# backend/.env (gitignored) must contain the same public Mapbox token
MAPBOX_ACCESS_TOKEN=pk....

# from backend/
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m pytest -q
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# from frontend/
npm run typecheck; npm run nav:check; npm run build
```

---

## 14. 2026-11-17 - Dynamic road closures + automatic alternate routes

### 14.1 What was added

Operators can now close a point on the road network and the router immediately
recommends a different shortest path. Closures are hard blocks (not penalties),
apply to every routing profile, and are shared by the HTTP navigation API, the
nearest-station mode, simulation routes, and the legacy demo-grid planner.

### 14.2 Backend changes

- `app/state.py`: in-memory `closures` registry with `add_closure`,
  `remove_closure`, `clear_closures`, `closures_snapshot`; `routing_ctx()`
  now also returns active `closures` as `{pos, radius_m}`.
- `app/routing/osm_graph.py`: `_edge_penalty` returns `None` when an edge is
  within a closure radius, so the edge is removed from A* and any path using
  it is rejected. `compute_navigation(..., closures=...)` and warnings now
  include active closures; no other profile-specific exception.
- `app/routing/graph.py` + `app/routing/algorithms.py`: `Ctx.closures` added
  and the legacy demo-grid Dijkstra blocks an arc when its midpoint falls in a
  closure radius.
- `app/services/navigation_service.py`: both coordinate and nearest-station
  modes pass closures and return `closures_considered`.
- `app/services/simulation_navigation_service.py` + `app/ws/frontend_adapter.py`:
  simulation fire/medical/evacuation routes also avoid closures.
- `app/schemas/route.py`: `ClosureCreate` (lat/lng/radius 5-100 m/reason/
  source), `NavigateProperties.closures_considered`.
- `app/api/v1/endpoints/routes.py`:
  - `GET /api/v1/routes/closures`
  - `POST /api/v1/routes/closures` (201, returns the closure)
  - `DELETE /api/v1/routes/closures/{id}`
  - `DELETE /api/v1/routes/closures` (clear all)
  Closures are intentionally in-memory (MVP): they reset when the backend
  restarts.

### 14.3 Frontend changes

- `src/types.ts`: `NavClosure`, `NavRouteProperties.closures_considered`.
- `src/lib/api.ts`: `fetchClosures`, `createClosure`, `deleteClosure`,
  `clearClosures`.
- `src/store.ts`: closure list/mode/error/busy state. Adding, removing, or
  clearing a closure automatically re-plans the active route
  (`navigateToAlert`), which is how the alternate shortest path appears.
- `src/components/NavigationCard.tsx`: new "Road closures / obstacles" panel:
  - "Block route ahead" drops a closure at ~55% of the current route geometry;
  - "Pick closure on map" arms map-click placement;
  - active closure list with individual remove and "Clear all";
  - result banner "Re-routed around N active road closure(s)".
- `src/components/MapView.tsx`: raw map click places a closure when armed
  (18 m radius, reason `Road closed at map click`); building selection is
  suppressed in that mode.
- `src/lib/layers.ts`: deck.gl red closure circles plus "ROAD CLOSED" labels.

### 14.4 Verification

- `tests/unit/test_osm_navigation.py`: +2 tests. A closure on the direct road
  forces the detour edge and a longer route; a closure with no alternative
  raises `ROUTE_NOT_FOUND`.
- `tests/integration/test_navigation_api.py`: +3 tests. Closure CRUD, blocked
  route until DELETE, clear-all reopening, `closures_considered` and warning.
- Full backend suite: `101 passed`.
- Live DB + real Mapbox nearest-fire route: baseline 2603 m; closure of radius
  30 m at the route midpoint produced a 2709 m / 44-edge alternate route with
  `Route avoids 1 active road closure(s)` (detour +106 m).
- Frontend: `npm run typecheck`, `npm run nav:check`, `npm run build` passed.

### 14.5 Operator use

1. Start a navigation route (nearest station or manual origin).
2. Click "Block route ahead", or arm "Pick closure on map" and click the map.
3. The backend blacklists affected OSM edges and returns the next fastest
   shortest path; the card shows the new distance/ETA and detour count.
4. Remove a closure or "Clear all" to restore the original route.

```powershell
# add / list / delete a closure manually (from backend/)
curl.exe -X POST http://localhost:8000/api/v1/routes/closures -H "Content-Type: application/json" -d '{\"lat\":32.7335,\"lng\":74.8636,\"radius_m\":20,\"reason\":\"road work\"}'
curl.exe http://localhost:8000/api/v1/routes/closures
curl.exe -X DELETE http://localhost:8000/api/v1/routes/closures/closure-1
```

---

## 15. 2026-11-18 - Road-only navigation geometry + honest no-route simulation

### 15.1 Problem

The OSM router still appended synthetic off-road connectors from the requested
origin/destination to the snapped road points, counted them in route distance
and delay, and emitted `walk` steps. Simulation payloads could still fall back
to the synthetic demo grid or fabricate a straight `[origin, destination]` path
when a profile had no route. That made the map look connected where OSM has no
road.

### 15.2 Backend changes

- `app/routing/osm_graph.py`
  - Route geometry is now road-only: snapped origin point + OSM edge geometry +
    snapped destination point. Requested off-road points and walk connectors are
    never included.
  - `distance_m` / `duration_s` now equal `road_distance_m` /
    `road_duration_s`; access and egress gaps remain reported separately in
    `access_*` / `egress_*` fields and warnings.
  - `validate_route_geometry(geometry, edges, tolerance_m=1.0)` checks every
    vertex and segment midpoint against the route edges; violations raise
    `ROUTE_GEOMETRY_INVALID` (HTTP 500) instead of drawing suspect geometry.
  - `_plan_route` prefers snap pairs whose access/egress gaps are within 25 m of
    the closest available snap (`PAIR_SNAP_WINDOW_M`), so a shorter road detour
    no longer wins by ending 100+ m away from the destination. Far-pair
    evaluation remains as fallback when no near pair is routable. Regression:
    the evacuation test initially ended at the junction 110 m short of the
    assembly because walking time made a farther snap pair look 3 s faster.
  - A pair that snaps both endpoints to the same point now reports
    `ROUTE_NOT_FOUND` ("same point ... no road segment to travel") instead of
    returning a zero-length success. Disconnected or profile-blocked pairs keep
    explicit messages mentioning one-way/access tags or disconnected OSM
    components.
  - `compute_navigation(..., max_snap_distance_m=...)` allows tests/callers to
    tighten the snap radius; turn-by-turn steps contain no `walk` maneuvers.
- `app/services/simulation_navigation_service.py`
  - Infeasible routes now use `path: []` (never a fabricated two-point line).
  - Without an OSM graph, `plan_osm_routes_for_building` returns all three
    profiles as infeasible with empty paths and the note
    "No OSM road graph is loaded; no simulation route can be drawn."
  - Feasible payloads carry road-only paths, zero `last_mile_m`, no foot path,
    and endpoint snap-gap notes; `from`/`to` labels are preserved.
- `app/ws/frontend_adapter.py`: removed the demo-grid planner fallback and the
  early `graph is None` return; simulation routes always come from the imported
  OSM graph.

### 15.3 Frontend changes (user-approved; Mapbox/OSM kept)

- `src/lib/layers.ts`: route casing, flow, and responder units draw only
  `feasible` routes with at least two coordinates. The existing local simulator
  `foot_path` rendering is preserved.
- `src/components/MapView.tsx`: no ETA chip is created for an infeasible/empty
  route (previously it could show "< 1 min" at the fallback origin).
- `src/components/cards.tsx`: infeasible simulation routes show "No route" plus
  the backend note, and no progress bar; feasible routes are unchanged.
- `src/components/NavigationCard.tsx`: snap/road-only warnings are prioritised
  and an explicit "Road-only route / start/end snapped N m off-road / connectors
  are not drawn" notice appears when a snap gap exceeds 5 m.
- Mapbox basemap, Mapbox station lookup, Geolocate control, OSM lane rendering,
  and the local demo simulator were left intact.

### 15.4 Tests and verification

- `tests/unit/test_osm_navigation.py`
  - `test_offroad_connectors_are_excluded_from_geometry_and_totals`: geometry
    starts/ends at snapped road points, no `walk` steps, totals equal road
    totals, geometry validates against OSM edges.
  - `test_route_geometry_validation_flags_offroad_connector`: an off-road point
    is reported as "off the OSM road network".
  - `test_near_but_disconnected_roads_are_not_joined`: nearby but topologically
    separate OSM ways raise `ROUTE_NOT_FOUND` (404).
  - `test_zero_length_snap_pair_reports_no_route`: same-point snap pair returns
    "same point ... no road segment to travel" (404).
  - `test_narrow_lane_blocks_fire_truck_but_not_bike_or_walking`: 2 m service
    lane rejects `fire_truck` but allows `responder_bike`/`walking`.
  - Existing hazard reroute, deep-flood block, and operator-closure tests still
    pass.
- `tests/integration/test_navigation_api.py`:
  `test_navigate_returns_road_only_turn_by_turn_steps` asserts snapped
  start/end, no walk steps, road-only distance, and the road-only warning.
- `tests/unit/test_simulation_navigation.py`:
  `test_plan_osm_routes_returns_empty_paths_without_osm_graph` and
  `test_plan_osm_routes_reports_infeasible_profile_without_fabricated_path`
  assert empty paths, infeasible flags, preserved labels, and no demo fallback;
  the profile-mapping test asserts evacuation ends at the assembly snap point.
- Full backend suite: `105 passed` (`pytest -q`).
- Real local PostGIS probe (1,375 OSM edges, 1,109 nodes, 9 components), Fire
  Post A -> B-014 with `fire_truck`: 543.3 m / 81.0 s, 9 edges, 22 road-only
  coordinates, 25.8 m start snap, 1.0 m end snap, zero geometry violations.
  Simulation payloads: fire 22 coords / 543 m, medical 52 / 882 m, evacuation
  37 / 768 m, all geometry-valid with no foot path.
- Frontend: `npm run typecheck`, `npm run nav:check`, `npm run sim:check`, and
  `npm run build` passed.

### 15.5 Behaviour and contracts

- `POST /api/v1/routes/navigate`
  - `route.geometry.coordinates` is a LineString of imported OSM road vertices
    only. It starts at the snapped origin and ends at the snapped destination;
    requested off-road points and connector segments are not present.
  - `origin` / `destination` still echo the requested `lat`/`lng`, add the
    `snapped` road point, and report `snap_distance_m`. These gaps are also
    reported in `origin_snap_distance_m` / `destination_snap_distance_m`,
    `access_*` / `egress_*`, and warnings.
  - `distance_m` and `duration_s` equal `road_distance_m` /
    `road_duration_s`. They do not include off-road walking time.
  - `steps` contains no `walk` maneuvers; the last step arrives at the snapped
    destination road point.
  - `ROUTE_GEOMETRY_INVALID` is HTTP 500 if any route vertex/segment midpoint is
    more than 1 m from the route edges. `ROUTE_NOT_FOUND` is HTTP 404 for
    same-point snaps, disconnected components, or no traversable pair.
    Endpoint snap failures remain HTTP 422 (`ORIGIN_OUT_OF_NETWORK` /
    `DESTINATION_OUT_OF_NETWORK`).
- Simulation WS `routes` messages keep the legacy shape
  (`profile`, `path`, `foot_path`, `length_m`, `travel_s`, `eta_s`, `feasible`,
  `last_mile_m`, `note`, `from`, `to`, optional `steps`).
  - Feasible: `path` is road-only, `foot_path=[]`, `last_mile_m=0`,
    `travel_s=eta_s=road_duration_s`.
  - Infeasible: `path=[]`, `foot_path=[]`, `length_m=travel_s=eta_s=0`,
    `feasible=false`, `steps=[]`, with a profile-specific note.
  - Missing/empty graph: three infeasible payloads (fire, medical, evacuation)
    with the note "No OSM road graph is loaded; no simulation route can be
    drawn."
- Frontend consumes `path=[]` safely and never draws a fake line, chip, or
  progress bar for an infeasible simulation route. The HTTP navigation route
  markers use the snapped line endpoints.

### 15.6 Files changed for this pass

- Backend:
  - `backend/app/routing/osm_graph.py`
  - `backend/app/services/simulation_navigation_service.py`
  - `backend/app/ws/frontend_adapter.py`
  - `backend/tests/unit/test_osm_navigation.py`
  - `backend/tests/integration/test_navigation_api.py`
  - `backend/tests/unit/test_simulation_navigation.py`
- Frontend:
  - `frontend/src/lib/layers.ts`
  - `frontend/src/components/MapView.tsx`
  - `frontend/src/components/cards.tsx`
  - `frontend/src/components/NavigationCard.tsx`
- Docs:
  - `graph.md`

### 15.7 Intentionally unchanged

- Mapbox basemap and token, `GeolocateControl`, live-location origin, and the
  Mapbox Search Box station lookup (`station_service.py`).
- OSM import pipeline and `roads_lanes.geojson` data (not modified in this
  pass), OSM lane rendering, and the OSM graph cache at world load.
- Hazard, flood, closure, and evacuation assembly-selection behavior.
- The legacy `POST /api/v1/routes` demo-grid planner and the local frontend
  `SimFeed` demo simulator, including its `foot_path` rendering. Only the
  WS simulation adapter stopped using the demo-grid fallback.
- Existing REST/WS payload shapes; all changes are additive or fill existing
  fields.

### 15.8 Operator checks

```powershell
# from backend/
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m pytest -q

# from frontend/
npm run typecheck
npm run nav:check
npm run sim:check
npm run build
```

---

## 16. 2026-11-18 - Operator-facing navigation result card (metadata hidden)

### 16.1 Problem

The navigation result card exposed routing-engine internals to operators:
`<profile> · 57 OSM segments · osm_highway_class_speed_table_no_live_traffic`,
`(mapbox, 1646 m from incident)`, and four backend provenance warnings
("route follows imported OSM geometry, not the synthetic demo grid", "geometry
is road-only; off-road gaps...", "turn-by-turn instructions are derived from
OSM way geometry", ...). None of this helps an operator decide where the truck
drives.

### 16.2 Frontend changes (presentation only; API contract untouched)

- `src/components/NavigationCard.tsx`
  - Result meta line now shows only the profile label (e.g. "Fire tender").
    `edge_count`, `duration_basis`, algorithm and geometry provenance are no
    longer rendered.
  - Backend `warnings[]` is no longer dumped verbatim. Only operational
    conditions are surfaced, in plain language: active fire hazard zones and
    waterlogged roads. Technical provenance strings are filtered out.
  - Snap notice rewritten from "Road-only route. Start snapped 19 m off-road...
    connectors are not drawn" to "Route stays on mapped roads. Nearest road is
    X m from the start; Y m from the incident."
  - Station line drops the provider tag and raw metres: "Station: <name> ·
    <address> — 1.6 km from incident".
  - Station hint text no longer says "Mapbox-listed"; section hint changed from
    "OSM road network · A*" to "Fastest road route".
  - Error box shows the human-readable message only (no raw error code line).
- `src/components/NavOverlay.tsx`
  - Removed the "{n} OSM segments" chip, the raw error code prefix, and the
    "on the OSM network" wording from the computing state.

### 16.3 Intentionally unchanged

- `POST /api/v1/routes/navigate` payloads, all warning strings, `edge_count`,
  `duration_basis`, `geometry_source`, snap metadata and turn-by-turn `steps`
  (still available to any client that wants them).
- Mapbox basemap, station lookup, geolocation, closures, hazards, layers,
  simulation routing, and the local demo simulator.

### 16.4 Verification

- `npm run typecheck` PASS.
- `npm run nav:check` -> `ALL NAV CHECKS PASSED`.
- `npm run build` PASS (same non-blocking zod/Rollup and chunk-size warnings).
- Files changed: `frontend/src/components/NavigationCard.tsx`,
  `frontend/src/components/NavOverlay.tsx`, `graph.md`.

---

## 17. 2026-11-18 - WebSocket disconnect noise fixed (`WebSocketDisconnected`)

### 17.1 Symptom

Uvicorn logged an ERROR with traceback on `/ws` when a browser tab reconnected
or closed:

```
File "app/ws/ws_routes.py", line 34, in ws_frontend
    raw = await websocket.receive_text()
starlette.websockets.WebSocketDisconnected: WebSocket is not connected. Need to call "accept" first.
```

### 17.2 Root cause

Starlette's `WebSocketDisconnected` is a `RuntimeError`, **not** a subclass of
`WebSocketDisconnect`. When a client disappears mid-connection:

1. Starlette's `send()` marks the socket `application_state=DISCONNECTED` and
   raises `WebSocketDisconnect(1006)`.
2. `FrontendWorld.send_raw` / `broadcast` swallowed that error and removed the
   socket, but the route's receive loop kept running.
3. The next `receive_text()` therefore raised `WebSocketDisconnected`, which
   fell through `except WebSocketDisconnect` into the generic
   `logger.exception("ws error")`.

The client behaved correctly in every case; only the logging was wrong. Rapid
reconnects are normal in dev (page reload, Vite HMR, the feed's 3 s retry).

### 17.3 Fix

- `app/ws/ws_routes.py`
  - Catch `(WebSocketDisconnect, WebSocketDisconnected)` as a normal disconnect
    for both `/ws` and `/ws/live`; no traceback for clients going away.
  - `world.connect()` now returns `bool`; the route exits immediately when the
    initial snapshot could not be delivered.
  - Cleanup moved to `finally` (`world.disconnect` / `bus.disconnect`), so a
    socket is never left registered after any exit path.
  - Unexpected exceptions still log via `logger.exception`; `/ws/live` now does
    the same instead of silently swallowing real errors.
- `app/ws/frontend_adapter.py`
  - `connect()` returns `False` when the snapshot send fails and only registers
    the socket in `ui_connections` **after** a successful snapshot, so early
    disconnects never enter the broadcast fan-out.
  - `send_raw()` returns `bool` success and unregisters on failure.

No payload, contract, or behaviour change for healthy clients.

### 17.4 Verification

- Live server on port 8001 + client that aborts the TCP transport at 0.02 s,
  0.05 s, 0.1 s, 0.2 s, 0.4 s and 0.6 s after connecting (8 abrupt disconnects,
  including during the initial snapshot write): server log shows only
  `connection open` lines, **zero** `ws error`, zero tracebacks.
- Healthy client still receives the full `snapshot` and can send a command.
- Backend unit suite: `76 passed`. Integration tests were not runnable at the
  time because `tests/conftest.py` targets the local `juras_test` database and
  local PostgreSQL `:5432` was not running (`backend/.env` currently points at
  Supabase, so this does not affect the running app).
- Files changed: `backend/app/ws/ws_routes.py`,
  `backend/app/ws/frontend_adapter.py`, `graph.md`.


