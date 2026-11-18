# JURAS Backend — Complete Reference

> **Project:** Jammu Urban Risk Intelligence System (JURAS)
> **Pilot area:** Purani Mandi, Jammu
> **Stack:** Python 3.11+ / FastAPI / async SQLAlchemy / PostgreSQL + PostGIS
> **Scope of this document:** schema, every REST and WebSocket route, internal routing, risk/incident pipeline, and how real field sensors can POST readings and receive responses.
>
> **Status (verified against the working tree, 18 Nov 2026):** the REST ingestion path for real sensors is implemented. The dashboard WebSocket (`/ws`) is still driven by the in-process simulator, not by field readings. MQTT is **not** implemented. Details are called out explicitly in [Real sensors](#10-real-sensors--complete-onboarding) and [Known gaps](#13-known-gaps-and-roadmap).

---

## Table of contents

1. [What this backend is](#1-what-this-backend-is)
2. [Quick start](#2-quick-start)
3. [Runtime architecture and data flow](#3-runtime-architecture-and-data-flow)
4. [Database schema](#4-database-schema)
5. [REST API conventions](#5-rest-api-conventions)
6. [Complete REST endpoint map](#6-complete-rest-endpoint-map)
7. [Endpoint-by-endpoint behaviour](#7-endpoint-by-endpoint-behaviour)
8. [WebSocket contracts](#8-websocket-contracts)
9. [Routing engine](#9-routing-engine)
10. [Real sensors — complete onboarding](#10-real-sensors--complete-onboarding)
11. [Risk engine and incident lifecycle](#11-risk-engine-and-incident-lifecycle)
12. [Simulation system](#12-simulation-system)
13. [Known gaps and roadmap](#13-known-gaps-and-roadmap)
14. [Operations, tests, and troubleshooting](#14-operations-tests-and-troubleshooting)
15. [File map](#15-file-map)

---

## 1. What this backend is

JURAS is a **simulation-first** risk-intelligence prototype for a dense Indian market area. It maintains a geospatial model of buildings, lanes, sensors, readings, risk assessments, incidents, and response routes.

What is actually implemented:

| Capability | Status | Notes |
|---|---|---|
| PostGIS schema for buildings, lanes, sensors, readings, risks, incidents, simulations | ✅ Implemented | 10 tables, SRID 4326 |
| REST ingestion of readings from real hardware | ✅ Implemented | `POST /api/v1/readings` |
| Rule-based risk scoring | ✅ Implemented | Fire, flood, structural; `demo-v1` rules |
| Automatic incident creation on high/critical risk | ✅ Implemented | Deduplicated per target + hazard |
| Incident state machine + audit events | ✅ Implemented | open → acknowledged → resolved/false_alarm |
| OSM road routing with A* | ✅ Implemented | Fire truck, responder bike, walking |
| Door-to-building frontage trimming | ✅ Implemented | Route stops at street-facing footprint edge |
| Road closures + automatic WS route replanning | ✅ Implemented | In-memory closures; live replan |
| Nearest emergency station via Mapbox | ✅ Implemented | Falls back to demo fire/medical posts |
| Simulator scenarios + live dashboard WebSocket | ✅ Implemented | `/ws`, simulator-generated telemetry |
| Raw event bus for backend consumers | ✅ Implemented | `/ws/live` |
| MQTT broker/subscriber | ❌ Not implemented | No MQTT client in dependencies |
| Sensor provisioning REST endpoint | ❌ Not implemented | Register with SQL (documented below) |
| Real readings → dashboard `/ws` cards/telemetry | ❌ Not wired | REST persists and emits on `/ws/live` only |
| Authentication / API keys / rate limiting | ❌ Not implemented | Put behind a proxy/VPN |
| Persisted road closures | ❌ Not implemented | Stored in `app_state` only |

**Truthfulness rule:** every risk score is an illustrative demo rule, not a certified safety judgment. Data labels returned by the API say so (`demo-v1`, "Illustrative demo data").

---

## 2. Quick start

All commands are PowerShell from the repository root unless stated otherwise.

### 2.1 Backend

```powershell
cd backend

# Use the existing virtualenv if present; otherwise create one.
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt

# Configure the database connection (edit DATABASE_URL inside).
Copy-Item .env.example .env

# Create/upgrade tables.
alembic upgrade head

# Wipe + load demo data (17 nodes, 25 lanes, 14 buildings, 14 sensors, 3 demo incidents).
.\.venv\Scripts\python.exe scripts\seed_demo_data.py

# Add the real OSM geometry used by navigation (76 buildings, 700 lanes).
.\.venv\Scripts\python.exe scripts\import_osm_geojson.py

# Start the API. Bind 0.0.0.0 so sensors on the LAN can reach it.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> `seed_demo_data.py` deletes **all** rows in all 10 tables. Always run the OSM import **after** seeding, never the other way around.

URLs:

| URL | Purpose |
|---|---|
| `http://localhost:8000/` | Root status JSON |
| `http://localhost:8000/health` | Health + DB check |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/openapi.json` | OpenAPI schema |
| `http://localhost:8000/api/v1/...` | REST API |
| `ws://localhost:8000/ws` | Dashboard WebSocket contract |
| `ws://localhost:8000/ws/live` | Raw event bus |

### 2.2 Frontend

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api` and `/ws` to `http://localhost:8000`. The UI defaults to its in-browser simulator; set `VITE_WS_URL=ws://localhost:8000/ws` to use the backend dashboard socket.

### 2.3 Environment variables

`backend/.env` (loaded by `app/core/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | Returned by `/health` |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:juras123@localhost:5432/juras` | Async SQLAlchemy URL |
| `CORS_ORIGINS` | `*` in `.env.example` (code fallback: `http://localhost:5173`) | Comma-separated origins; `*` allows all |
| `SIMULATION_MAX_ACTIVE` | `3` | Max concurrently `running` simulations |
| `SIMULATION_DEFAULT_INTERVAL_MS` | `2000` | Default reading cadence |
| `SIMULATION_MIN_INTERVAL_MS` | `500` | Lower clamp |
| `SIMULATION_MAX_DURATION_SEC` | `300` | Upper clamp |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAPBOX_ACCESS_TOKEN` | empty | Search Box token for nearest-station routing |
| `MAPBOX_STATION_CACHE_SECONDS` | `600` | Station result cache TTL |

The backend currently has **no authentication**, so exposing port 8000 directly to the internet exposes write endpoints. Use a reverse proxy, VPN, or firewall rule.

---

## 3. Runtime architecture and data flow

### 3.1 Component diagram

```mermaid
flowchart LR
    subgraph Clients
        Browser["React dashboard<br/>(/api/v1 + /ws)"]
        Sensor["Field sensor / gateway<br/>(HTTP POST)"]
        Consumer["Event consumer<br/>(/ws/live)"]
    end

    subgraph FastAPI["FastAPI app (app/main.py)"]
        CORS["CORS + exception handlers"]
        API["/api/v1 routers"]
        Health["/health, /"]
        WS["/ws dashboard adapter"]
        WSL["/ws/live event bus"]
        Mgr["SimulationManager"]
        World["FrontendWorld<br/>(in-memory alerts/routes/telemetry)"]
        Bus["RealtimeBus"]
    end

    subgraph Domain
        Svc["Services<br/>reading, risk, incident, navigation, GIS"]
        Repo["Repositories<br/>(async SQLAlchemy)"]
        Rules["Risk rules + thresholds"]
    end

    DB[("PostgreSQL + PostGIS<br/>10 tables")]
    OSM["OSM GeoJSON import"]
    Mapbox["Mapbox Search Box API"]

    Browser --> CORS --> API
    Sensor --> CORS
    Consumer --> WSL
    CORS --> WS
    API --> Svc --> Repo --> DB
    Svc --> Rules
    Mgr --> Svc
    Mgr --> Bus
    Bus --> WSL
    Bus -->|adapter handler| World
    World --> WS
    API -->|closure listeners| World
    OSM --> DB
    API --> Mapbox
```

### 3.2 Startup lifecycle

`app/main.py` `lifespan()` does the following once per process:

1. Creates `SimulationManager(SessionFactory)`.
2. Creates `FrontendWorld(SessionFactory, manager)`.
3. Registers `world.handle_event` as the bus adapter handler.
4. Stores both objects in `app.api.deps` for endpoint dependencies.
5. Registers an `on_closures_changed` listener that schedules `world.replan_routes_for_closures()`.
6. Checks DB connectivity (warns but still starts if unreachable).
7. On shutdown: removes the listener, cancels replan tasks, stops simulations, cancels the `/ws` telemetry loop, clears the bus handler, disposes the engine.

> Run **one** Uvicorn worker. Simulation state, closures, alerts, and WebSocket connections are in-process memory.

### 3.3 Reading ingestion pipeline

This is the core path used by both the simulator and real sensors.

```mermaid
sequenceDiagram
    participant C as Client / sensor
    participant R as POST /api/v1/readings
    participant S as reading_service.ingest()
    participant DB as PostgreSQL/PostGIS
    participant RK as risk.rules.evaluate()
    participant I as incident_service
    participant B as RealtimeBus
    participant L as /ws/live

    C->>R: JSON ReadingCreate
    R->>R: Pydantic validation
    R->>S: payload dict
    S->>DB: resolve sensor (UUID or code)
    S->>DB: resolve building (UUID or code)
    S->>DB: resolve simulation (optional)
    S->>DB: INSERT readings
    S->>RK: evaluate(hazard, values)
    S->>DB: INSERT risk_assessments
    alt category is high or critical
        S->>I: upsert_for_risk()
        I->>DB: find active incident / INSERT incident
        I->>DB: INSERT incident_events
    end
    S-->>R: result + queued events
    R->>DB: COMMIT
    R->>B: broadcast reading.updated, risk.updated, incident.*
    B->>L: event envelope
    R-->>C: 201 {id, accepted, risk, incident_id, incident_created}
```

Exact code path:

| Step | File | What happens |
|---|---|---|
| 1 | `app/api/v1/endpoints/readings.py` | `ReadingCreate` validates hazard/source/values |
| 2 | `app/services/reading_service.py:ingest` | Resolves entities, inserts reading, scores risk, upserts incident |
| 3 | `app/risk/rules.py:evaluate` | Dispatches to fire/flood/structural evaluator |
| 4 | `app/services/incident_service.py:upsert_for_risk` | Only acts at `high`/`critical` |
| 5 | `app/api/v1/endpoints/readings.py` | Commits the explicit `SessionFactory` session |
| 6 | `app/realtime/bus.py:broadcast_event` | Sends envelope to `/ws/live`, then calls `world.handle_event` |

Important: the events are stripped from the HTTP response (`result.pop("events")`) and only delivered over `/ws/live`.

### 3.4 Navigation request flow

```mermaid
sequenceDiagram
    participant C as Dashboard
    participant R as POST /api/v1/routes/navigate
    participant N as navigation_service
    participant DB as lane/lane_node tables
    participant S as station_service
    participant M as Mapbox API
    participant G as OSM A* graph

    C->>R: origin/destination/profile
    R->>N: navigate(...)
    N->>DB: load OSM lanes + nodes
    N->>G: build graph
    alt origin_mode = nearest_station
        N->>S: nearest_stations(department)
        S->>M: Search Box category query
        M-->>S: stations
        S-->>N: nearest first (or demo fallback)
        N->>G: route from up to 6 stations
        N->>N: keep fastest/nearest valid route
    else coordinates
        N->>G: A* from given origin
    end
    N->>N: apply hazards/floods/closures
    N->>N: trim final connector at building frontage
    N-->>C: NavigateResponse
```

---

## 4. Database schema

### 4.1 Conventions

- **Primary keys:** UUID, generated client-side by SQLAlchemy (`uuid.uuid4`). Raw SQL inserts must provide `id` — there is no DB default.
- **Timestamps:** `timestamptz`; application defaults use UTC (`datetime.now(timezone.utc)`).
- **JSON:** the ORM declares `JSON`, but the Alembic migration creates `JSONB`. The migration is authoritative.
- **Coordinates:** all `pos` / `center` / `path` JSON arrays are **[longitude, latitude]** (GeoJSON order), matching SRID 4326.
- **Geometry:** PostGIS `POINT`, `LINESTRING`, `POLYGON` with GiST indexes on the geometry columns.
- **Source convention:** `attributes.source` is `demo` or `osm` for buildings/lanes; `sensors.source` and `readings.source` use `simulation`, `field`, or `imported`.
- **Soft references:** `graph_edges.lane_code`, `graph_edges.from_node`, `graph_edges.to_node`, `incidents.node_code`, and `sensors.node_code` store codes without FK constraints.

### 4.2 ER diagram

```mermaid
erDiagram
    BUILDINGS ||--o{ SENSORS : "building_id"
    BUILDINGS ||--o{ READINGS : "building_id"
    BUILDINGS ||--o{ INCIDENTS : "building_id"
    BUILDINGS ||--o{ SIMULATIONS : "target_building_id"
    SENSORS ||--o{ READINGS : "sensor_id"
    SENSORS ||--o{ SIMULATIONS : "target_sensor_id"
    SIMULATIONS ||--o{ READINGS : "simulation_id"
    SIMULATIONS ||--o{ RISK_ASSESSMENTS : "simulation_id"
    SIMULATIONS ||--o{ INCIDENTS : "simulation_id"
    INCIDENTS ||--o{ INCIDENT_EVENTS : "incident_id"
    LANE_NODES ||--o{ LANES : "node_a_code / node_b_code"
    LANES ||--o{ GRAPH_EDGES : "lane_code"
    BUILDINGS ||--o{ RISK_ASSESSMENTS : "entity_id (polymorphic)"
    LANE_NODES ||--o{ RISK_ASSESSMENTS : "entity_id (polymorphic)"
```

`risk_assessments` is polymorphic: `entity_type` is `building` or `node`; `entity_id` points at the corresponding table. The `entity_code` is denormalized for reporting.

### 4.3 `buildings`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `code` | varchar(32) | unique, not null | Human key, e.g. `B-052` |
| `name` | varchar(255) | not null | |
| `floors` | integer | not null, default 1 | |
| `building_type` | varchar(64) | not null, default `residential` | |
| `construction` | varchar(64) | not null, default `''` | |
| `occupancy` | integer | not null, default 0 | |
| `year_built` | integer | not null, default 1970 | |
| `height_m` | float | not null, default 3.3 | |
| `priority` | integer | not null, default 0 | |
| `status` | varchar(16) | not null, default `ok` | `ok`, `watch`, `inspect`, `fire` |
| `center` | JSONB | not null | `[lng, lat]` |
| `footprint` | JSONB | not null | Closed ring of `[lng, lat]` |
| `access_node_code` | varchar(32) | not null, default `''` | Nearest demo lane node code |
| `attributes` | JSONB | nullable | `source`, `tilt_deg`, `crack_mm`, `last_inspection`, `label_data`, `demo` |
| `created_at` | timestamptz | not null | |
| `geom` | geometry(POLYGON, 4326) | not null, GiST | |
| `center_point` | geometry(POINT, 4326) | not null | |

### 4.4 `lane_nodes`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `code` | varchar(32) | unique, not null | Demo nodes: `A`..`Q`; OSM: generated codes |
| `label` | varchar(255) | not null | |
| `kind` | varchar(32) | not null, default `junction` | `junction`, `fire_post`, `medical_post`, `assembly` |
| `pos` | JSONB | not null | `[lng, lat]` |
| `attributes` | JSONB | nullable | `source`, `label_data` |
| `created_at` | timestamptz | not null | |
| `geom` | geometry(POINT, 4326) | not null, GiST | |

### 4.5 `lanes`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `code` | varchar(64) | unique, not null | Demo: `A-B`; OSM: `OSM-...` |
| `name` | varchar(255) | not null | |
| `width_m` | float | not null | Used for profile access |
| `stairs` | boolean | not null, default false | |
| `slope_pct` | float | not null, default 0 | |
| `vehicle_access` | boolean | not null, default true | |
| `blocked` | boolean | not null, default false | Static flag; live closures live in `app_state` |
| `surface` | varchar(32) | not null, default `paved` | |
| `length_m` | float | not null, default 0 | |
| `node_a_code` | varchar(32) | FK → `lane_nodes.code`, not null | |
| `node_b_code` | varchar(32) | FK → `lane_nodes.code`, not null | |
| `path` | JSONB | not null | Ordered `[lng, lat]` vertices |
| `attributes` | JSONB | nullable | `source`, OSM tags, `width_verified`, `label_data` |
| `created_at` | timestamptz | not null | |
| `geom` | geometry(LINESTRING, 4326) | not null, GiST | |

### 4.6 `graph_edges`

Directed edge table used by the legacy demo-grid Dijkstra path.

| Column | Type | Constraints / default |
|---|---|---|
| `id` | UUID | PK |
| `from_node` | varchar(32) | not null, indexed |
| `to_node` | varchar(32) | not null, indexed |
| `lane_code` | varchar(64) | not null |
| `length_m` | float | not null, default 0 |
| `cost` | float | not null, default 0 |
| `width_m` | float | not null, default 0 |
| `stairs` | boolean | not null, default false |
| `slope_pct` | float | not null, default 0 |
| `vehicle_access` | boolean | not null, default true |
| `blocked` | boolean | not null, default false |
| `created_at` | timestamptz | not null |

### 4.7 `sensors`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | Raw SQL must supply it |
| `code` | varchar(32) | unique, not null | Device key, e.g. `JM-052`, `FIELD-B052-F1` |
| `label` | varchar(255) | not null | |
| `kind` | varchar(32) | not null, indexed | `smoke_temp`, `structure`, `rain_level` |
| `building_id` | UUID | FK → `buildings.id`, nullable | Null for node-mounted rain sensors |
| `node_code` | varchar(32) | nullable | Set for flood/rain sensors |
| `status` | varchar(16) | not null, default `active` | Not currently enforced during ingestion |
| `source` | varchar(16) | not null, default `simulation` | Use `field` for hardware |
| `pos` | JSONB | not null | `[lng, lat]` |
| `attributes` | JSONB | nullable | `flood_factor`, vendor metadata |
| `created_at` | timestamptz | not null | |
| `geom` | geometry(POINT, 4326) | not null, GiST | |

Indexes: `ix_sensors_kind`, `ix_sensors_geom` (GiST).

### 4.8 `readings`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `sensor_id` | UUID | FK → `sensors.id`, nullable | |
| `building_id` | UUID | FK → `buildings.id`, nullable | |
| `simulation_id` | UUID | FK → `simulations.id`, nullable | |
| `hazard` | varchar(32) | not null | `fire`, `flood`, `structural` |
| `values` | JSONB | not null | Raw measurement map |
| `observed_at` | timestamptz | not null | Device time or server now |
| `received_at` | timestamptz | not null, default now | Server receipt time |
| `source` | varchar(16) | not null, default `simulation` | `simulation`, `field`, `imported` |
| `simulation` | boolean | not null, default true | Real hardware must send `false` |

Indexes: `ix_readings_sensor_observed (sensor_id, observed_at)`, `ix_readings_building_observed (building_id, observed_at)`.

### 4.9 `risk_assessments`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `entity_type` | varchar(16) | not null | `building` or `node` |
| `entity_id` | UUID | not null | No FK (polymorphic) |
| `entity_code` | varchar(64) | not null | e.g. `B-052`, `I` |
| `hazard` | varchar(32) | not null | |
| `score` | integer | not null, 0–100 check | |
| `category` | varchar(16) | not null | `normal`…`critical` |
| `reasons` | JSONB | nullable | List of rule objects |
| `assessed_at` | timestamptz | not null | Equals reading `observed_at` |
| `simulation_id` | UUID | FK → `simulations.id`, nullable | |
| `rule_version` | varchar(16) | not null, default `demo-v1` | |
| `created_at` | timestamptz | not null | |

Constraint: `ck_risk_score_range` (`score >= 0 AND score <= 100`).
Index: `ix_risk_entity_time (entity_type, entity_id, assessed_at)`.

### 4.10 `simulations`

| Column | Type | Constraints / default |
|---|---|---|
| `id` | UUID | PK |
| `scenario` | varchar(32) | not null, indexed |
| `target_building_id` | UUID | FK → `buildings.id`, nullable, indexed |
| `target_node_code` | varchar(32) | nullable |
| `target_sensor_id` | UUID | FK → `sensors.id`, nullable |
| `severity` | varchar(16) | not null, default `warning` |
| `seed` | integer | not null, default 42 |
| `status` | varchar(16) | not null, default `queued`, indexed |
| `interval_ms` | integer | not null, default 2000 |
| `duration_sec` | integer | not null, default 60 |
| `started_at` | timestamptz | nullable |
| `ended_at` | timestamptz | nullable |
| `actor` | varchar(64) | not null, default `dashboard` |
| `error_code` | varchar(64) | nullable |
| `attributes` | JSONB | nullable |

No `created_at` column on this table.

### 4.11 `incidents`

| Column | Type | Constraints / default | Notes |
|---|---|---|---|
| `id` | UUID | PK | |
| `code` | varchar(64) | unique, not null | e.g. `AL-FIRE-B-052` |
| `hazard` | varchar(32) | not null, indexed | |
| `building_id` | UUID | FK → `buildings.id`, nullable, indexed | |
| `node_code` | varchar(32) | nullable | Set for node-target incidents |
| `severity` | varchar(16) | not null, default `medium` | `low`…`critical` |
| `status` | varchar(16) | not null, default `open`, indexed | |
| `title` | varchar(255) | not null | |
| `description` | varchar(1024) | not null, default `''` | |
| `source` | varchar(16) | not null, default `simulation` | |
| `simulation_id` | UUID | FK → `simulations.id`, nullable, indexed | |
| `opened_at` | timestamptz | not null | |
| `acknowledged_at` | timestamptz | nullable | |
| `resolved_at` | timestamptz | nullable | |
| `pos` | JSONB | not null | `[lng, lat]` |
| `created_at` | timestamptz | not null | |
| `geom` | geometry(POINT, 4326) | not null, GiST | |

### 4.12 `incident_events`

| Column | Type | Constraints / default |
|---|---|---|
| `id` | UUID | PK |
| `incident_id` | UUID | FK → `incidents.id`, not null, indexed |
| `action` | varchar(32) | not null |
| `old_status` | varchar(16) | nullable |
| `new_status` | varchar(16) | nullable |
| `actor` | varchar(64) | not null, default `system` |
| `note` | varchar(1024) | not null, default `''` |
| `created_at` | timestamptz | not null |

Actions observed in code: `opened`, `status_changed`, `severity_escalated`, `dispatched`.

### 4.13 Seed inventory (verified live)

| Item | Count |
|---|---|
| Buildings | 90 (14 demo + 76 OSM) |
| Lane nodes | 1,093 (17 demo + OSM) |
| Lanes | 725 (25 demo + 700 OSM) |
| Sensors | 14 |
| Readings | 2 |
| Risk assessments | 2 |
| Incidents | 3 |
| Simulations | 0 initially |

Seeded sensors:

| Code | Kind | Attached to |
|---|---|---|
| `JM-014` | `smoke_temp` | B-014 |
| `JM-021a`, `JM-021b` | `smoke_temp` | B-021 |
| `JM-052` | `smoke_temp` | B-052 |
| `JM-066` | `smoke_temp` | B-066 |
| `JM-073` | `smoke_temp` | B-073 |
| `JM-095` | `smoke_temp` | B-095 |
| `JM-S07` | `structure` | B-007 |
| `JM-S52` | `structure` | B-052 |
| `JM-S73` | `structure` | B-073 |
| `JM-S81` | `structure` | B-081 |
| `JM-R01` | `rain_level` | node I (`flood_factor` 1.0) |
| `JM-R02` | `rain_level` | node O (`flood_factor` 0.6) |
| `JM-R03` | `rain_level` | node M (`flood_factor` 0.8) |

Demo lane nodes `A`..`Q` include `A` (fire_post), `E` (medical_post), and `G`/`Q` (assembly). These are used by the simulator's response routes.

---

## 5. REST API conventions

- **Base URL:** `http://localhost:8000`
- **Prefix:** every business endpoint is under `/api/v1`. `/health` and `/` are at the root.
- **Content type:** `application/json` for all request bodies.
- **Authentication:** none.
- **CORS:** from `CORS_ORIGINS`, credentials disabled, methods include GET/POST/PATCH/PUT/DELETE/OPTIONS.
- **IDs:** most lookup endpoints accept **either a UUID or a human code**. Notable exception: `GET /api/v1/sensors?building_id=` expects a UUID.
- **Errors:** uniform envelope:

```json
{
  "error": {
    "code": "SENSOR_NOT_FOUND",
    "message": "Sensor X does not exist",
    "request_id": "a random UUID"
  }
}
```

- **Validation errors:** HTTP 422 with code `VALIDATION_ERROR`.
- **Case:** enums are lowercase (`fire`, `field`, `critical`).

Common error codes:

| Code | HTTP | Cause |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Pydantic/body validation failed |
| `TARGET_REQUIRED` | 400 | No sensor/building or simulation target |
| `SENSOR_NOT_FOUND` | 404 | Unknown sensor UUID/code, or the target building has no sensor of the hazard's kind |
| `BUILDING_NOT_FOUND` | 404 | Unknown building UUID/code |
| `NODE_NOT_FOUND` | 404 | Unknown lane node code |
| `SIMULATION_NOT_FOUND` | 404 | Unknown simulation |
| `INCIDENT_NOT_FOUND` | 404 | Unknown incident UUID/code |
| `CLOSURE_NOT_FOUND` | 404 | Unknown closure id |
| `INVALID_TRANSITION` | 400 | Illegal incident status change |
| `SIMULATION_LIMIT` | 409 | Max active simulations reached |
| `SIMULATION_ALREADY_RUNNING` | 409 | Same scenario already active on building |
| `INVALID_PROFILE` | 422 | Routing profile not supported |
| `INTERNAL_ERROR` | 500 | Unhandled exception |

---

## 6. Complete REST endpoint map

### 6.1 System

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Project status |
| GET | `/health` | Health + DB check |
| GET | `/api/v1/health` | Same handler under the API prefix |
| GET | `/docs` | Swagger UI |
| GET | `/openapi.json` | OpenAPI document |

### 6.2 Data & sensors

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/buildings` | Buildings as GeoJSON |
| GET | `/api/v1/buildings/{building_id}` | Building detail + latest reading/risk |
| GET | `/api/v1/lanes` | Lanes as GeoJSON |
| GET | `/api/v1/lanes/nodes` | Lane nodes as GeoJSON |
| GET | `/api/v1/sensors` | List sensors |
| GET | `/api/v1/readings/latest` | Latest reading per hazard for one building |
| GET | `/api/v1/readings` | Historical readings with filters |
| POST | `/api/v1/readings` | **Ingest a reading (real sensors use this)** |

### 6.3 Risk & incidents

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/risks` | Latest risk per entity+hazard |
| GET | `/api/v1/incidents` | List incidents (JSON or GeoJSON) |
| GET | `/api/v1/incidents/{incident_id}` | Incident + audit events |
| PATCH | `/api/v1/incidents/{incident_id}` | Change status with note/actor |
| GET | `/api/v1/incidents/{incident_id}/events` | Audit events only |

### 6.4 Simulations

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/simulations` | Start fire/flood/structural simulation |
| GET | `/api/v1/simulations` | List simulations (optional `status`) |
| GET | `/api/v1/simulations/{simulation_id}` | Describe one simulation |
| POST | `/api/v1/simulations/{simulation_id}/stop` | Stop a simulation |

### 6.5 Routing

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/routes/closures` | List in-memory closures |
| POST | `/api/v1/routes/closures` | Add closure + trigger WS replan |
| DELETE | `/api/v1/routes/closures/{closure_id}` | Remove one closure |
| DELETE | `/api/v1/routes/closures` | Remove all closures |
| GET | `/api/v1/routes/stations` | Nearest Mapbox stations |
| POST | `/api/v1/routes/navigate` | OSM navigation (production path) |
| POST | `/api/v1/routes` | Legacy demo-grid route |

### 6.6 WebSockets

| Path | Purpose |
|---|---|
| `/ws` | Dashboard contract: snapshot, telemetry, alerts, routes |
| `/ws/live` | Raw event bus: `reading.updated`, `risk.updated`, `incident.*`, `simulation.*` |

---

## 7. Endpoint-by-endpoint behaviour

### 7.1 `GET /` and `GET /health`

- `GET /` returns `{"project":"JURAS","pilot":"Purani Mandi","status":"running","docs":"/docs"}`.
- `/health` calls `check_db()` (`SELECT 1`) and returns:

```json
{
  "status": "healthy",
  "db": true,
  "app_env": "development",
  "project": "JURAS",
  "pilot": "Purani Mandi",
  "data_label": "illustrative demo data, not surveyed Purani Mandi geometry"
}
```

`status` becomes `degraded` if the DB check fails.

### 7.2 `GET /api/v1/buildings`

Query parameters:

| Param | Type | Default | Behaviour |
|---|---|---|---|
| `bbox` | `minlon,minlat,maxlon,maxlat` | none | PostGIS `ST_Intersects` filter |
| `limit` | 1–500 | 200 | Applied |
| `source` | `demo` or `osm` | none | Filters on `attributes.source` |

Response: GeoJSON `FeatureCollection`. Each feature has `id = building.code`, Polygon geometry, and properties including `name`, `floors`, `building_type`, `construction`, `occupancy`, `year_built`, `height_m`, `priority`, `status`, `center`, `access_node`, `simulation`, `source`, `label`, and optional `risk` `{score, category, hazard}`.

`simulation` is `true` only when `attributes.source == "demo"`.

### 7.3 `GET /api/v1/buildings/{building_id}`

Accepts UUID or code. Runs:

1. `building_repo.get_by_id` (UUID → code fallback).
2. `reading_repo.latest_per_kind_for_building` (latest 50 readings, one per hazard).
3. `risk_repo.latest_for_entity("building", id)`.

Returns the full flat building object with `latest_reading`, `latest_risk`, `attributes`, `footprint`, `access_node`, `simulation`, `source`, `label`. 404 `BUILDING_NOT_FOUND` if missing.

### 7.4 `GET /api/v1/lanes`

Query: `bbox`, `blocked`, `accessible_to`, `source`.

- `accessible_to` filters width/stairs:
  - `foot_responder`: `width_m >= 0.9`
  - `ambulance`: `width_m >= 1.2` **and** `stairs = false`
  - `fire_vehicle`: `width_m >= 3.5` **and** `stairs = false`
- `source` filters `attributes.source`.
- `bbox` is accepted but **ignored** in the current implementation.
- Returns a GeoJSON `FeatureCollection`; properties include width, stairs, slope, vehicle access, blocked, surface, length, node codes, and source.

### 7.5 `GET /api/v1/lanes/nodes`

Returns all lane nodes as GeoJSON Points. `source` filters on `attributes.source`; nodes with no source are treated as `demo`. Properties: `id` (code), `label`, `kind`, `simulation`.

### 7.6 `GET /api/v1/sensors`

Query: `building_id`, `type`, `status`.

- `type` maps to `Sensor.kind` (`smoke_temp`, `structure`, `rain_level`).
- `building_id` is treated as a **UUID only** by `sensor_repo.list_sensors`. Passing `B-052` returns an empty list.
- Response is a JSON array (not wrapped):

```json
[
  {
    "id": "uuid",
    "code": "JM-052",
    "label": "Smoke + temp, B-052",
    "kind": "smoke_temp",
    "building_id": "uuid",
    "node_code": null,
    "status": "active",
    "source": "simulation",
    "pos": [74.85867, 32.72751],
    "attributes": {},
    "simulation": true
  }
]
```

The `"simulation": true` flag is hardcoded in this endpoint.

### 7.7 `GET /api/v1/readings/latest`

Query: `building_id` (required in practice), `sensor_type`.

- If `building_id` is missing or unknown → `{"readings": [], "simulation": true}`.
- Resolves the building by UUID **or code**, then returns the latest reading per hazard.
- `sensor_type` is compared against the **hazard** (`fire`, `flood`, `structural`), not the sensor kind.
- Envelope always says `"simulation": true`, even when individual readings have `simulation: false`.

### 7.8 `GET /api/v1/readings`

Query:

| Param | Default | Behaviour |
|---|---|---|
| `building_id` | none | UUID or code; unknown → empty page |
| `sensor_id` | none | UUID or code; unknown → empty page |
| `from` | none | ISO timestamp, inclusive |
| `to` | none | ISO timestamp, inclusive |
| `limit` | 200 (1–1000) | Passed to SQL |

Returns `{"items": [ReadingOut...], "limit": N, "simulation": true}`. Each item has the real per-row `source` and `simulation` values.

### 7.9 `POST /api/v1/readings` — the ingestion endpoint

This is the supported real-hardware path. Full details, payloads, and device examples are in [section 10](#10-real-sensors--complete-onboarding).

Request schema (`ReadingCreate`):

| Field | Type | Default | Rules |
|---|---|---|---|
| `sensor_id` | string | null | UUID or sensor code; 404 if unknown |
| `building_id` | string | null | UUID or building code; 404 if unknown |
| `simulation_id` | string | null | UUID; 404 if unknown |
| `hazard` | string | `fire` | `fire`, `flood`, `structural` |
| `values` | object of floats | `{}` | Must not be empty |
| `observed_at` | ISO datetime | server UTC now | Naive datetimes are accepted as-is |
| `source` | string | `simulation` | `simulation`, `field`, `imported` |
| `simulation` | boolean | `true` | Set `false` for hardware |

Target resolution order inside `ingest()`:

1. If `sensor_id` is given, resolve by UUID then code. When `building_id` is omitted, a building-mounted sensor supplies its own building.
2. If a building id is now known, resolve it by UUID then code.
3. If `simulation_id` is given, resolve it.
4. If no sensor was given but a building was, pick the building's first sensor of the hazard's kind. If the building has no sensor of that kind → `SENSOR_NOT_FOUND` (404).
5. If neither a sensor nor a building can be resolved → `TARGET_REQUIRED` (400).

Response `201`:

```json
{
  "id": "reading UUID",
  "accepted": true,
  "risk": { "...": "or null" },
  "incident_id": "incident UUID or null",
  "incident_created": false
}
```

`risk` is `null` when there is no risk target or the reading could not be tied to a building/node. `incident_created` is `true` only for the first incident opened for that target + hazard.

> **Building fallback:** a building-mounted sensor can be posted with `sensor_id` alone. The reading inherits the sensor's `building_id`, so risk and incidents are produced for that building. Sending both IDs explicitly is still recommended for auditability. Flood sensors mounted on a lane node work with `sensor_id` alone because the risk target is `sensor.node_code`.

### 7.10 `GET /api/v1/risks`

Query: `entity_type`, `category`, `bbox`.

- Loads the latest 200 assessments.
- Deduplicates in Python by `entity_type:entity_id:hazard`, keeping the newest.
- Applies `entity_type` and `category` filters.
- **`bbox` is accepted but ignored.**
- Response: `{"items": [...], "rule_version": "demo-v1", "label": "Illustrative demo scores, not calibrated probability"}`.

### 7.11 Incidents

`GET /api/v1/incidents`:

| Param | Values |
|---|---|
| `status` | `open`, `acknowledged`, `resolved`, `false_alarm` |
| `hazard` | `fire`, `flood`, `structural` |
| `severity` | `low`, `medium`, `high`, `critical` |
| `format` | `json` (default) or `geojson` |

JSON: `{"items": [IncidentOut...]}`. GeoJSON: `FeatureCollection` with Point features.

`GET /api/v1/incidents/{incident_id}` accepts UUID or code. Returns `{"incident": {...}, "events": [...]}`.

`PATCH /api/v1/incidents/{incident_id}` body:

```json
{
  "status": "acknowledged",
  "note": "Crew dispatched",
  "actor": "operator"
}
```

Allowed transitions:

| From | To |
|---|---|
| `open` | `acknowledged`, `resolved`, `false_alarm` |
| `acknowledged` | `resolved`, `false_alarm` |
| `resolved` | none |
| `false_alarm` | none |

Sets `acknowledged_at` or `resolved_at`; appends a `status_changed` audit event; emits `incident.updated` on the bus.

`GET /api/v1/incidents/{incident_id}/events` returns `{"items": [...]}`.

### 7.12 Simulations

`POST /api/v1/simulations`:

| Field | Required | Default / bounds |
|---|---|---|
| `scenario` | yes | `fire`, `flood`, `structural` |
| `target_building_id` | fire/structural | UUID or code |
| `target_node_code` | flood | Lane node code with a `rain_level` sensor |
| `severity` | no | `normal`, `warning`, `critical` |
| `duration_sec` | no | 5–300, clamped to `SIMULATION_MAX_DURATION_SEC` |
| `interval_ms` | no | 500–10000, clamped to minimum |
| `seed` | no | random if omitted |
| `actor` | no | `dashboard` |

Rules enforced in `SimulationManager.start()`:

- At most `SIMULATION_MAX_ACTIVE` running simulations (409 `SIMULATION_LIMIT`).
- Fire/structural require a building with a `smoke_temp`/`structure` sensor, and only one active simulation per building+scenario (409 `SIMULATION_ALREADY_RUNNING`).
- Flood requires a node with a `rain_level` sensor.

Each tick writes a reading with `source="simulation"`, `simulation=true`, and the simulation UUID, then runs the same risk/incident pipeline.

Other endpoints:

- `GET /api/v1/simulations?status=running` → array of simulation descriptions.
- `GET /api/v1/simulations/{id}` → one description.
- `POST /api/v1/simulations/{id}/stop` → cancels the task and marks `stopped`.

### 7.13 Closures

Closures are **in-memory** (`app/state.py`), not in the database, and are lost on restart.

`POST /api/v1/routes/closures`:

```json
{
  "lat": 32.7285,
  "lng": 74.8585,
  "radius_m": 15,
  "reason": "Drainage work",
  "source": "manual"
}
```

Constraints: `radius_m` 5–100; `source` is `manual` or `simulated`.

Response:

```json
{
  "id": "closure-1",
  "lat": 32.7285,
  "lng": 74.8585,
  "pos": [74.8585, 32.7285],
  "radius_m": 15.0,
  "reason": "Drainage work",
  "source": "manual",
  "active": true
}
```

Adding/removing a closure fires `app_state._notify_closures_changed()`. The lifespan listener schedules `world.replan_routes_for_closures()`, which recomputes every active fire response route so `/ws` never keeps a route through the new closure.

`GET /api/v1/routes/closures` → `{"count": N, "closures": [...]}`.
`DELETE /api/v1/routes/closures/{id}` → `{"removed": id}` or 404.
`DELETE /api/v1/routes/closures` → `{"removed": "all"}`.

### 7.14 `GET /api/v1/routes/stations`

Query: `department` (`fire`, `medical`, `police`), `lat`, `lng`, `limit` (1–10, default 8).

- Calls Mapbox Search Box category search with the configured token.
- Caches results for `MAPBOX_STATION_CACHE_SECONDS`.
- Rejects stations farther than 30 km straight-line.
- If Mapbox is unavailable or unconfigured, falls back to demo `fire_post` / `medical_post` nodes. Police has no fallback.
- Response: `{"department", "count", "source", "stations": [...]}`.

### 7.15 `POST /api/v1/routes/navigate` — production routing

Request:

```json
{
  "origin": { "lat": 32.7285, "lng": 74.8575 },
  "destination": { "lat": 32.72747, "lng": 74.85879 },
  "destination_building_id": "B-052",
  "profile": "fire_truck",
  "weighting": "time",
  "avoid_hazards": true,
  "department": null,
  "origin_mode": "coordinates"
}
```

| Field | Rules |
|---|---|
| `origin` | Required when `origin_mode = coordinates` |
| `destination` | Always required |
| `destination_building_id` | Optional; when set, final connector is trimmed at the building frontage |
| `profile` | `fire_truck`, `responder_bike`, `walking` |
| `weighting` | `time` or `distance` |
| `avoid_hazards` | Uses active hazards/floods/closures when true |
| `origin_mode` | `coordinates` or `nearest_station` |
| `department` | Required for `nearest_station`; `fire`, `medical`, `police` |

Response keys:

- `route`: GeoJSON `Feature` with `LineString` and properties:
  `distance_m`, `duration_s`, `profile`, `weighting`, `algorithm` (`astar_osm`), `duration_basis`, `geometry_source` (`openstreetmap`), `edge_count`, `edge_ids`, `warnings`, `origin_snap_distance_m`, `destination_snap_distance_m`, `road_distance_m`, `road_duration_s`, `access_distance_m`, `access_duration_s`, `egress_distance_m`, `egress_duration_s`, `closures_considered`, `steps`.
- `origin` and `destination`: snap objects with `lat`, `lng`, `snapped`, `snap_distance_m`, `edge_id`, `way_id`, `road_name`, `highway`, `oneway`.
- `warnings`, `origin_station`, `stations_considered`.

For `origin_mode = nearest_station`, the backend lists Mapbox stations nearest to the **destination**, routes from up to six of them, and keeps the fastest (or shortest) feasible route. The chosen station is returned in `origin_station`.

Building frontage behaviour: when `destination_building_id` resolves to a building with a footprint, `trim_route_to_entrance` replaces the final centre-bound connector with a stop at the street-facing footprint edge and updates the returned destination coordinates to that gate. This is what makes B-052 routes end at the frontage rather than the building centre.

### 7.16 `POST /api/v1/routes` — legacy demo-grid route

Body:

```json
{
  "origin": { "lat": 32.7285, "lon": 74.8575 },
  "destination_building_id": "B-052",
  "responder_type": "fire_vehicle"
}
```

- Loads the `lanes` + `lane_nodes` tables (demo grid plus imported OSM rows) and runs Dijkstra; it does **not** use the dedicated OSM navigation graph or its A* implementation.
- `responder_type`: `fire_vehicle`, `ambulance`, `foot_responder`; mapped to profiles `fire_truck`, `medical`, `evacuation`.
- Without an origin, starts at fire post `A` (fire truck) or medical post `E`.
- If the destination is unreachable, stops at the nearest reachable node and adds a warning; if nothing is reachable, returns `feasible: false` with an empty geometry.
- Response: `route_id`, `responder_type`, `profile`, `geometry`, `distance_m`, `travel_s`, `eta_s`, `edge_ids`, `warnings`, `algorithm`, `feasible`, `last_mile_m`, `note`.

---

## 8. WebSocket contracts

Two sockets with different audiences:

| | `/ws` | `/ws/live` |
|---|---|---|
| Consumer | Dashboard UI | Backend/debug/event consumers |
| Initial message | Full snapshot | None |
| Message shape | `{"t": "...", ...}` | `{"event_id", "event", "version", "occurred_at", "simulation", "data"}` |
| Client commands | Scenario + alert action | Only text `ping`/`heartbeat` |
| Data source | In-process simulator/fusion | All bus events |
| Auth | None | None |

### 8.1 `/ws` — connect and snapshot

On connect the server:

1. Accepts the socket.
2. Starts the telemetry loop if not running (one loop per `FrontendWorld`).
3. Loads the world once from the DB if not loaded (buildings, nodes, lanes, sensors, incidents, demo graph, OSM graph).
4. Sends a `snapshot`.
5. Registers the socket for broadcasts.

Snapshot shape:

```json
{
  "t": "snapshot",
  "buildings": [
    {
      "id": "B-052",
      "name": "Mubarak Dharamshala",
      "center": [74.85867, 32.72751],
      "footprint": [[74.8586, 32.7274]],
      "floors": 3,
      "height_m": 9.9,
      "year_built": 1936,
      "use": "Institutional",
      "construction": "Stone masonry",
      "occupancy": 80,
      "priority": 77,
      "status": "watch",
      "tilt_deg": 0.18,
      "crack_mm": 0.2,
      "last_inspection": "2025-05-30",
      "access_node": "L"
    }
  ],
  "lane_nodes": [
    { "id": "A", "pos": [74.8543, 32.7271], "label": "Fire Post (demo)", "kind": "fire_post" }
  ],
  "lane_edges": [
    { "id": "A-B", "a": "A", "b": "B", "width_m": 7.0, "stairs": false }
  ],
  "sensors": [
    { "node_id": "JM-052", "kind": "smoke_temp", "pos": [74.85867, 32.72751], "label": "Smoke + temp, B-052", "building_id": "B-052" }
  ],
  "alerts": [
    { "id": "AL-FIRE-B-052", "module": "fire", "severity": "critical", "status": "new" }
  ],
  "routes": {
    "AL-FIRE-B-052": [
      {
        "profile": "fire_truck",
        "path": [[74.8575, 32.7285]],
        "foot_path": [],
        "length_m": 0,
        "travel_s": 0,
        "eta_s": 0,
        "feasible": true,
        "last_mile_m": 0,
        "note": "OSM road route to Mubarak Dharamshala.",
        "from": "Fire post",
        "to": "Mubarak Dharamshala",
        "steps": []
      }
    ]
  },
  "hazards": [
    { "id": "HZ-B-052", "kind": "fire", "pos": [74.85867, 32.72751], "radius_m": 22.5, "active": true }
  ],
  "flood_zones": [],
  "interventions": []
}
```

Snapshot arrays are truncated above; real payloads contain all loaded rows. `sensor.node_id` is the sensor **code**, not a UUID. `sensors[].building_id` is a building code.

### 8.2 `/ws` — server messages

| `t` | Payload keys | When |
|---|---|---|
| `snapshot` | `buildings`, `lane_nodes`, `lane_edges`, `sensors`, `alerts`, `routes`, `hazards`, `flood_zones`, `interventions` | Once after connect |
| `telemetry` | `items` | Every 1 second |
| `building` | `id`, `patch` | Building status changes |
| `alert` | `alert` | Fusion creates/updates an alert |
| `routes` | `alert_id`, `routes` | Routes planned/replanned/cleared |
| `hazard` | `hazard` | Fire hazard radius changes |
| `flood` | `zones`, `interventions` | Flood scenario updates |

Telemetry item shapes:

```json
{
  "node_id": "JM-052",
  "kind": "smoke_temp",
  "ts": 1763450000000,
  "battery": 87.4,
  "values": { "smoke_ppm": 35, "temp_c": 31.5 }
}
```

| Kind | `values` keys |
|---|---|
| `smoke_temp` | `smoke_ppm`, `temp_c` |
| `structure` | `tilt_deg`, `crack_mm`, `vib_rms` |
| `rain_level` | `rain_mmh`, `level_cm` |

> The dashboard telemetry uses `temp_c` and `level_cm`. The REST risk engine uses `temperature_c` and `water_level_cm`. Do not copy telemetry key names into `POST /readings`.

Live alert object:

```json
{
  "id": "AL-FIRE-B-052",
  "module": "fire",
  "severity": "critical",
  "status": "new",
  "title": "Fire confirmed, B-052",
  "detail": "Mubarak Dharamshala, 3 floors, about 80 occupants. Simulated data.",
  "building_id": "B-052",
  "pos": [74.85867, 32.72751],
  "confidence": 0.86,
  "sources": [
    { "kind": "sensor", "label": "JM-052: smoke 420 ppm, 62 °C", "ts": 1763450000000 },
    { "kind": "citizen", "label": "Citizen report: smoke from upper floor", "ts": 1763450014000 }
  ],
  "created_at": 1763450000000,
  "updated_at": 1763450022000,
  "dispatched_at": null,
  "recommendation": "Evacuate via the route shown. Simulated demo, not a real emergency."
}
```

Alert statuses: `new`, `ack`, `dispatched`, `resolved`. Modules: `fire`, `flood`, `structure`.

### 8.3 `/ws` — client commands

```json
{ "cmd": "scenario", "name": "fire" }
{ "cmd": "scenario", "name": "crack" }
{ "cmd": "scenario", "name": "flood" }
{ "cmd": "scenario", "name": "reset" }
{ "cmd": "alert_action", "id": "AL-FIRE-B-052", "action": "ack" }
{ "cmd": "alert_action", "id": "AL-FIRE-B-052", "action": "dispatch" }
{ "cmd": "alert_action", "id": "AL-FIRE-B-052", "action": "resolve" }
```

Behaviour:

- `scenario: fire` starts a 90 s warning simulation on the next building in the fire pick list.
- `scenario: crack` starts a structural simulation.
- `scenario: flood` starts a flood simulation at node `I` if none is active.
- `scenario: reset` clears alerts/routes/hazards/zones, resets sensor levels, and marks open/acknowledged incidents resolved in the DB.
- `alert_action` first tries to find a matching DB incident by alert id/prefix, then falls back to the in-memory alert. `ack` → acknowledged, `dispatch` → acknowledged + dispatch event (or `dispatched` on the live alert), `resolve` → resolved and clears routes/hazard.

Invalid JSON frames are ignored. There is no per-client subscription model; every connected UI receives every broadcast.

### 8.4 `/ws/live` — raw event bus

On connect: no snapshot. The server only forwards future bus events. Sending `ping` or `heartbeat` returns the text `pong`.

Envelope:

```json
{
  "event_id": "uuid",
  "event": "reading.updated",
  "version": 1,
  "occurred_at": "2026-11-18T10:15:00+00:00",
  "simulation": true,
  "data": {}
}
```

> The envelope's `simulation` field defaults to `true` in `bus.broadcast_event` and is not derived from the reading. Check `data.simulation` for the real per-reading flag.

Events:

| Event | Emitted by | `data` keys |
|---|---|---|
| `reading.updated` | `POST /readings`, simulation ticks | `reading_id`, `building_id`, `building_code`, `sensor_code`, `type`, `values`, `observed_at`, `simulation`, `simulation_id` |
| `risk.updated` | Same | Full risk object: `entity_type`, `entity_id`, `entity_code`, `building_id`, `building_code`, `hazard`, `score`, `category`, `reasons`, `assessed_at`, `rule_version`, `simulation`, `simulation_id` |
| `incident.created` | First high/critical assessment | IncidentOut |
| `incident.updated` | Escalation or PATCH/alert action | IncidentOut (sometimes `escalated: true`) |
| `simulation.started` | Simulation manager | `simulation_id`, `scenario`, `target_building_id`, `target_building_code`, `target_node_code`, `severity`, `status`, `simulation` |
| `simulation.completed` | Simulation manager | `simulation_id`, `scenario`, `status`, `ended_at` |
| `simulation.failed` | Simulation manager | `simulation_id`, `scenario`, `status`, `error_code` |

Example `reading.updated`:

```json
{
  "event_id": "0f7b...",
  "event": "reading.updated",
  "version": 1,
  "occurred_at": "2026-11-18T10:15:00+00:00",
  "simulation": true,
  "data": {
    "reading_id": "8a1c...",
    "building_id": "5ef3...",
    "building_code": "B-052",
    "sensor_code": "FIELD-B052-F1",
    "type": "fire",
    "values": { "smoke_level": 88, "temperature_c": 95, "smoke_ppm": 880 },
    "observed_at": "2026-11-18T10:15:00+00:00",
    "simulation": false,
    "simulation_id": null
  }
}
```

### 8.5 Closure-triggered route replanning

The route replan loop is real and verified:

1. Operator calls `POST /api/v1/routes/closures` (or delete/clear).
2. `AppState` notifies listeners.
3. `main.py` schedules `world.replan_routes_for_closures()`.
4. For every stored alert route with an active fire hazard, `plan_osm_routes_for_building` reruns with the latest closure list.
5. The new route list is pushed as `{"t":"routes","alert_id":...,"routes":[...]}`.

The navigation API reads `app_state.routing_ctx()` directly on every call, so it does not need a replan trigger.

### 8.6 B-052 frontage regression check

Reference values recorded during verification:

| Route | Last coordinate `[lng, lat]` |
|---|---|
| `POST /api/v1/routes/navigate` to B-052 | `[74.85879075405327, 32.727468208895836]` |
| `/ws` fire route for B-052 | `[74.85879218490025, 32.727461336383655]` |
| `/ws` medical route for B-052 | `[74.85879218490025, 32.727461336383655]` |

The exact last coordinate moves slightly with the requested destination point because the gate is projected from it. The invariant is that the final point lies on the street-facing footprint edge, not the building centre. Routes for other buildings follow the same trim logic.

---

## 9. Routing engine

There are two routing implementations:

| Engine | Used by | Graph | Algorithm |
|---|---|---|---|
| Legacy graph | `POST /api/v1/routes` | `lanes` + `lane_nodes` (all rows) | Dijkstra |
| OSM navigation | `POST /api/v1/routes/navigate`, `/ws` fire/medical/evacuation | OSM lanes (`attributes.source = osm`) | A* |

### 9.1 OSM graph build

`app/routing/osm_graph.py`:

- Reads OSM lanes and their `attributes` (highway, oneway, maxwidth, maxheight, access tags, `width_verified`).
- Builds directed edges honouring one-way tags.
- Applies profile access rules.
- Speeds come from an OSM highway-class table; there is no live traffic.
- The API rebuilds the graph on each navigation request. The `/ws` world builds it once at startup.

Profiles:

| Profile | Min lane width | Vehicle width | Vehicle height | Default speed |
|---|---|---|---|---|
| `fire_truck` | 3.5 m | 2.5 m | 3.2 m | 12 km/h |
| `responder_bike` | 1.2 m | 0.8 m | 2.0 m | 12 km/h |
| `walking` | 0.9 m | — | — | 4.5 km/h |

Department → routing profile for nearest-station mode:

| Department | Profile |
|---|---|
| `fire` | `fire_truck` |
| `medical` | `responder_bike` |
| `police` | `responder_bike` |

### 9.2 Snapping and connectors

- Requested origin/destination points are snapped to the nearest OSM edge.
- The first and last connector are drawn as straight lines so the returned geometry starts at the requested origin and ends at the requested destination.
- Connector walking speed is 1.3 m/s.
- Gaps over 25 m produce a warning; they are not fabricated roads.
- If a building footprint is supplied, the final connector is trimmed at the street-facing edge (front gate).
- No route is ever drawn on the synthetic demo grid by this engine; if the OSM graph is empty, navigation raises `OSM_GRAPH_EMPTY`.

### 9.3 Hazards, floods, closures

`app/state.py` holds:

- `hazards`: fire zones with `pos`, `radius_m`, `active`.
- `flood_zones`: with `pos`, `radius_m`, `depth_cm`.
- `closures`: with `pos`, `radius_m`, `active`.

Routing context is passed into `compute_navigation`:

- Closure: an edge is removed when the closure point is within `radius_m` of the edge path.
- Fire hazard: edges within the hazard radius + 10 m get a ×6 cost multiplier.
- Flood: edges within the flood radius + 6 m get a cost multiplier; fire trucks are blocked when `depth_cm >= 25`.

The `/ws` adapter stores its own hazard/closure context in sync with `app_state` and replans fire routes after closure changes.

### 9.4 Nearest station selection

`app/services/station_service.py`:

- Mapbox Search Box category API: `fire_station`, `hospital`, `police`.
- Search proximity is the destination.
- Results are sorted by straight-line distance, capped at 8 and at 30 km.
- For `nearest_station` routing, up to 6 stations are actually routed; the best duration/distance wins.
- If Mapbox returns nothing, demo `fire_post` / `medical_post` nodes are used. If routing still fails, the API returns `STATION_ROUTE_NOT_FOUND`.

### 9.5 Legacy demo-grid specifics

`app/routing/algorithms.py`:

| Profile | Min width | Stairs allowed | Speed |
|---|---|---|---|
| `fire_truck` | 3.5 m | No | 8.0 m/s if width ≥ 6 m, else 4.2 |
| `medical` | 1.2 m | No | 5.5 m/s if width ≥ 2.4 m, else 1.5 |
| `evacuation` | 0.9 m | Yes | 0.8 m/s on stairs, else 1.3 |

Costs are time-based with hazard/flood multipliers; closures remove edges. This path is kept for compatibility and is not the production navigation path.

---

## 10. Real sensors — complete onboarding

### 10.1 What works and what does not

| Question | Answer |
|---|---|
| Can a real sensor POST a reading? | **Yes** — `POST /api/v1/readings` |
| Is the reading stored? | **Yes** — `readings` row |
| Is risk computed? | **Yes**, if it can resolve a building or flood node |
| Is an incident created? | **Yes**, only at high/critical risk |
| Can the device get a response? | **Yes** — HTTP 201 JSON with `risk` and `incident_id` |
| Does the dashboard card update? | **No** — `/ws` alerts/telemetry are still simulator-generated |
| Can a backend consumer see it live? | **Yes** — `/ws/live` emits `reading.updated`, `risk.updated`, `incident.*` |
| Is there a sensor registration API? | **No** — register with SQL (below) |
| Is there MQTT? | **No** — HTTP only |
| Is there auth? | **No** — protect the network/proxy |

### 10.2 Step 1 — make the backend reachable

The sensor must reach the machine running FastAPI.

1. Start Uvicorn with `--host 0.0.0.0`.
2. Find the LAN IP: `ipconfig` → IPv4 address, e.g. `192.168.1.20`.
3. Allow inbound TCP 8000 in Windows Firewall (private network only).
4. Test from another device: `http://192.168.1.20:8000/health`.

For production, put Nginx/Caddy in front for TLS and authentication. Do not expose port 8000 directly.

### 10.3 Step 2 — register the sensor row

There is no `POST /sensors` endpoint. Register hardware in the `sensors` table. The insert **must** include:

- `id` (no DB default) — use `gen_random_uuid()`.
- `created_at` (no DB default) — use `now()`.
- `pos` and `geom` — `pos` is `[lng, lat]`; geometry is `POINT(lng lat)` SRID 4326.

If `gen_random_uuid()` is unavailable:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

#### Fire / smoke-temperature sensor attached to a building

```sql
INSERT INTO sensors (
    id, code, label, kind, building_id, node_code,
    status, source, pos, attributes, created_at, geom
)
SELECT
    gen_random_uuid(),
    'FIELD-B052-F1',
    'B-052 kitchen smoke + temperature',
    'smoke_temp',
    b.id,
    NULL,
    'active',
    'field',
    jsonb_build_array((b.center->>0)::float, (b.center->>1)::float),
    '{"vendor":"esp32","fw":"1.0","mount":"kitchen"}'::jsonb,
    now(),
    ST_SetSRID(
        ST_MakePoint((b.center->>0)::float, (b.center->>1)::float),
        4326
    )
FROM buildings b
WHERE b.code = 'B-052';
```

#### Structural sensor attached to a building

```sql
INSERT INTO sensors (
    id, code, label, kind, building_id, node_code,
    status, source, pos, attributes, created_at, geom
)
SELECT
    gen_random_uuid(),
    'FIELD-B052-S1',
    'B-052 tilt + crack',
    'structure',
    b.id,
    NULL,
    'active',
    'field',
    jsonb_build_array((b.center->>0)::float, (b.center->>1)::float),
    '{"vendor":"acme","fw":"2.1","mount":"north wall"}'::jsonb,
    now(),
    ST_SetSRID(
        ST_MakePoint((b.center->>0)::float, (b.center->>1)::float),
        4326
    )
FROM buildings b
WHERE b.code = 'B-052';
```

#### Flood / rain-level sensor attached to a lane node

```sql
INSERT INTO sensors (
    id, code, label, kind, building_id, node_code,
    status, source, pos, attributes, created_at, geom
)
SELECT
    gen_random_uuid(),
    'FIELD-I-WL1',
    'Junction I water level',
    'rain_level',
    NULL,
    n.code,
    'active',
    'field',
    n.pos,
    '{"vendor":"acme","fw":"1.4","flood_factor":1.0}'::jsonb,
    now(),
    ST_SetSRID(
        ST_MakePoint((n.pos->>0)::float, (n.pos->>1)::float),
        4326
    )
FROM lane_nodes n
WHERE n.code = 'I';
```

You can also supply explicit coordinates:

```sql
ST_SetSRID(ST_MakePoint(74.85879, 32.72747), 4326)  -- lng first, lat second
```

Common registration mistakes:

| Mistake | Result |
|---|---|
| Omitting `id` or `created_at` | NOT NULL violation |
| `ST_MakePoint(lat, lng)` | Wrong location |
| `pos` as `[lat, lng]` | Wrong map position and wrong risk target distance |
| Reusing an existing `code` | Unique violation |
| `kind` typo | Sensor never selected for that hazard |
| Setting `building_id` on a rain sensor | Risk target becomes the building instead of the node |

### 10.4 Step 3 — verify registration

```powershell
# All sensors
curl.exe http://localhost:8000/api/v1/sensors

# Filter by UUID (not code)
curl.exe "http://localhost:8000/api/v1/sensors?building_id=PUT-BUILDING-UUID-HERE"

# Find the new sensor's UUID
curl.exe http://localhost:8000/api/v1/sensors | Select-String FIELD-B052-F1
```

SQL check:

```sql
SELECT s.code, s.kind, s.source, s.status,
       b.code AS building, s.node_code,
       s.pos
FROM sensors s
LEFT JOIN buildings b ON b.id = s.building_id
WHERE s.code LIKE 'FIELD-%'
ORDER BY s.created_at DESC;
```

> Set `source = 'field'` for hardware. The ingestion endpoint does not check it, but it keeps inventory honest.

### 10.5 Step 4 — map hardware values to risk-engine keys

`values` must be a non-empty object of numbers. The risk engine reads specific keys; unknown keys are stored but ignored.

| Hazard | Sensor kind | Required value keys | Units | Notes |
|---|---|---|---|---|
| `fire` | `smoke_temp` | `smoke_level` and/or `smoke_ppm`, `temperature_c` | index 0–100, ppm, °C | If `smoke_level` is 0 and `smoke_ppm` > 0, ppm/10 is used |
| `flood` | `rain_level` | `water_level_cm`, `rain_mmh` | cm, mm/h | |
| `structural` | `structure` | `tilt_deg`, `crack_mm` | degrees, mm | Optional extras: `vib_rms`, `deviation_mm` |

Missing keys default to zero (temperature defaults to 31.5 °C). That can silently produce a deceptively low score, so always send every key for the hazard.

Do **not** use the dashboard telemetry names (`temp_c`, `level_cm`) in REST payloads. They will be stored but ignored by the rules.

### 10.6 Step 5 — POST the reading

Headers:

```http
Content-Type: application/json
```

Base body:

```json
{
  "sensor_id": "FIELD-B052-F1",
  "building_id": "B-052",
  "hazard": "fire",
  "values": {
    "smoke_level": 88,
    "temperature_c": 95,
    "smoke_ppm": 880
  },
  "observed_at": "2026-11-18T10:15:00+05:30",
  "source": "field",
  "simulation": false
}
```

`source` and `simulation` are separate fields. Set both (`"field"`, `false`).

> The examples below use `Invoke-RestMethod` because Windows PowerShell 5.1 can strip the quotes from nested JSON passed to `curl.exe -d`. Pipe the result to `ConvertTo-Json -Depth 10` if you want to see the raw response body.

#### Fire — normal reading

```powershell
$body = @{
    sensor_id = "JM-052"
    building_id = "B-052"
    hazard = "fire"
    values = @{ smoke_level = 4; temperature_c = 30; smoke_ppm = 40 }
    source = "field"
    simulation = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/readings" `
  -ContentType "application/json" `
  -Body $body
```

Example response:

```json
{
  "id": "f2c1...",
  "accepted": true,
  "risk": {
    "entity_type": "building",
    "entity_id": "5ef3...",
    "entity_code": "B-052",
    "building_id": "5ef3...",
    "building_code": "B-052",
    "hazard": "fire",
    "score": 2,
    "category": "normal",
    "reasons": [
      { "rule": "FIRE-R0", "text": "Below demo action thresholds" }
    ],
    "assessed_at": "2026-11-18T10:15:00+00:00",
    "rule_version": "demo-v1",
    "simulation": true,
    "simulation_id": null
  },
  "incident_id": null,
  "incident_created": false
}
```

`risk.simulation` is hardcoded `true` in the response builder. The stored `readings.simulation` is `false`.

#### Fire — critical reading (creates an incident)

```powershell
$body = @{
    sensor_id = "JM-052"
    building_id = "B-052"
    hazard = "fire"
    values = @{ smoke_level = 88; temperature_c = 95; smoke_ppm = 880 }
    source = "field"
    simulation = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/readings" `
  -ContentType "application/json" `
  -Body $body
```

On a clean seed, expected: `score = 90`, `category = "critical"`, `incident_created = true`, `incident_id` non-null. The incident code will be `AL-FIRE-B-052` (or `-2`, `-3` if a prior closed incident used that code and no active one exists). If an open/acknowledged fire incident already exists for B-052, the response returns that `incident_id` with `incident_created: false`.

#### Flood — node-target reading

```powershell
$body = @{
    sensor_id = "JM-R01"
    hazard = "flood"
    values = @{ water_level_cm = 45; rain_mmh = 40 }
    source = "field"
    simulation = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/readings" `
  -ContentType "application/json" `
  -Body $body
```

On a clean seed, expected: `risk.entity_type = "node"`, `risk.entity_code = "I"`, `score = 70`, `category = "high"`, incident `AL-FLOOD-I` created. If an open/acknowledged flood incident already exists at node I, the same id is returned with `incident_created: false`. Do **not** send a `building_id` unless the sensor is genuinely building-mounted.

#### Structural — high/critical reading

```powershell
$body = @{
    sensor_id = "JM-S52"
    building_id = "B-052"
    hazard = "structural"
    values = @{ tilt_deg = 1.0; crack_mm = 1.2 }
    source = "field"
    simulation = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/readings" `
  -ContentType "application/json" `
  -Body $body
```

On a clean seed, expected: `score = 89`, `category = "critical"`, incident `AL-STR-B-052` created. If an open/acknowledged structural incident already exists for B-052, the same id is returned with `incident_created: false`.

### 10.7 Response semantics

| Field | Meaning |
|---|---|
| `id` | UUID of the stored reading |
| `accepted` | `true` after a successful insert |
| `risk` | Risk object, or `null` if no target/score |
| `risk.category` | `normal`, `low`, `warning`, `high`, `critical` |
| `incident_id` | UUID of the active incident, or `null` |
| `incident_created` | `true` only when this request opened a new incident |

Incident creation happens at `high` **or** `critical` (score ≥ 65). A `warning` reading (40–64) never opens one. Repeated high readings return the existing incident with `incident_created: false`; a severity increase appends a `severity_escalated` event and emits `incident.updated`.

### 10.8 Step 6 — verify persistence

```powershell
curl.exe "http://localhost:8000/api/v1/readings?building_id=B-052&limit=10"
curl.exe "http://localhost:8000/api/v1/risks?entity_type=building"
curl.exe "http://localhost:8000/api/v1/incidents?hazard=fire"
```

SQL:

```sql
SELECT r.observed_at, r.hazard, r.values, r.source, r.simulation,
       s.code AS sensor, b.code AS building
FROM readings r
LEFT JOIN sensors s ON s.id = r.sensor_id
LEFT JOIN buildings b ON b.id = r.building_id
ORDER BY r.received_at DESC
LIMIT 10;

SELECT code, hazard, severity, status, opened_at
FROM incidents
ORDER BY opened_at DESC
LIMIT 10;
```

### 10.9 Device-side loop (Python)

This is a complete HTTP reporter with retries, UTC timestamps, and response checking. It uses only the standard library.

```python
"""JURAS field sensor reporter.

Environment:
    JURAS_API   e.g. http://192.168.1.20:8000
    JURAS_SENSOR   e.g. FIELD-B052-F1
    JURAS_BUILDING e.g. B-052
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = os.getenv("JURAS_API", "http://127.0.0.1:8000").rstrip("/")
SENSOR = os.getenv("JURAS_SENSOR", "FIELD-B052-F1")
BUILDING = os.getenv("JURAS_BUILDING", "B-052")
ENDPOINT = f"{API}/api/v1/readings"


def read_hardware() -> dict:
    """Replace this with real sensor reads."""
    return {
        "smoke_level": round(random.uniform(0, 100), 1),
        "temperature_c": round(random.uniform(28, 45), 1),
        "smoke_ppm": round(random.uniform(20, 500)),
    }


def post_reading(values: dict) -> dict:
    payload = {
        "sensor_id": SENSOR,
        "building_id": BUILDING,
        "hazard": "fire",
        "values": values,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": "field",
        "simulation": False,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    backoff = 1
    while True:
        try:
            result = post_reading(read_hardware())
            risk = result.get("risk") or {}
            print(
                "stored", result["id"],
                "score", risk.get("score"),
                "category", risk.get("category"),
                "incident", result.get("incident_id"),
            )
            backoff = 1
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            print("HTTP", exc.code, detail)
            backoff = min(backoff * 2, 60)
        except Exception as exc:
            print("network error:", exc)
            backoff = min(backoff * 2, 60)
        time.sleep(backoff if backoff > 1 else 30)


if __name__ == "__main__":
    main()
```

For a flood sensor, change the payload to omit `building_id` and use:

```python
{
    "sensor_id": "FIELD-I-WL1",
    "hazard": "flood",
    "values": {"water_level_cm": 18.5, "rain_mmh": 22.0},
    "source": "field",
    "simulation": False,
}
```

### 10.10 Microcontroller / ESP32 notes

- Use `Content-Type: application/json`; many minimal HTTP clients omit it and Pydantic returns 422.
- Use NTP to set UTC; otherwise omit `observed_at` and let the server stamp receipt time.
- Keep payloads small. A single JSON object is enough; do not batch multiple readings in one request (the API has no batch endpoint).
- Send at a sane cadence (15–60 s). The backend has no rate limiting.
- Retry on network errors and 5xx with exponential backoff. Do not retry 4xx except 429 (which is not currently emitted).
- Use HTTP only inside a trusted LAN. For anything else, terminate TLS at a reverse proxy.
- There is no idempotency key: a retry after a lost response inserts a second reading. That is acceptable for telemetry but should be considered in the dedupe/incident logic (which already prevents duplicate open incidents).
- The response body is small; parse `risk.category` to decide whether the device should raise a local alarm.

### 10.11 Reading a live response from another service

If you want a non-dashboard service to react to field readings, connect to `/ws/live`:

```python
import asyncio
import json

import websockets


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8000/ws/live") as ws:
        async for raw in ws:
            event = json.loads(raw)
            if event.get("event") in ("reading.updated", "risk.updated", "incident.created"):
                print(event["event"], event["data"])


asyncio.run(main())
```

### 10.12 Security and data-quality checklist

Before connecting hardware:

- [ ] Put the API behind a VPN or reverse proxy with TLS.
- [ ] Restrict inbound 8000 to the sensor VLAN.
- [ ] Register each device with a unique `code`.
- [ ] Set `sensors.source = 'field'`.
- [ ] Send `"source": "field"` and `"simulation": false` on every reading.
- [ ] Validate values on the device; do not send strings or `null`.
- [ ] Prefer sending both `sensor_id` and `building_id` for building-mounted sensors. `sensor_id` alone inherits the sensor's building, but the explicit pair is easier to audit. The backend does not verify that the sensor belongs to that building.
- [ ] Do not send `building_id` for lane-mounted flood sensors.
- [ ] Monitor `GET /health` and the `incidents` table.
- [ ] Back up the database; there is no retention policy yet.

---

## 11. Risk engine and incident lifecycle

### 11.1 Score bands

| Score | Category | Incident? |
|---|---|---|
| 0–19 | `normal` | No |
| 20–39 | `low` | No |
| 40–64 | `warning` | No |
| 65–84 | `high` | **Yes** |
| 85–100 | `critical` | **Yes** |

Code: `app/risk/rules.py:CATEGORY_BANDS` and `app/core/constants.py`.

### 11.2 Fire formula

Inputs: `smoke_level` (0–100), `temperature_c`, optional `smoke_ppm`.

```text
if smoke_level == 0 and smoke_ppm > 0:
    smoke_level = min(100, smoke_ppm / 10)

smoke_norm = clamp(smoke_level / 100, 0, 1)
temp_norm  = clamp((temperature_c - 35) / (100 - 35), 0, 1)
score      = round(100 * (0.60 * smoke_norm + 0.40 * temp_norm))
```

Reason codes:

| Rule | Trigger |
|---|---|
| `FIRE-R2` | smoke ≥ 80 (critical band) |
| `FIRE-R1` | smoke ≥ 60 (high band) |
| `FIRE-R4` | temperature ≥ 85 °C (critical) |
| `FIRE-R3` | temperature ≥ 70 °C (high) |
| `FIRE-R0` | below all thresholds |

### 11.3 Flood formula

Inputs: `water_level_cm`, `rain_mmh`.

```text
level_norm = clamp(water_level_cm / 60, 0, 1)
rain_norm  = clamp(rain_mmh / 75, 0, 1)
score      = round(100 * (0.75 * level_norm + 0.25 * rain_norm))
```

Reason codes:

| Rule | Trigger |
|---|---|
| `FLOOD-R2` | water level ≥ 40 cm (critical) |
| `FLOOD-R1` | water level ≥ 25 cm (high) |
| `FLOOD-R3` | rainfall ≥ 30 mm/h |
| `FLOOD-R0` | below thresholds |

### 11.4 Structural formula

Inputs: `tilt_deg`, `crack_mm`.

```text
tilt_norm  = clamp(tilt_deg / 1.1, 0, 1)
crack_norm = clamp(crack_mm / 1.4, 0, 1)
score      = round(100 * (0.55 * tilt_norm + 0.45 * crack_norm))
```

Reason codes:

| Rule | Trigger |
|---|---|
| `STRUCT-R2` | tilt ≥ 1.1° (critical) |
| `STRUCT-R1` | tilt ≥ 0.8° (high) |
| `STRUCT-R4` | crack ≥ 1.4 mm (critical) |
| `STRUCT-R3` | crack ≥ 1.0 mm (high) |
| `STRUCT-R0` | below thresholds |

### 11.5 Risk target selection

Inside `reading_service.ingest()`:

1. If a building was resolved → `entity_type=building`, `entity_id=building.id`, `entity_code=building.code`, position = `building.center`.
2. Else if the sensor has `node_code` and `hazard == "flood"` → look up the lane node, use `entity_type=node`, `entity_code=node.code`, position = `sensor.pos`.
3. Else → no risk assessment (`risk: null`).

### 11.6 Incident creation and dedupe

`upsert_for_risk()`:

- Ignores anything below `high`.
- Finds an existing incident with the same hazard and target and status `open` or `acknowledged`.
- If found:
  - Escalates severity if the new severity is higher.
  - Adds a `severity_escalated` event.
  - Emits `incident.updated` with `escalated: true`.
  - Returns `incident_created = false`.
- If not found:
  - Generates a code: `AL-FIRE-<building>`, `AL-FLOOD-<node>`, `AL-STR-<building>`.
  - Adds `-2`, `-3`, … if that code exists.
  - Creates an `open` incident with severity mapped from category (`high` → `high`, `critical` → `critical`).
  - Adds an `opened` event.
  - Emits `incident.created`.

Incident title patterns:

| Hazard | Title |
|---|---|
| Fire | `Fire risk, B-052` |
| Flood | `Waterlogging risk, I` |
| Structural | `Structural deviation, B-052` |

Severity mapping: `normal/low → low`, `warning → medium`, `high → high`, `critical → critical`.

### 11.7 Incident status lifecycle

```text
open ──► acknowledged ──► resolved
  │            │
  ├────────────┴──────► false_alarm
  └───────────────────► resolved
```

- `resolved` and `false_alarm` are terminal.
- PATCH writes an audit event with actor and note.
- `/ws` alert resolution also clears the related fire hazard/route and sets the building back to `ok`.

---

## 12. Simulation system

### 12.1 Scenarios

`app/simulation/models.py`, with severity rate multiplier `normal 0.55`, `warning 1.0`, `critical 1.6`.

| Scenario | Target | Generated values |
|---|---|---|
| `fire` | Building with `smoke_temp` | `temperature_c`, `smoke_ppm`, `smoke_level` |
| `flood` | Lane node with `rain_level` | `rain_mmh`, `water_level_cm` |
| `structural` | Building with `structure` | `tilt_deg`, `crack_mm`, `vib_rms`, `deviation_mm` |

Fire model (elapsed `age`):

```text
smoke_ppm   = clamp(35 + age * 14, 30, 900)
temperature = 31.5 + min(110, age * 1.1)
smoke_level = smoke_ppm / 10
```

Flood model:

```text
rain = min(75, age * 2)
if rain > 18: level_cm += (rain - 18) * 0.012 * flood_factor * 2
else: level_cm = max(0, level_cm - 0.25)
```

Structural model:

```text
tilt_deg = base_tilt + min(1.1, age * 0.012)
crack_mm = base_crack + min(1.2, age * 0.02)
vib_rms  = 0.02 + min(0.05, age * 0.0004)
```

### 12.2 Lifecycle

1. `POST /simulations` validates and inserts a `queued` row.
2. Manager sets `running`, records `started_at`, emits `simulation.started`.
3. A task ticks every `interval_ms`, calling the same `ingest()` used by real sensors.
4. At `duration_sec`, sets `completed` and emits `simulation.completed`.
5. `stop` cancels the task, sets `stopped`, emits `simulation.completed` with status `stopped`.
6. Exceptions set `failed` + `error_code = SCENARIO_ERROR` and emit `simulation.failed`.

The `/ws` adapter reacts to `simulation.started` by seeding its in-memory fire/crack/flood animation state, and to `incident.*` by linking alert ids. It does **not** react to `risk.updated`.

### 12.3 Simulation concurrency

- Max 3 running simulations.
- One active simulation per building+scenario.
- Fire/structural need a building sensor; flood needs a node sensor.
- A database restart does not resume in-flight simulations; rows remain `running` unless stopped.

---

## 13. Known gaps and roadmap

These are current, verified limitations — not documentation errors.

| # | Gap | Impact | Suggested fix |
|---|---|---|---|
| 1 | No sensor registration API | Hardware onboarding needs SQL | `POST /api/v1/sensors` + validation |
| 2 | No MQTT subscriber | MQTT devices cannot publish directly | Bridge MQTT → `reading_service.ingest` |
| 3 | `/ws` telemetry is simulator-only | Real readings do not move dashboard gauges | Build telemetry from latest DB readings for field sensors |
| 4 | `/ws` alerts are fusion-only | A REST-created incident does not automatically become a dashboard alert | Map `risk.updated`/`incident.created` to alert objects |
| 5 | `GET /sensors?building_id=` requires UUID | Code filter silently returns `[]` | Accept codes like other endpoints |
| 6 | `bbox` ignored for lanes and risks | Clients may expect spatial filtering | Wire `ST_Intersects` |
| 7 | `simulation: true` hardcoded in several responses | Field data looks simulated | Use the row flag |
| 8 | `/ws/live` envelope `simulation` defaults true | Consumers may misclassify events | Derive from `data.simulation` |
| 9 | Closures are in-memory | Lost on restart; not shared across workers | Persist `closures` table |
| 10 | No idempotency key on readings | Retries duplicate rows | Add `device_reading_id` unique key |
| 11 | No auth/rate limiting/TLS in app | Anyone on the network can write | Reverse proxy + API keys/HMAC |
| 12 | Single-process state | Multiple workers diverge | Redis pub/sub + shared state |
| 13 | No retention/partitioning | Readings grow unbounded | Time partitions + retention job |
| 14 | No value range validation | Out-of-range/sensor-fault values can score incorrectly | Pydantic bounds + quality flags |
| 15 | No live traffic in routing | ETAs are class-speed estimates | Traffic provider integration |
| 16 | Integration tests need local `juras_test` | CI cannot run them against Supabase env | Provision test DB in CI |

Recommended next implementation order:

1. `POST /api/v1/sensors` with device token.
2. Field-reading → `/ws` alert/telemetry bridge.
3. MQTT bridge.
4. Persist closures and add auth.

---

## 14. Operations, tests, and troubleshooting

### 14.1 Database reset

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
.\.venv\Scripts\python.exe scripts\import_osm_geojson.py
```

The first command wipes everything; the second restores OSM buildings/lanes. Closures and active simulations are in memory and are also lost on backend restart.

### 14.2 Unit tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

### 14.3 Integration tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

They expect PostgreSQL at `postgresql+asyncpg://postgres:juras123@localhost:5432/juras_test` (`tests/conftest.py`). The current development `.env` points at Supabase, so these tests fail unless a local `juras_test` database exists.

### 14.4 Smoke test

With the backend running:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

It checks health, 90 buildings, source filters, sensors, ingestion, incident creation, and the `/ws` snapshot/telemetry/alerts.

### 14.5 Frontend checks

```powershell
cd frontend
npm run typecheck
```

### 14.6 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `500` on `/api/v1/buildings` | DB unreachable or migrations missing | Check `/health`, run `alembic upgrade head` |
| `422 VALIDATION_ERROR` on readings | Missing `values`, wrong enum, or string values | Send numbers and valid hazard/source |
| Reading stored but `risk: null` | Sensor has neither a `building_id` nor a usable `node_code` | Register the sensor against a building or lane node |
| `404 SENSOR_NOT_FOUND` | Code typo, sensor not registered, or building has no sensor of the hazard kind | `GET /sensors`, re-run insert, or send an existing `sensor_id` |
| Incident not created | Score < 65 | Check the formula inputs |
| Dashboard still shows old routes after closure | WS not connected or no active fire alert | Closures only replan existing fire routes |
| `/ws` shows no real sensor data | Expected gap | Use `/ws/live`; `/ws` telemetry is simulated |
| Navigation error `OSM_GRAPH_EMPTY` | OSM import not run | `python scripts/import_osm_geojson.py` |
| Nearest-station routing fails | No Mapbox token and no demo fallback for police | Set `MAPBOX_ACCESS_TOKEN` or pass an origin |
| Device cannot reach API | Uvicorn bound to 127.0.0.1 or firewall | `--host 0.0.0.0`, allow port 8000 |

### 14.7 Useful SQL

```sql
-- Sensor inventory
SELECT code, kind, source, status, node_code,
       building_id IS NOT NULL AS building_mounted
FROM sensors ORDER BY kind, code;

-- Latest readings
SELECT r.received_at, r.hazard, r.source, r.simulation,
       s.code AS sensor, b.code AS building, r.values
FROM readings r
LEFT JOIN sensors s ON s.id = r.sensor_id
LEFT JOIN buildings b ON b.id = r.building_id
ORDER BY r.received_at DESC
LIMIT 20;

-- Latest risk per entity+hazard
SELECT DISTINCT ON (entity_type, entity_id, hazard)
       entity_type, entity_code, hazard, score, category, assessed_at
FROM risk_assessments
ORDER BY entity_type, entity_id, hazard, assessed_at DESC;

-- Open incidents
SELECT code, hazard, severity, status, opened_at
FROM incidents
WHERE status IN ('open', 'acknowledged')
ORDER BY opened_at DESC;
```

---

## 15. File map

| Path | Responsibility |
|---|---|
| `backend/app/main.py` | FastAPI app, lifespan, middleware, exception handlers, root routes, WS mounting |
| `backend/app/api/v1/router.py` | Includes all `/api/v1` endpoint routers |
| `backend/app/api/v1/endpoints/` | HTTP handlers: health, buildings, lanes, sensors, readings, simulations, risks, incidents, routes |
| `backend/app/api/deps.py` | Runtime registry for manager/world |
| `backend/app/schemas/` | Pydantic request/response models |
| `backend/app/services/reading_service.py` | Ingestion → reading → risk → incident pipeline |
| `backend/app/services/incident_service.py` | Incident dedupe, severity escalation, transitions |
| `backend/app/services/navigation_service.py` | OSM navigate endpoint + frontage trim |
| `backend/app/services/simulation_navigation_service.py` | `/ws` fire/medical/evacuation route payloads |
| `backend/app/services/gis_service.py` | GeoJSON assemblies |
| `backend/app/services/station_service.py` | Mapbox Search Box + demo fallback |
| `backend/app/services/osm_import_service.py` | GeoJSON → PostGIS import |
| `backend/app/repositories/` | SQLAlchemy queries and output shaping |
| `backend/app/models/` | ORM tables |
| `backend/app/risk/rules.py` | Fire/flood/structural scoring |
| `backend/app/risk/thresholds.py` | Numeric thresholds |
| `backend/app/routing/osm_graph.py` | OSM graph build, profiles, A*, snapping |
| `backend/app/routing/building_access.py` | Frontage trimming |
| `backend/app/routing/graph.py` | Legacy graph primitives |
| `backend/app/routing/algorithms.py` | Legacy Dijkstra/cost functions |
| `backend/app/ws/ws_routes.py` | `/ws` and `/ws/live` socket handlers |
| `backend/app/ws/frontend_adapter.py` | Dashboard snapshot, telemetry, fusion, alerts, routes, commands |
| `backend/app/realtime/bus.py` | In-process pub/sub + adapter dispatch |
| `backend/app/realtime/events.py` | Event envelope factory |
| `backend/app/simulation/` | Scenario models and manager |
| `backend/app/state.py` | In-memory hazards, floods, closures |
| `backend/app/db/` | Engine, sessions, metadata |
| `backend/alembic/versions/0001_initial.py` | Authoritative PostGIS DDL |
| `backend/scripts/seed_demo_data.py` | Destructive demo seed |
| `backend/scripts/import_osm_geojson.py` | Idempotent OSM import |
| `backend/scripts/smoke_test.py` | End-to-end HTTP/WS smoke test |
| `backend/tests/` | Unit + integration tests |
| `frontend/src/types.ts` | Dashboard WS message contract |

---

### Final note

For real hardware, the reliable recipe is:

1. Register one sensor row in SQL with `kind`, `building_id`/`node_code`, `pos`, and `geom`.
2. POST every reading to `/api/v1/readings` with `source: "field"`, `simulation: false`, and the risk-engine keys.
3. For building sensors, send `sensor_id` and (recommended) `building_id`; the backend inherits the building from the sensor when the id is omitted.
4. Read `risk.category` and `incident_id` from the HTTP response; listen to `/ws/live` if you need a push stream.
5. Treat `/ws` as the demo dashboard feed until the field-to-dashboard bridge is implemented.
