import { create } from 'zustand';
import type {
  Alert, Building, FeedStatus, FloodZone, Hazard, Intervention, LaneEdge, LaneNode, ModuleId, Route, SensorKind, SensorMeta, ServerMsg, Telemetry,
} from './types';
import { safetyScore } from './lib/metrics';

export interface LogLine { ts: number; text: string; hot: boolean; kind: SensorKind }
export interface Layers { osm: boolean; lanes: boolean; sensors: boolean; flood: boolean }

export interface StoreState {
  ready: boolean;
  buildings: Record<string, Building>;
  laneNodes: LaneNode[];
  laneEdges: LaneEdge[];
  sensors: SensorMeta[];
  nodeState: Record<string, Telemetry>;
  alerts: Record<string, Alert>;
  routes: Record<string, Route[]>;
  hazards: Record<string, Hazard>;
  floodZones: FloodZone[];
  interventions: Intervention[];
  log: LogLine[];
  riskHistory: { ts: number; score: number }[];
  rainHistory: { ts: number; rain: number; level: number }[];

  selectedAlert: string | null;
  selectedBuilding: string | null;
  module: ModuleId;
  layers: Layers;
  feedStatus: FeedStatus;
  feedLabel: string;

  apply: (m: ServerMsg) => void;
  selectAlert: (id: string | null) => void;
  selectBuilding: (id: string | null) => void;
  setModule: (m: ModuleId) => void;
  toggleLayer: (k: keyof Layers) => void;
  setFeed: (status: FeedStatus, label: string) => void;
  sample: () => void;
}

const fmt = (t: Telemetry): LogLine => {
  const v = t.values;
  if (t.kind === 'smoke_temp') return { ts: t.ts, kind: t.kind, hot: v.smoke_ppm > 120 || v.temp_c > 45, text: `${t.node_id}  smoke ${v.smoke_ppm} ppm  ${v.temp_c.toFixed(1)} °C` };
  if (t.kind === 'structure') return { ts: t.ts, kind: t.kind, hot: v.tilt_deg >= 0.45 || v.crack_mm >= 0.55, text: `${t.node_id}  tilt ${v.tilt_deg.toFixed(2)}°  crack ${v.crack_mm.toFixed(2)} mm` };
  return { ts: t.ts, kind: t.kind, hot: v.level_cm >= 3, text: `${t.node_id}  rain ${v.rain_mmh.toFixed(0)} mm/h  level ${v.level_cm.toFixed(0)} cm` };
};

let batch = 0;

export const useStore = create<StoreState>()((set, get) => ({
  ready: false,
  buildings: {},
  laneNodes: [],
  laneEdges: [],
  sensors: [],
  nodeState: {},
  alerts: {},
  routes: {},
  hazards: {},
  floodZones: [],
  interventions: [],
  log: [],
  riskHistory: [],
  rainHistory: [],
  selectedAlert: null,
  selectedBuilding: null,
  module: 'overview',
  layers: { osm: true, lanes: true, sensors: true, flood: true },
  feedStatus: 'connecting',
  feedLabel: '',

  apply: (m) => {
    switch (m.t) {
      case 'snapshot':
        set({
          ready: true,
          buildings: Object.fromEntries(m.buildings.map((b) => [b.id, b])),
          laneNodes: m.lane_nodes,
          laneEdges: m.lane_edges,
          sensors: m.sensors,
          alerts: Object.fromEntries(m.alerts.map((a) => [a.id, a])),
          routes: m.routes,
          hazards: Object.fromEntries(m.hazards.map((h) => [h.id, h])),
          floodZones: m.flood_zones,
          interventions: m.interventions,
          nodeState: {},
          selectedAlert: null,
          selectedBuilding: null,
        });
        break;
      case 'telemetry': {
        const nodeState = { ...get().nodeState };
        for (const i of m.items) nodeState[i.node_id] = i;
        const lines = m.items.map(fmt);
        const hot = lines.filter((l) => l.hot);
        const calm = lines.filter((l) => !l.hot);
        batch++;
        const pick = [...hot.slice(0, 4), calm[batch % Math.max(1, calm.length)]].filter(Boolean);
        const log = [...pick.reverse(), ...get().log].slice(0, 40);
        const rainNodes = m.items.filter((i) => i.kind === 'rain_level');
        let rainHistory = get().rainHistory;
        if (rainNodes.length) {
          const rain = Math.max(...rainNodes.map((i) => i.values.rain_mmh));
          const level = Math.max(...rainNodes.map((i) => i.values.level_cm));
          rainHistory = [...rainHistory, { ts: m.items[0].ts, rain, level }].slice(-90);
        }
        set({ nodeState, log, rainHistory });
        break;
      }
      case 'building': {
        const b = get().buildings[m.id];
        if (b) set({ buildings: { ...get().buildings, [m.id]: { ...b, ...m.patch } } });
        break;
      }
      case 'alert':
        set({ alerts: { ...get().alerts, [m.alert.id]: m.alert } });
        break;
      case 'routes': {
        const routes = { ...get().routes };
        if (m.routes.length) routes[m.alert_id] = m.routes;
        else delete routes[m.alert_id];
        set({ routes });
        break;
      }
      case 'hazard':
        set({ hazards: { ...get().hazards, [m.hazard.id]: m.hazard } });
        break;
      case 'flood':
        set({ floodZones: m.zones, interventions: m.interventions });
        break;
    }
  },

  selectAlert: (id) => {
    const a = id ? get().alerts[id] : undefined;
    set({ selectedAlert: id, selectedBuilding: a?.building_id ?? get().selectedBuilding });
  },
  selectBuilding: (id) => set({ selectedBuilding: id }),
  setModule: (module) => set({ module }),
  toggleLayer: (k) => set({ layers: { ...get().layers, [k]: !get().layers[k] } }),
  setFeed: (feedStatus, feedLabel) => set({ feedStatus, feedLabel }),
  sample: () => {
    const score = safetyScore(get().alerts);
    set({ riskHistory: [...get().riskHistory, { ts: Date.now(), score }].slice(-90) });
  },
}));
