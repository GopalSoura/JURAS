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
export type FeedStatus = 'connecting' | 'live' | 'sim' | 'offline';

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
}

export interface Telemetry {
  node_id: string;
  kind: SensorKind;
  ts: number;
  battery: number;
  values: Record<string, number>;
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
  pos: LonLat;
  confidence: number; // 0-1
  sources: Source[];
  created_at: number;
  updated_at: number;
  dispatched_at?: number;
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
      alerts: Alert[];
      routes: Record<string, Route[]>;
      hazards: Hazard[];
      flood_zones: FloodZone[];
      interventions: Intervention[];
    }
  | { t: 'telemetry'; items: Telemetry[] }
  | { t: 'building'; id: string; patch: Partial<Building> }
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
