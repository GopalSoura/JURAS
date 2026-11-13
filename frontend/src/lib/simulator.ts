import type {
  Alert, Building, ClientCmd, Feed, FeedStatus, FloodZone, Hazard, Intervention, Route, SensorMeta, ServerMsg, Source, Telemetry,
} from '../types';
import { distM, ellipse } from './geo';
import { buildGraph, planRoutes, type Ctx } from './routing';
import { FLOOD_FACTOR, LANE_EDGES, LANE_NODES, makeBuildings, makeSensors, POSTS, rankInterventions, seedAlerts } from './seed';

// Browser-side stand-in for the whole backend: hardware nodes + MQTT + sensor fusion + routing.
// It emits exactly the ServerMsg shapes the real FastAPI WebSocket should emit.

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const noise = (s: number) => (Math.random() - 0.5) * 2 * s;
const r1 = (v: number) => Math.round(v * 10) / 10;
const r2 = (v: number) => Math.round(v * 100) / 100;

interface FireScn { t0: number; auto: boolean; step: number }

export class SimFeed implements Feed {
  label = 'Simulated hardware feed';
  private onMsg: (m: ServerMsg) => void = () => {};
  private timer: ReturnType<typeof setInterval> | undefined;
  private fakeNow: number | undefined;

  private base: Building[] = [];
  private buildings = new Map<string, Building>();
  private sensors: SensorMeta[] = [];
  private graph = buildGraph(LANE_NODES, LANE_EDGES);

  private alerts = new Map<string, Alert>();
  private routes = new Map<string, Route[]>();
  private hazards = new Map<string, Hazard>();
  private zones: FloodZone[] = [];
  private interventions: Intervention[] = [];
  private lastKey = new Map<string, string>();

  private fires = new Map<string, FireScn>();
  private cracks = new Map<string, { t0: number }>();
  private flood: { t0: number } | null = null;
  private rain = 0;
  private level = new Map<string, number>();
  private battery = new Map<string, number>();
  private zoneKey = '';

  private clock = () => this.fakeNow ?? Date.now();

  start(onMsg: (m: ServerMsg) => void, onStatus: (s: FeedStatus) => void): void {
    this.onMsg = onMsg;
    onStatus('sim');
    this.reset();
    this.startFire('B-021', 24, true); // open on an incident already in progress
    this.step();
    this.timer = setInterval(() => this.step(), 1000);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
  }

  send(cmd: ClientCmd): void {
    if (cmd.cmd === 'scenario') {
      if (cmd.name === 'reset') this.reset();
      else if (cmd.name === 'fire') this.startFire(this.pickFire(), 0, false);
      else if (cmd.name === 'crack') this.startCrack(this.pickCrack());
      else if (cmd.name === 'flood') this.flood = { t0: this.clock() };
      return;
    }
    const a = this.alerts.get(cmd.id);
    if (!a) return;
    const now = this.clock();
    if (cmd.action === 'ack' && a.status === 'new') this.put({ ...a, status: 'ack', updated_at: now });
    if (cmd.action === 'dispatch') this.put({ ...a, status: 'dispatched', dispatched_at: now, updated_at: now });
    if (cmd.action === 'resolve') this.resolve(a);
  }

  // ---------------- state ----------------
  private reset(): void {
    const now = this.clock();
    this.base = makeBuildings();
    this.buildings = new Map(this.base.map((b) => [b.id, { ...b }]));
    this.sensors = makeSensors(this.base);
    this.alerts = new Map(seedAlerts(now, this.base).map((a) => [a.id, a]));
    this.routes.clear();
    this.hazards.clear();
    this.fires.clear();
    this.cracks.clear();
    this.flood = null;
    this.rain = 0;
    this.zones = [];
    this.zoneKey = '';
    this.interventions = [];
    this.lastKey.clear();
    this.level = new Map(this.sensors.filter((s) => s.kind === 'rain_level').map((s) => [s.node_id, 0]));
    this.battery = new Map(this.sensors.map((s) => [s.node_id, 72 + Math.random() * 24]));
    this.onMsg({
      t: 'snapshot',
      buildings: [...this.buildings.values()],
      lane_nodes: LANE_NODES,
      lane_edges: LANE_EDGES,
      sensors: this.sensors,
      alerts: [...this.alerts.values()],
      routes: {},
      hazards: [],
      flood_zones: [],
      interventions: [],
    });
  }

  private pickFire(): string {
    const ids = ['B-014', 'B-052', 'B-066', 'B-073', 'B-095', 'B-021'];
    return ids.find((id) => !this.fires.has(id)) ?? ids[Math.floor(Math.random() * ids.length)];
  }
  private pickCrack(): string {
    const ids = ['B-007', 'B-073', 'B-052'];
    return ids.find((id) => !this.cracks.has(id)) ?? ids[0];
  }

  private startFire(id: string, ageS: number, auto: boolean): void {
    this.alerts.delete(`AL-FIRE-${id}`);
    this.lastKey.delete(`AL-FIRE-${id}`);
    this.fires.set(id, { t0: this.clock() - ageS * 1000, auto, step: -1 });
  }
  private startCrack(id: string): void {
    this.alerts.delete(`AL-STR-${id}`);
    this.lastKey.delete(`AL-STR-${id}`);
    this.cracks.set(id, { t0: this.clock() });
  }

  private put(a: Alert): void {
    this.alerts.set(a.id, a);
    this.onMsg({ t: 'alert', alert: a });
  }

  private resolve(a: Alert): void {
    const now = this.clock();
    this.put({ ...a, status: 'resolved', updated_at: now });
    if (a.module === 'fire' && a.building_id) {
      this.fires.delete(a.building_id);
      const hz = this.hazards.get(`HZ-${a.building_id}`);
      if (hz) {
        const off = { ...hz, active: false };
        this.hazards.set(off.id, off);
        this.onMsg({ t: 'hazard', hazard: off });
      }
      this.routes.delete(a.id);
      this.onMsg({ t: 'routes', alert_id: a.id, routes: [] });
      this.patchBuilding(a.building_id, { status: 'ok' });
    }
    if (a.module === 'structure' && a.building_id) {
      this.cracks.delete(a.building_id);
      this.patchBuilding(a.building_id, { status: 'watch' });
    }
    if (a.module === 'flood') this.flood = null;
  }

  private patchBuilding(id: string, patch: Partial<Building>): void {
    const b = this.buildings.get(id);
    if (!b) return;
    Object.assign(b, patch);
    this.onMsg({ t: 'building', id, patch });
  }

  // ---------------- one second of the world ----------------
  step(now?: number): void {
    if (now !== undefined) this.fakeNow = now;
    const t = this.clock();
    this.stepWeather(t);
    const items = this.sensors.map((s) => this.read(s, t));
    this.onMsg({ t: 'telemetry', items });
    const by = new Map(items.map((i) => [i.node_id, i]));
    this.detectFire(t, by);
    this.detectStructure(t, by);
    this.detectFlood(t, by);
  }

  private stepWeather(t: number): void {
    if (this.flood) this.rain = Math.min(75, ((t - this.flood.t0) / 1000) * 2);
    else this.rain = Math.max(0, this.rain - 3);
    for (const [id, lvl] of this.level) {
      const f = FLOOD_FACTOR[id] ?? 0.5;
      const next = this.rain > 18 ? lvl + (this.rain - 18) * 0.012 * f : Math.max(0, lvl - 0.25);
      this.level.set(id, next);
    }
  }

  private read(s: SensorMeta, t: number): Telemetry {
    const bat = clamp((this.battery.get(s.node_id) ?? 80) - Math.random() * 0.002, 5, 100);
    this.battery.set(s.node_id, bat);
    const base = { node_id: s.node_id, kind: s.kind, ts: t, battery: r1(bat) };

    if (s.kind === 'smoke_temp') {
      let smoke = 35 + noise(5);
      let temp = 31.5 + noise(0.4);
      for (const [bid, f] of this.fires) {
        const age = (t - f.t0) / 1000 - (s.node_id.endsWith('b') ? 5 : 0);
        if (age <= 0) continue;
        const fb = this.buildings.get(bid)!;
        let inf = 0;
        if (s.building_id === bid) inf = 1;
        else {
          const d = distM(s.pos, fb.center);
          if (d < 130) inf = 0.06 * (1 - d / 130);
        }
        smoke += Math.min(900, age * 14) * inf;
        temp += Math.min(110, age * 1.1) * inf;
      }
      return { ...base, values: { smoke_ppm: Math.round(smoke), temp_c: r1(temp) } };
    }

    if (s.kind === 'structure') {
      const b0 = this.base.find((b) => b.id === s.building_id)!;
      let tilt = b0.tilt_deg + noise(0.01);
      let crack = b0.crack_mm + noise(0.01);
      let vib = 0.02 + noise(0.004);
      const c = this.cracks.get(s.building_id!);
      if (c) {
        const age = (t - c.t0) / 1000;
        tilt += Math.min(1.1, age * 0.012);
        crack += Math.min(1.2, age * 0.02);
        vib += age * 0.0004;
      }
      return { ...base, values: { tilt_deg: r2(tilt), crack_mm: r2(crack), vib_rms: r2(vib * 10) / 10 } };
    }

    return {
      ...base,
      values: { rain_mmh: r1(Math.max(0, this.rain + (this.rain > 0 ? noise(1.5) : 0))), level_cm: r1(this.level.get(s.node_id) ?? 0) },
    };
  }

  // ---------------- fusion + decisions ----------------
  private detectFire(t: number, by: Map<string, Telemetry>): void {
    for (const b of this.buildings.values()) {
      const nodes = this.sensors.filter((s) => s.kind === 'smoke_temp' && s.building_id === b.id);
      if (!nodes.length) continue;
      const id = `AL-FIRE-${b.id}`;
      const prev = this.alerts.get(id);
      if (prev?.status === 'resolved') continue;

      const ps: { p: number; src: Source }[] = [];
      for (const n of nodes) {
        const v = by.get(n.node_id)!.values;
        const score = clamp(v.smoke_ppm / 400, 0, 1) * 0.6 + clamp((v.temp_c - 45) / 40, 0, 1) * 0.4;
        if (score >= 0.12) {
          ps.push({ p: Math.min(0.9, score), src: { kind: 'sensor', label: `${n.node_id}: smoke ${v.smoke_ppm} ppm, ${v.temp_c.toFixed(0)} °C`, ts: t } });
        }
      }
      const scn = this.fires.get(b.id);
      const age = scn ? (t - scn.t0) / 1000 : 0;
      if (scn && age >= 14) ps.push({ p: 0.55, src: { kind: 'citizen', label: 'Citizen report: smoke from upper floor', ts: scn.t0 + 14000 } });
      if (scn && age >= 22) ps.push({ p: 0.6, src: { kind: 'camera', label: 'CAM-03: smoke plume detected', ts: scn.t0 + 22000 } });
      const conf = 1 - ps.reduce((a, x) => a * (1 - x.p), 1);
      if (conf < 0.35 && !prev) continue;
      if (conf < 0.2) continue;

      const confirmed = conf >= 0.8;
      let status = prev?.status ?? 'new';
      let dispatched_at = prev?.dispatched_at;
      if (scn?.auto && confirmed && !dispatched_at) {
        status = 'dispatched';
        dispatched_at = t - 6000;
        scn.auto = false;
      }

      // hazard zone and routes
      let routes = this.routes.get(id);
      if (confirmed) {
        const radius = Math.min(42, 18 + age * 0.35);
        const hz: Hazard = { id: `HZ-${b.id}`, kind: 'fire', pos: b.center, radius_m: r1(radius), active: true };
        const step = Math.floor(radius / 1.5);
        if (!routes || (scn && step !== scn.step)) {
          if (scn) scn.step = step;
          this.hazards.set(hz.id, hz);
          this.onMsg({ t: 'hazard', hazard: hz });
          routes = planRoutes(this.graph, { building: b, posts: POSTS, ctx: this.ctx([hz]) });
          this.routes.set(id, routes);
          this.onMsg({ t: 'routes', alert_id: id, routes });
        }
        if (b.status !== 'fire') this.patchBuilding(b.id, { status: 'fire' });
      }

      const truck = routes?.find((r) => r.profile === 'fire_truck');
      const alert: Alert = {
        id, module: 'fire', severity: confirmed ? 'critical' : 'high', status, dispatched_at,
        title: confirmed ? `Fire confirmed, ${b.id}` : `Possible fire, ${b.id}`,
        detail: `${b.name}, ${b.floors} floors, about ${b.occupancy} occupants`,
        building_id: b.id, pos: b.center, confidence: Math.round(conf * 100) / 100,
        sources: ps.map((x) => x.src), created_at: prev?.created_at ?? scn?.t0 ?? t, updated_at: t,
        recommendation: confirmed && truck ? `${truck.note} Evacuate via the route shown.` : 'Waiting for a second independent signal before dispatch.',
      };
      const key = `${alert.severity}|${Math.round(conf * 50)}|${alert.sources.length}|${status}`;
      if (this.lastKey.get(id) !== key) {
        this.lastKey.set(id, key);
        this.put(alert);
      } else this.alerts.set(id, alert);
    }
  }

  private detectStructure(t: number, by: Map<string, Telemetry>): void {
    for (const s of this.sensors.filter((x) => x.kind === 'structure')) {
      const b = this.buildings.get(s.building_id!)!;
      const base = this.base.find((x) => x.id === b.id)!;
      const v = by.get(s.node_id)!.values;
      const id = `AL-STR-${b.id}`;
      const prev = this.alerts.get(id);
      if (prev?.status === 'resolved') continue;

      const high = v.tilt_deg >= 0.8 || v.crack_mm >= 1.0;
      const med = v.tilt_deg >= 0.45 || v.crack_mm >= 0.55;
      const scn = this.cracks.get(b.id);
      const age = scn ? (t - scn.t0) / 1000 : 0;
      const cv = scn && age >= 10;

      const priority = clamp(Math.round(base.priority + v.tilt_deg * 14 + v.crack_mm * 8), 0, 99);
      const status = high ? 'inspect' : med ? 'watch' : 'ok';
      if (b.status !== 'fire' && (Math.abs(priority - b.priority) >= 2 || status !== b.status)) {
        this.patchBuilding(b.id, { priority, status, tilt_deg: v.tilt_deg, crack_mm: v.crack_mm });
      }
      if (!high && !med) continue;

      const sources: Source[] = [{ kind: 'sensor', label: `${s.node_id}: tilt ${v.tilt_deg.toFixed(2)}°, crack ${v.crack_mm.toFixed(2)} mm`, ts: t }];
      if (cv) sources.push({ kind: 'cv', label: 'Photo analysis: 3 crack candidates, widest 1.4 mm', ts: scn!.t0 + 10000 });
      const conf = Math.min(0.96, 0.35 + v.tilt_deg * 0.35 + v.crack_mm * 0.2 + (cv ? 0.1 : 0));
      const severity = high ? 'high' : 'medium';
      const alert: Alert = {
        id, module: 'structure', severity,
        status: prev && prev.severity === severity ? prev.status : 'new',
        title: high ? `Tilt and crack growth, ${b.id}` : `Tilt watch, ${b.id}`,
        detail: `${b.name}, built ${b.year_built}, ${b.construction}`,
        building_id: b.id, pos: b.center, confidence: Math.round(conf * 100) / 100, sources,
        created_at: prev?.created_at ?? t, updated_at: t,
        recommendation: high
          ? 'Queue for engineer inspection within 24 h. Restrict upper-floor use until validated. AI only ranks priority.'
          : 'Keep on weekly review. Engineer to validate if tilt passes 0.8°.',
      };
      const key = `${severity}|${Math.round(conf * 40)}|${sources.length}|${alert.status}`;
      if (this.lastKey.get(id) !== key) {
        this.lastKey.set(id, key);
        this.put(alert);
      } else this.alerts.set(id, alert);
    }
  }

  private detectFlood(t: number, by: Map<string, Telemetry>): void {
    const zones: FloodZone[] = [];
    for (const s of this.sensors.filter((x) => x.kind === 'rain_level')) {
      const v = by.get(s.node_id)!.values;
      const lvl = v.level_cm;
      if (lvl >= 3) {
        const rx = 14 + lvl * 0.9;
        zones.push({
          id: `FZ-${s.node_id}`, node_id: s.node_id, center: s.pos, radius_m: rx,
          polygon: ellipse(s.pos, rx, 7 + lvl * 0.45, 20), depth_cm: r1(lvl), label: `${lvl.toFixed(0)} cm`,
        });
      }
      const id = `AL-FLOOD-${s.node_id}`;
      const prev = this.alerts.get(id);
      if (prev?.status === 'resolved' || lvl < 10) continue;
      const high = lvl >= 25;
      const conf = Math.min(0.95, 0.4 + lvl / 60 + v.rain_mmh / 200);
      const severity = high ? 'high' : 'medium';
      const alert: Alert = {
        id, module: 'flood', severity, status: prev && prev.severity === severity ? prev.status : 'new',
        title: `Waterlogging risk, ${s.label}`,
        detail: `Water level ${lvl.toFixed(0)} cm, rainfall ${v.rain_mmh.toFixed(0)} mm/h`,
        pos: s.pos, confidence: Math.round(conf * 100) / 100,
        sources: [{ kind: 'sensor', label: `${s.node_id}: level ${lvl.toFixed(0)} cm, rain ${v.rain_mmh.toFixed(0)} mm/h`, ts: t }],
        created_at: prev?.created_at ?? t, updated_at: t,
        recommendation: high
          ? 'Avoid this lane for tenders. Pre-position a pump and open the nearest drain gate.'
          : 'Watch level. Check the drain at the nearest junction.',
      };
      const key = `${severity}|${Math.round(lvl / 4)}|${alert.status}`;
      if (this.lastKey.get(id) !== key) {
        this.lastKey.set(id, key);
        this.put(alert);
      } else this.alerts.set(id, alert);
    }
    const zk = zones.map((z) => `${z.node_id}:${Math.round(z.depth_cm / 2)}`).join('|');
    if (zk !== this.zoneKey) {
      this.zoneKey = zk;
      this.zones = zones;
      this.interventions = zones.length ? rankInterventions() : [];
      this.onMsg({ t: 'flood', zones, interventions: this.interventions });
      // re-plan active fire routes around newly flooded lanes
      for (const [aid] of this.routes) {
        const a = this.alerts.get(aid);
        const b = a?.building_id ? this.buildings.get(a.building_id) : undefined;
        const hz = b ? this.hazards.get(`HZ-${b.id}`) : undefined;
        if (a && b && hz?.active) {
          const routes = planRoutes(this.graph, { building: b, posts: POSTS, ctx: this.ctx([hz]) });
          this.routes.set(aid, routes);
          this.onMsg({ t: 'routes', alert_id: aid, routes });
        }
      }
    }
  }

  private ctx(hazards: Hazard[]): Ctx {
    return {
      hazards: hazards.filter((h) => h.active).map((h) => ({ pos: h.pos, radius_m: h.radius_m })),
      floods: this.zones.map((z) => ({ pos: z.center, radius_m: z.radius_m, depth_cm: z.depth_cm })),
    };
  }
}
