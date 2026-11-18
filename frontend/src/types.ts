// Shared data contract. The same JSON shapes are produced by the built-in simulator
// and expected from the real backend (FastAPI WebSocket). See README.

export type LonLat = [number, number];

export type ModuleId = 'overview' | 'fire' | 'structure' | 'flood' | 'routing' | 'sensors';
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type AlertStatus = 'new' | 'ack' | 'dispatched' | 'resolved';
export type AlertModule = 'fire' | 'structure' | 'flood' | 'map';
export type BuildingStatus = 'ok' | 'watch' | 'inspect' | 'fire';
export type SensorKind = 'smoke_temp' | 'structure' | 'rain_level';
export type Profile = 'fire_truck' | 'medical' | 'evacuation';
export type FeedStatus = 'connecting' | 'live' | 'sim' | 'reconnecting' | 'offline';
export type ViewMode = 'simulation' | 'realtime';

/* ---------- real OSM navigation (backend /api/v1/routes/navigate) ---------- */
export type NavProfile = 'fire_truck' | 'responder_bike' | 'walking';
export type NavDepartment = 'fire' | 'medical' | 'police';
export type NavOriginMode = 'coordinates' | 'nearest_station';

export interface NavOrigin {
  id: string;
  label: string;
  pos: LonLat;
}

export interface NavStation {
  id: string;
  department: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  distance_m: number;
  source: string;
  category?: string;
}

export interface NavClosure {
  id: string;
  lat: number;
  lng: number;
  pos: LonLat;
  radius_m: number;
  reason: string;
  source: 'manual' | 'simulated';
  active: boolean;
}

export interface NavSnap {
  lat: number;
  lng: number;
  snapped: { lat: number; lng: number };
  snap_distance_m: number;
  edge_id: string;
  way_id: string;
  road_name: string;
  highway: string;
  oneway: 'both' | 'forward' | 'backward';
}

export interface NavRouteProperties {
  distance_m: number;
  duration_s: number | null;
  profile: NavProfile;
  weighting: string;
  algorithm: string;
  duration_basis?: string | null;
  geometry_source: string;
  edge_count: number;
  edge_ids: string[];
  warnings: string[];
  origin_snap_distance_m: number;
  destination_snap_distance_m: number;
  closures_considered?: number;
}

export interface NavRouteFeature {
  type: 'Feature';
  geometry: { type: 'LineString'; coordinates: LonLat[] };
  properties: NavRouteProperties;
}

export interface NavResponse {
  route: NavRouteFeature;
  origin: NavSnap;
  destination: NavSnap;
  warnings: string[];
  origin_station?: NavStation | null;
  stations_considered?: number;
}

export interface Building {
  id: string;
  name: string;
  center: LonLat;
  footprint: LonLat[];
  floors: number;
  height_m: number;
  year_built: number;
  use: string;
  construction: string;
  occupancy: number;
  priority: number; // 0-100 inspection priority
  status: BuildingStatus;
  tilt_deg: number;
  crack_mm: number;
  last_inspection: string;
  access_node: string;
}

export interface LaneNode {
  id: string;
  pos: LonLat;
  label: string;
  kind: 'junction' | 'fire_post' | 'medical_post' | 'assembly';
}

export interface LaneEdge {
  id: string;
  a: string;
  b: string;
  width_m: number;
  stairs: boolean;
}

export interface SensorMeta {
  node_id: string;
  kind: SensorKind;
  pos: LonLat;
  label: string;
  building_id?: string;
  node_code?: string | null;
  device_id?: string | null;
  source?: string;
  simulation?: boolean;
}

export interface RiskState {
  sensor_code?: string;
  device_id?: string | null;
  hazard: 'fire' | 'flood' | 'structural';
  entity_type: 'building' | 'node';
  entity_code: string;
  building_code?: string | null;
  node_code?: string | null;
  score: number;
  category: 'normal' | 'low' | 'warning' | 'high' | 'critical';
  reasons?: { rule: string; text: string }[];
  assessed_at: string;
  simulation?: boolean;
  realtime?: boolean;
}

export interface Telemetry {
  node_id: string;
  kind: SensorKind;
  ts: number;
  battery: number;
  values: Record<string, number>;
  sim_values?: Record<string, number>;
  live_values?: Record<string, number>;
  device_id?: string | null;
  source?: string;
  simulation?: boolean;
  realtime?: boolean;
  live?: boolean;
  stale?: boolean;
  observed_at?: string | null;
  risk?: Pick<RiskState, 'score' | 'category' | 'hazard' | 'assessed_at'>;
  live_risk?: Pick<RiskState, 'score' | 'category' | 'hazard' | 'assessed_at'>;
}

export interface Source {
  kind: 'sensor' | 'citizen' | 'camera' | 'cv' | 'field';
  label: string;
  ts: number;
}

export interface Alert {
  id: string;
  module: AlertModule;
  severity: Severity;
  status: AlertStatus;
  title: string;
  detail: string;
  building_id?: string;
  node_code?: string | null;
  target?: string;
  pos: LonLat;
  confidence: number; // 0-1
  sources: Source[];
  created_at: number;
  updated_at: number;
  last_update?: string | null;
  dispatched_at?: number;
  simulation?: boolean;
  realtime?: boolean;
  recommendation?: string;
}

export interface Route {
  profile: Profile;
  path: LonLat[];
  foot_path?: LonLat[]; // final stretch the vehicle cannot enter
  length_m: number;
  travel_s: number; // time to reach end of `path`
  eta_s: number; // including last stretch on foot
  feasible: boolean;
  last_mile_m: number;
  note: string;
  from: string;
  to: string;
}

export interface Hazard {
  id: string;
  kind: 'fire';
  pos: LonLat;
  radius_m: number;
  active: boolean;
}

export interface FloodZone {
  id: string;
  node_id: string;
  polygon: LonLat[];
  center: LonLat;
  radius_m: number;
  depth_cm: number;
  label: string;
}

export interface Intervention {
  id: string;
  name: string;
  where: string;
  pos: LonLat;
  reduces_pct: number;
  cost_lakh: number;
  rank: number;
}

// ---------- server -> client ----------
export type ServerMsg =
  | {
      t: 'snapshot';
      buildings: Building[];
      lane_nodes: LaneNode[];
      lane_edges: LaneEdge[];
      sensors: SensorMeta[];
      telemetry?: Telemetry[];
      risks?: RiskState[];
      live_risks?: RiskState[];
      live_building_patches?: Record<string, Partial<Building>>;
      alerts: Alert[];
      routes: Record<string, Route[]>;
      hazards: Hazard[];
      flood_zones: FloodZone[];
      interventions: Intervention[];
    }
  | { t: 'telemetry'; items: Telemetry[] }
  | { t: 'live'; items: Telemetry[] }
  | { t: 'risk'; risk: RiskState }
  | { t: 'building'; id: string; patch: Partial<Building>; realtime?: boolean }
  | { t: 'alert'; alert: Alert }
  | { t: 'routes'; alert_id: string; routes: Route[] }
  | { t: 'hazard'; hazard: Hazard }
  | { t: 'flood'; zones: FloodZone[]; interventions: Intervention[] };

// ---------- client -> server ----------
export type ClientCmd =
  | { cmd: 'scenario'; name: 'fire' | 'crack' | 'flood' | 'reset' }
  | { cmd: 'alert_action'; id: string; action: 'ack' | 'dispatch' | 'resolve' };

export interface Feed {
  label: string;
  start(onMsg: (m: ServerMsg) => void, onStatus: (s: FeedStatus) => void): void;
  stop(): void;
  send(cmd: ClientCmd): void;
}
