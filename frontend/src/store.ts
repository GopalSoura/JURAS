import { create } from 'zustand';
import type {
  Alert, Building, FeedStatus, FloodZone, Hazard, Intervention, LaneEdge, LaneNode, ModuleId, NavClosure, NavDepartment, NavOrigin, NavOriginMode, NavProfile, NavResponse, NavStation, RiskState, Route, SensorKind, SensorMeta, ServerMsg, Telemetry, ViewMode,
} from './types';
import { safetyScore } from './lib/metrics';
import { mergeLiveTelemetry, mergeRisks, mergeTelemetry } from './lib/live';
import {
  clearClosures,
  createClosure,
  deleteClosure,
  fetchClosures,
  fetchNavigation,
  ApiError,
  type ClosureInput,
} from './lib/api';

export interface LogLine { ts: number; text: string; hot: boolean; kind: SensorKind }
export interface Layers { lanes: boolean; sensors: boolean; flood: boolean }
export type NavStatus = 'idle' | 'loading' | 'ready' | 'error';

let navAbort: AbortController | null = null;

function defaultNavOrigin(s: StoreState): NavOrigin | null {
  if (s.navOrigin) return s.navOrigin;
  const firePost = s.laneNodes.find((n) => n.kind === 'fire_post');
  if (firePost) return { id: `node:${firePost.id}`, label: `${firePost.label} (fire post)`, pos: firePost.pos };
  const post = s.laneNodes.find((n) => n.kind !== 'junction');
  if (post) return { id: `node:${post.id}`, label: `${post.label} (staging point)`, pos: post.pos };
  return null;
}

export interface StoreState {
  ready: boolean;
  mode: ViewMode;
  buildings: Record<string, Building>;
  laneNodes: LaneNode[];
  laneEdges: LaneEdge[];
  sensors: SensorMeta[];
  nodeState: Record<string, Telemetry>;
  liveState: Record<string, Telemetry>;
  risks: Record<string, RiskState>;
  liveRisks: Record<string, RiskState>;
  alerts: Record<string, Alert>;
  simAlerts: Record<string, Alert>;
  liveAlerts: Record<string, Alert>;
  simBuildings: Record<string, Building>;
  liveBuildings: Record<string, Building>;
  routes: Record<string, Route[]>;
  hazards: Record<string, Hazard>;
  floodZones: FloodZone[];
  interventions: Intervention[];
  log: LogLine[];
  simLog: LogLine[];
  liveLog: LogLine[];
  riskHistory: { ts: number; score: number }[];
  simRiskHistory: { ts: number; score: number }[];
  liveRiskHistory: { ts: number; score: number }[];
  rainHistory: { ts: number; rain: number; level: number }[];

  selectedAlert: string | null;
  selectedBuilding: string | null;
  module: ModuleId;
  layers: Layers;
  feedStatus: FeedStatus;
  feedLabel: string;

  navRoute: NavResponse | null;
  navStatus: NavStatus;
  navError: string | null;
  navErrorCode: string | null;
  navProfile: NavProfile;
  navOrigin: NavOrigin | null;
  navDepartment: NavDepartment;
  navOriginMode: NavOriginMode;
  navStation: NavStation | null;
  navTargetId: string | null;
  navClosures: NavClosure[];
  navClosureMode: boolean;
  navClosureError: string | null;
  navClosureBusy: boolean;

  apply: (m: ServerMsg) => void;
  selectAlert: (id: string | null) => void;
  selectBuilding: (id: string | null) => void;
  setModule: (m: ModuleId) => void;
  setMode: (m: ViewMode) => void;
  toggleLayer: (k: keyof Layers) => void;
  setFeed: (status: FeedStatus, label: string) => void;
  sample: () => void;
  setNavOrigin: (o: NavOrigin | null) => void;
  setNavProfile: (p: NavProfile) => void;
  setNavDepartment: (d: NavDepartment) => void;
  setNavOriginMode: (m: NavOriginMode) => void;
  navigateToAlert: (id: string) => Promise<void>;
  refreshNavigation: () => Promise<void>;
  clearNavigation: () => void;
  loadNavClosures: () => Promise<void>;
  setNavClosureMode: (on: boolean) => void;
  addNavClosure: (input: ClosureInput) => Promise<boolean>;
  removeNavClosure: (id: string) => Promise<void>;
  clearNavClosures: () => Promise<void>;
}

const fmt = (t: Telemetry): LogLine => {
  const v = t.values;
  const num = (x: number | undefined): number | undefined =>
    typeof x === 'number' && Number.isFinite(x) ? x : undefined;
  const fixed = (x: number | undefined, d: number): string =>
    x === undefined ? 'N/A' : x.toFixed(d);
  if (t.kind === 'smoke_temp') {
    const ppm = num(v.smoke_ppm);
    const temp = num(v.temp_c ?? v.temperature_c);
    return {
      ts: t.ts,
      kind: t.kind,
      hot: (ppm ?? 0) > 120 || (temp ?? 0) > 45,
      text: `${t.node_id}  smoke ${ppm === undefined ? 'N/A' : ppm} ppm  ${fixed(temp, 1)} °C`,
    };
  }
  if (t.kind === 'structure') {
    const tilt = num(v.tilt_deg);
    const crack = num(v.crack_mm);
    return {
      ts: t.ts,
      kind: t.kind,
      hot: (tilt ?? 0) >= 0.45 || (crack ?? 0) >= 0.55,
      text: `${t.node_id}  tilt ${fixed(tilt, 2)}°  crack ${fixed(crack, 2)} mm`,
    };
  }
  const level = num(v.level_cm ?? v.water_level_cm);
  const rain = num(v.rain_mmh);
  return {
    ts: t.ts,
    kind: t.kind,
    hot: (level ?? 0) >= 3,
    text: `${t.node_id}  rain ${fixed(rain, 0)} mm/h  level ${fixed(level, 0)} cm`,
  };
};

let batch = 0;

export const useStore = create<StoreState>()((set, get) => ({
  ready: false,
  mode: 'simulation',
  buildings: {},
  simBuildings: {},
  liveBuildings: {},
  laneNodes: [],
  laneEdges: [],
  sensors: [],
  nodeState: {},
  liveState: {},
  risks: {},
  liveRisks: {},
  alerts: {},
  simAlerts: {},
  liveAlerts: {},
  routes: {},
  hazards: {},
  floodZones: [],
  interventions: [],
  log: [],
  simLog: [],
  liveLog: [],
  riskHistory: [],
  simRiskHistory: [],
  liveRiskHistory: [],
  rainHistory: [],
  selectedAlert: null,
  selectedBuilding: null,
  module: 'overview',
  layers: { lanes: true, sensors: true, flood: true },
  feedStatus: 'connecting',
  feedLabel: '',
  navRoute: null,
  navStatus: 'idle',
  navError: null,
  navErrorCode: null,
  navProfile: 'fire_truck',
  navOrigin: null,
  navDepartment: 'fire',
  navOriginMode: 'nearest_station',
  navStation: null,
  navTargetId: null,
  navClosures: [],
  navClosureMode: false,
  navClosureError: null,
  navClosureBusy: false,

  apply: (m) => {
    switch (m.t) {
      case 'snapshot': {
        const simBuildings = Object.fromEntries(m.buildings.map((b) => [b.id, b]));
        const liveBuildings = { ...simBuildings };
        for (const [id, patch] of Object.entries(m.live_building_patches ?? {})) {
          const b = liveBuildings[id];
          if (b) liveBuildings[id] = { ...b, ...patch };
        }
        const simAlerts: Record<string, Alert> = {};
        const liveAlerts: Record<string, Alert> = {};
        for (const a of m.alerts) (a.realtime ? liveAlerts : simAlerts)[a.id] = a;
        const mode = get().mode;
        set({
          ready: true,
          simBuildings,
          liveBuildings,
          buildings: mode === 'realtime' ? liveBuildings : simBuildings,
          laneNodes: m.lane_nodes,
          laneEdges: m.lane_edges,
          sensors: m.sensors,
          simAlerts,
          liveAlerts,
          alerts: mode === 'realtime' ? liveAlerts : simAlerts,
          routes: m.routes,
          hazards: Object.fromEntries(m.hazards.map((h) => [h.id, h])),
          floodZones: m.flood_zones,
          interventions: m.interventions,
          nodeState: mergeTelemetry({}, m.telemetry ?? []),
          liveState: mergeLiveTelemetry({}, m.telemetry ?? []),
          risks: mergeRisks({}, m.risks ?? []),
          liveRisks: mergeRisks({}, m.live_risks ?? []),
          selectedAlert: null,
          selectedBuilding: null,
        });
        break;
      }
      case 'live': {
        const liveLog = [...m.items.map(fmt).reverse(), ...get().liveLog].slice(0, 40);
        set({
          liveState: mergeLiveTelemetry(get().liveState, m.items),
          liveLog,
          ...(get().mode === 'realtime' ? { log: liveLog } : {}),
        });
        break;
      }
      case 'telemetry': {
        const nodeState = mergeTelemetry(get().nodeState, m.items);
        const lines = m.items.map(fmt);
        const hot = lines.filter((l) => l.hot);
        const calm = lines.filter((l) => !l.hot);
        batch++;
        const pick = [...hot.slice(0, 4), calm[batch % Math.max(1, calm.length)]].filter(Boolean);
        const simLog = [...pick.reverse(), ...get().simLog].slice(0, 40);
        const rainNodes = m.items.filter((i) => i.kind === 'rain_level');
        let rainHistory = get().rainHistory;
        if (rainNodes.length) {
          const rain = Math.max(...rainNodes.map((i) => i.values.rain_mmh));
          const level = Math.max(...rainNodes.map((i) => i.values.level_cm));
          rainHistory = [...rainHistory, { ts: m.items[0].ts, rain, level }].slice(-90);
        }
        set({
          nodeState,
          simLog,
          rainHistory,
          ...(get().mode === 'simulation' ? { log: simLog } : {}),
        });
        break;
      }
      case 'risk':
        if (m.risk.realtime) set({ liveRisks: mergeRisks(get().liveRisks, m.risk) });
        else set({ risks: mergeRisks(get().risks, m.risk) });
        break;
      case 'building': {
        const realtime = Boolean(m.realtime);
        const simBuildings = get().simBuildings;
        const liveBuildings = get().liveBuildings;
        const source = realtime ? liveBuildings : simBuildings;
        const b = source[m.id];
        if (!b) break;
        const updated = { ...b, ...m.patch };
        const nextSim = realtime ? simBuildings : { ...simBuildings, [m.id]: updated };
        const nextLive = realtime ? { ...liveBuildings, [m.id]: updated } : liveBuildings;
        set({
          simBuildings: nextSim,
          liveBuildings: nextLive,
          buildings: get().mode === 'realtime' ? nextLive : nextSim,
        });
        break;
      }
      case 'alert': {
        const realtime = Boolean(m.alert.realtime);
        const simAlerts = get().simAlerts;
        const liveAlerts = get().liveAlerts;
        const nextSim = realtime ? simAlerts : { ...simAlerts, [m.alert.id]: m.alert };
        const nextLive = realtime ? { ...liveAlerts, [m.alert.id]: m.alert } : liveAlerts;
        set({
          simAlerts: nextSim,
          liveAlerts: nextLive,
          alerts: get().mode === 'realtime' ? nextLive : nextSim,
        });
        break;
      }
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
    if (get().navTargetId && id !== null && id !== get().navTargetId) get().clearNavigation();
    const a = id ? get().alerts[id] : undefined;
    set({ selectedAlert: id, selectedBuilding: a?.building_id ?? get().selectedBuilding });
  },
  selectBuilding: (id) => set({ selectedBuilding: id }),
  setModule: (module) => set({ module }),
  setMode: (mode) => {
    const s = get();
    if (mode === s.mode) return;
    // Swap only the mode-specific views. Nav state, map instance, origin,
    // destination, zoom and centre are deliberately left untouched.
    const alerts = mode === 'realtime' ? s.liveAlerts : s.simAlerts;
    const buildings = mode === 'realtime' ? s.liveBuildings : s.simBuildings;
    set({
      mode,
      alerts,
      buildings,
      log: mode === 'realtime' ? s.liveLog : s.simLog,
      riskHistory: mode === 'realtime' ? s.liveRiskHistory : s.simRiskHistory,
      selectedAlert: s.selectedAlert && alerts[s.selectedAlert] ? s.selectedAlert : null,
      selectedBuilding: s.selectedBuilding && buildings[s.selectedBuilding] ? s.selectedBuilding : null,
    });
  },
  toggleLayer: (k) => set({ layers: { ...get().layers, [k]: !get().layers[k] } }),
  setFeed: (feedStatus, feedLabel) => set({ feedStatus, feedLabel }),
  sample: () => {
    const s = get();
    const score = safetyScore(s.alerts);
    const point = { ts: Date.now(), score };
    if (s.mode === 'realtime') {
      const liveRiskHistory = [...s.liveRiskHistory, point].slice(-90);
      set({ liveRiskHistory, riskHistory: liveRiskHistory });
    } else {
      const simRiskHistory = [...s.simRiskHistory, point].slice(-90);
      set({ simRiskHistory, riskHistory: simRiskHistory });
    }
  },

  setNavOrigin: (navOrigin) => {
    set({ navOrigin, navOriginMode: 'coordinates' });
    const target = get().navTargetId;
    if (target) void get().navigateToAlert(target);
  },
  setNavProfile: (navProfile) => {
    set({ navProfile });
    const target = get().navTargetId;
    if (target) void get().navigateToAlert(target);
  },
  setNavDepartment: (navDepartment) => {
    set({ navDepartment, navOriginMode: 'nearest_station' });
    const target = get().navTargetId;
    if (target) void get().navigateToAlert(target);
  },
  setNavOriginMode: (navOriginMode) => {
    set({ navOriginMode });
    const target = get().navTargetId;
    if (target) void get().navigateToAlert(target);
  },
  navigateToAlert: async (id) => {
    const alert = get().alerts[id];
    if (!alert) {
      set({ navStatus: 'error', navError: 'Incident is no longer available', navErrorCode: 'ALERT_NOT_FOUND' });
      return;
    }
    const { navOriginMode, navDepartment } = get();
    const origin = navOriginMode === 'nearest_station' ? null : defaultNavOrigin(get());
    if (navOriginMode === 'coordinates' && !origin) {
      set({
        navTargetId: id,
        navStatus: 'error',
        navError: 'No responder origin available. Pick a fire post, use your live location, or enter coordinates.',
        navErrorCode: 'NO_ORIGIN',
      });
      return;
    }
    navAbort?.abort();
    const controller = new AbortController();
    navAbort = controller;
    set({
      navTargetId: id,
      navOrigin: origin,
      navStation: null,
      navStatus: 'loading',
      navError: null,
      navErrorCode: null,
    });
    try {
      const navRoute = await fetchNavigation(
        {
          ...(origin ? { origin: origin.pos } : {}),
          destination: alert.pos,
          ...(alert.building_id ? { buildingId: alert.building_id } : {}),
          profile: get().navProfile,
          originMode: navOriginMode,
          ...(navOriginMode === 'nearest_station' ? { department: navDepartment } : {}),
        },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      set({ navRoute, navStation: navRoute.origin_station ?? null, navStatus: 'ready', navError: null, navErrorCode: null });
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof DOMException && error.name === 'AbortError') return;
      const apiError = error instanceof ApiError ? error : null;
      set({
        navRoute: null,
        navStatus: 'error',
        navError:
          apiError?.message ??
          (error instanceof TypeError
            ? 'Cannot reach the navigation API. Check the backend and VITE_API_URL.'
            : 'Navigation request failed'),
        navErrorCode: apiError?.code ?? 'NAVIGATION_UNAVAILABLE',
      });
    } finally {
      if (navAbort === controller) navAbort = null;
    }
  },
  refreshNavigation: async () => {
    const target = get().navTargetId;
    if (target) await get().navigateToAlert(target);
  },
  clearNavigation: () => {
    navAbort?.abort();
    navAbort = null;
    set({
      navRoute: null,
      navStation: null,
      navStatus: 'idle',
      navError: null,
      navErrorCode: null,
      navTargetId: null,
      navClosureMode: false,
    });
  },
  loadNavClosures: async () => {
    try {
      const navClosures = await fetchClosures();
      set({ navClosures, navClosureError: null });
    } catch {
      set({ navClosureError: 'Cannot load road closures from the backend.' });
    }
  },
  setNavClosureMode: (navClosureMode) => set({ navClosureMode, navClosureError: null }),
  addNavClosure: async (input) => {
    set({ navClosureBusy: true, navClosureError: null });
    try {
      const closure = await createClosure(input);
      set({
        navClosures: [...get().navClosures, closure],
        navClosureMode: false,
        navClosureBusy: false,
      });
      const target = get().navTargetId;
      if (target) await get().navigateToAlert(target);
      return true;
    } catch {
      set({
        navClosureBusy: false,
        navClosureError: 'Could not add the road closure. Check the backend connection.',
      });
      return false;
    }
  },
  removeNavClosure: async (id) => {
    set({ navClosureBusy: true, navClosureError: null });
    try {
      await deleteClosure(id);
      set({
        navClosures: get().navClosures.filter((closure) => closure.id !== id),
        navClosureBusy: false,
      });
      const target = get().navTargetId;
      if (target) await get().navigateToAlert(target);
    } catch {
      set({ navClosureBusy: false, navClosureError: 'Could not remove the road closure.' });
    }
  },
  clearNavClosures: async () => {
    set({ navClosureBusy: true, navClosureError: null });
    try {
      await clearClosures();
      set({ navClosures: [], navClosureBusy: false });
      const target = get().navTargetId;
      if (target) await get().navigateToAlert(target);
    } catch {
      set({ navClosureBusy: false, navClosureError: 'Could not clear road closures.' });
    }
  },
}));
