import { PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import type { Layer, PickingInfo } from '@deck.gl/core';
import type { Building, FloodZone, Hazard, LaneEdge, LaneNode, LonLat, NavClosure, Route, SensorMeta } from '../types';
import type { StoreState } from '../store';
import { CONFIG } from '../config';
import { cumulative, distM, midpoint, pointAlong } from './geo';
import { focusAlert, isOpen } from './metrics';
import { NAV_PROFILE_META, PROFILE_META, type RGB } from './meta';
import { navRouteLine } from './navigation';

type RGBA = [number, number, number, number];
const rgba = (c: RGB, a: number): RGBA => [c[0], c[1], c[2], a];
const FONT = 'IBM Plex Mono, ui-monospace, monospace';

const tsCache = new WeakMap<Route, number[]>();
const timestamps = (r: Route) => {
  let t = tsCache.get(r);
  if (!t) {
    t = cumulative(r.path);
    tsCache.set(r, t);
  }
  return t;
};

interface Unit { pos: LonLat; route: Route; arrived: boolean }

function buildingColor(b: Building, s: StoreState, pulse: number): RGBA {
  if (b.status === 'fire') return [227, 93, 106, Math.round(165 + pulse * 30)];
  if (s.selectedBuilding === b.id) return [77, 159, 255, 235];
  if (s.module === 'structure') {
    const k = Math.min(1, Math.max(0, (b.priority - 30) / 60));
    return [Math.round(64 + 130 * k), Math.round(112 + 34 * (1 - k)), Math.round(150 - 70 * k), 215];
  }
  if (b.status === 'inspect') return [224, 122, 69, 220];
  if (b.status === 'watch') return [224, 166, 60, 200];
  return [58, 76, 110, 200];
}

function sensorColor(m: SensorMeta, s: StoreState): { c: RGBA; hot: boolean } {
  const realtime = s.mode === 'realtime';
  const risk = realtime ? s.liveRisks[m.node_id] : s.risks[m.node_id];
  if (risk?.category === 'critical') return { c: [227, 93, 106, 255], hot: true };
  if (risk?.category === 'high') return { c: [232, 145, 60, 255], hot: true };
  const v = realtime ? s.liveState[m.node_id]?.values : s.nodeState[m.node_id]?.values;
  if (v) {
    if (m.kind === 'smoke_temp' && (v.smoke_ppm > 120 || v.temp_c > 45)) return { c: [227, 93, 106, 255], hot: true };
    if (m.kind === 'structure' && (v.tilt_deg >= 0.45 || v.crack_mm >= 0.55)) return { c: [224, 122, 69, 255], hot: true };
    if (m.kind === 'rain_level' && v.level_cm >= 3) return { c: [77, 159, 255, 255], hot: true };
  }
  if (m.kind === 'smoke_temp') return { c: [205, 150, 120, 235], hot: false };
  if (m.kind === 'structure') return { c: [160, 145, 205, 235], hot: false };
  return { c: [95, 175, 230, 235], hot: false };
}

export function buildLayers(s: StoreState, t: number, now: number, zoom: number): Layer[] {
  const pulse = 0.5 + 0.5 * Math.sin(t / 520);
  const nodePos = new Map<string, LonLat>(s.laneNodes.map((n) => [n.id, n.pos]));
  const buildings = Object.values(s.buildings);
  const realtime = s.mode === 'realtime';
  const focus = focusAlert(s.alerts, s.routes, s.selectedAlert);
  const routes = focus ? s.routes[focus.id] ?? [] : [];
  const hazards = Object.values(s.hazards).filter((h) => h.active);
  const layers: Layer[] = [];

  // ---- lane network, coloured by what can use it ----
  if (s.layers.lanes) {
    const flooded = (e: LaneEdge) => {
      const a = nodePos.get(e.a);
      const b = nodePos.get(e.b);
      if (!a || !b || realtime) return false;
      const mid = midpoint(a, b);
      return s.floodZones.some((z) => distM(mid, z.center) <= z.radius_m + 6);
    };
    layers.push(
      new PathLayer<LaneEdge>({
        id: 'lanes',
        data: s.laneEdges,
        getPath: (e) => [nodePos.get(e.a) ?? [0, 0], nodePos.get(e.b) ?? [0, 0]],
        getColor: (e) => (flooded(e) ? [80, 150, 225, 200] : e.stairs ? [224, 166, 60, 150] : e.width_m >= 3.5 ? [90, 165, 235, 95] : [100, 120, 165, 85]),
        getWidth: (e) => Math.max(1.1, e.width_m * 0.4),
        widthUnits: 'meters',
        widthMinPixels: 1,
        capRounded: true,
        jointRounded: true,
        updateTriggers: { getColor: [s.floodZones] },
      }),
    );
  }

  // ---- flood zones (simulation hazards only; Realtime Mode is sensor-driven) ----
  if (!realtime && s.layers.flood && s.floodZones.length) {
    layers.push(
      new PolygonLayer<FloodZone>({
        id: 'flood',
        data: s.floodZones,
        getPolygon: (z) => z.polygon,
        getFillColor: [70, 140, 230, 78],
        getLineColor: [130, 190, 240, 170],
        lineWidthMinPixels: 1.5,
        stroked: true,
        filled: true,
      }),
      new TextLayer<FloodZone>({
        id: 'flood-labels',
        data: s.floodZones,
        getPosition: (z) => [...z.center, 2],
        getText: (z) => z.label,
        getSize: 11,
        getColor: [190, 220, 245, 235],
        fontFamily: FONT,
        background: true,
        getBackgroundColor: [8, 12, 20, 225],
        backgroundPadding: [4, 2],
      }),
    );
  }

  // ---- fire hazard zone (simulation only) ----
  if (!realtime && hazards.length) {
    layers.push(
      new ScatterplotLayer<Hazard>({
        id: 'hazard-fill',
        data: hazards,
        getPosition: (h) => h.pos,
        getRadius: (h) => h.radius_m * (1 + 0.012 * pulse),
        getFillColor: [227, 93, 106, Math.round(30 + 16 * pulse)],
        stroked: true,
        getLineColor: [227, 93, 106, 150],
        lineWidthMinPixels: 1.5,
        updateTriggers: { getRadius: [Math.round(t / 160)], getFillColor: [Math.round(t / 160)] },
      }),
      new ScatterplotLayer<Hazard>({
        id: 'hazard-ring',
        data: hazards,
        getPosition: (h) => h.pos,
        getRadius: (h) => h.radius_m * (0.9 + 0.25 * ((t / 2400) % 1)),
        filled: false,
        stroked: true,
        getLineColor: [227, 93, 106, Math.round(120 * (1 - ((t / 2400) % 1)))],
        lineWidthMinPixels: 1.5,
        updateTriggers: { getRadius: [Math.round(t / 120)], getLineColor: [Math.round(t / 120)] },
      }),
    );
  }

  // ---- operator road closures: hard blocks, not just penalties ----
  if (s.navClosures.length) {
    const closures = s.navClosures.filter((c) => c.active);
    if (closures.length) {
      layers.push(
        new ScatterplotLayer<NavClosure>({
          id: 'nav-closures',
          data: closures,
          getPosition: (c) => c.pos,
          getRadius: (c) => Math.max(c.radius_m, 6),
          getFillColor: [255, 92, 92, 72],
          stroked: true,
          getLineColor: [255, 120, 120, 235],
          lineWidthMinPixels: 2,
        }),
        new TextLayer<NavClosure>({
          id: 'nav-closure-labels',
          data: closures,
          getPosition: (c) => [...c.pos, 2],
          getText: () => 'ROAD CLOSED',
          getSize: 9,
          getColor: [255, 170, 170, 240],
          fontFamily: FONT,
          background: true,
          getBackgroundColor: [20, 6, 8, 225],
          backgroundPadding: [3, 1],
        }),
      );
    }
  }

  // ---- buildings (digital passports) ----
  layers.push(
    new PolygonLayer<Building>({
      id: 'buildings',
      data: buildings,
      getPolygon: (b) => b.footprint,
      getFillColor: (b) => buildingColor(b, s, pulse),
      getLineColor: [110, 130, 165, 110],
      lineWidthMinPixels: 1,
      pickable: true,
      autoHighlight: true,
      highlightColor: [77, 159, 255, 190],
      updateTriggers: { getFillColor: [Math.round(t / 160), s.selectedBuilding, s.module] },
    }),
    new TextLayer<Building>({
      id: 'building-labels',
      data: buildings.filter((b) => b.status === 'fire' || b.id === s.selectedBuilding),
      getPosition: (b) => b.center,
      getText: (b) => b.id,
      getSize: 11,
      getColor: [215, 223, 236, 255],
      fontFamily: FONT,
      background: true,
      getBackgroundColor: [8, 12, 20, 235],
      backgroundPadding: [4, 2],
    }),
  );

  // ---- real OSM navigation route ----
  const navLine = navRouteLine(s.navRoute);
  if (navLine.length) {
    const navColor = NAV_PROFILE_META[s.navProfile].rgb;
    const markers = [
      { kind: 'origin' as const, pos: navLine[0] },
      { kind: 'destination' as const, pos: navLine[navLine.length - 1] },
    ];
    layers.push(
      new PathLayer<{ path: LonLat[] }>({
        id: 'nav-route-casing',
        data: [{ path: navLine }],
        getPath: (d) => d.path,
        getColor: [5, 8, 14, 210],
        getWidth: 10,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
      }),
      new PathLayer<{ path: LonLat[] }>({
        id: 'nav-route',
        data: [{ path: navLine }],
        getPath: (d) => d.path,
        getColor: rgba(navColor, 245),
        getWidth: 6,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
      }),
      new ScatterplotLayer<{ kind: 'origin' | 'destination'; pos: LonLat }>({
        id: 'nav-markers',
        data: markers,
        getPosition: (d) => d.pos,
        getRadius: (d) => (d.kind === 'destination' ? 8 : 6),
        radiusUnits: 'pixels',
        getFillColor: (d) => (d.kind === 'destination' ? [227, 93, 106, 255] : [235, 241, 250, 255]),
        stroked: true,
        getLineColor: (d) => (d.kind === 'destination' ? [20, 8, 10, 255] : [10, 14, 22, 255]),
        lineWidthMinPixels: 2,
      }),
      new ScatterplotLayer<{ kind: 'origin' | 'destination'; pos: LonLat }>({
        id: 'nav-destination-ring',
        data: markers.filter((m) => m.kind === 'destination'),
        getPosition: (d) => d.pos,
        getRadius: 14,
        radiusUnits: 'pixels',
        filled: false,
        stroked: true,
        getLineColor: [227, 93, 106, 170],
        lineWidthMinPixels: 1.5,
      }),
      new TextLayer<{ kind: 'origin' | 'destination'; pos: LonLat }>({
        id: 'nav-marker-labels',
        data: markers,
        getPosition: (d) => d.pos,
        getText: (d) => (d.kind === 'destination' ? 'INCIDENT' : 'START'),
        getSize: 9,
        getColor: [225, 232, 244, 255],
        getPixelOffset: [0, 22],
        fontFamily: FONT,
        background: true,
        getBackgroundColor: [8, 12, 20, 225],
        backgroundPadding: [3, 2],
      }),
    );
  }

  // ---- response routes ----
  if (routes.length) {
    const drawable = routes.filter((r) => r.feasible && r.path.length >= 2);
    layers.push(
      new PathLayer<Route>({
        id: 'route-base',
        data: drawable,
        getPath: (r) => r.path,
        getColor: (r) => rgba(PROFILE_META[r.profile].rgb, 80),
        getWidth: 3.5,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
      }),
      new PathLayer<Route>({
        id: 'route-foot',
        data: routes.filter((r) => r.foot_path && r.foot_path.length >= 2 && r.last_mile_m > 8),
        getPath: (r) => r.foot_path ?? [],
        getColor: (r) => rgba(PROFILE_META[r.profile].rgb, 130),
        getWidth: 2,
        widthUnits: 'pixels',
      }),
      new TripsLayer<Route>({
        id: 'route-flow',
        data: drawable,
        getPath: (r) => r.path,
        getTimestamps: (r) => timestamps(r),
        getColor: (r) => rgba(PROFILE_META[r.profile].rgb, 235),
        widthMinPixels: 4,
        fadeTrail: true,
        trailLength: 120,
        currentTime: (t * 0.12) % 650,
        capRounded: true,
        jointRounded: true,
      }),
    );

    // moving responders after dispatch
    if (focus?.dispatched_at && isOpen(focus)) {
      const elapsed = ((now - focus.dispatched_at) / 1000) * CONFIG.timeScale;
      const units: Unit[] = routes
        .filter((r) => r.feasible && r.travel_s > 0 && r.path.length >= 2)
        .map((r) => {
          const p = Math.min(1, elapsed / r.travel_s);
          return { pos: pointAlong(r.path, p), route: r, arrived: p >= 1 };
        });
      layers.push(
        new ScatterplotLayer<Unit>({
          id: 'units',
          data: units,
          getPosition: (u) => u.pos,
          getRadius: 9,
          radiusUnits: 'pixels',
          getFillColor: (u) => rgba(PROFILE_META[u.route.profile].rgb, 255),
          stroked: true,
          getLineColor: [10, 14, 22, 255],
          lineWidthMinPixels: 1.5,
          updateTriggers: { getPosition: [Math.round(t / 100)] },
        }),
        new TextLayer<Unit>({
          id: 'unit-glyph',
          data: units,
          getPosition: (u) => u.pos,
          getText: (u) => PROFILE_META[u.route.profile].glyph,
          getSize: 10,
          getColor: [10, 14, 22, 255],
          fontFamily: FONT,
          fontWeight: 700,
          updateTriggers: { getPosition: [Math.round(t / 100)] },
        }),
      );
    }
  }

  // ---- fire post, medical post, assembly points ----
  const posts = s.laneNodes.filter((n) => n.kind !== 'junction');
  const postColor = (n: LaneNode): RGBA => (n.kind === 'fire_post' ? [227, 93, 106, 255] : n.kind === 'medical_post' ? [87, 168, 232, 255] : [63, 191, 133, 255]);
  layers.push(
    new ScatterplotLayer<LaneNode>({
      id: 'posts',
      data: posts,
      getPosition: (n) => n.pos,
      getRadius: 7,
      radiusUnits: 'pixels',
      getFillColor: postColor,
      stroked: true,
      getLineColor: [10, 14, 22, 255],
      lineWidthMinPixels: 1.5,
    }),
    new TextLayer<LaneNode>({
      id: 'post-labels',
      data: posts,
      getPosition: (n) => n.pos,
      getText: (n) => n.label.toUpperCase(),
      getSize: 10,
      getColor: [190, 205, 228, 255],
      getPixelOffset: [0, 20],
      fontFamily: FONT,
      background: true,
      getBackgroundColor: [8, 12, 20, 225],
      backgroundPadding: [3, 2],
    }),
  );

  // ---- sensor nodes ----
  if (s.layers.sensors) {
    layers.push(
      new ScatterplotLayer<SensorMeta>({
        id: 'sensors',
        data: s.sensors,
        getPosition: (m) => m.pos,
        getRadius: (m) => (sensorColor(m, s).hot ? 4 + 2.5 * pulse : 3.5),
        radiusUnits: 'pixels',
        getFillColor: (m) => sensorColor(m, s).c,
        stroked: true,
        getLineColor: [10, 14, 22, 255],
        lineWidthMinPixels: 1,
        pickable: true,
        updateTriggers: {
          getRadius: [Math.round(t / 160), s.nodeState, s.risks, s.liveState, s.liveRisks, s.mode],
          getFillColor: [s.nodeState, s.risks, s.liveState, s.liveRisks, s.mode],
        },
      }),
    );
    if (zoom >= 17.2) {
      layers.push(
        new TextLayer<SensorMeta>({
          id: 'sensor-labels',
          data: s.sensors,
          getPosition: (m) => m.pos,
          getText: (m) => m.node_id,
          getSize: 9,
          getColor: [140, 158, 190, 235],
          getPixelOffset: [0, -11],
          fontFamily: FONT,
        }),
      );
    }
  }

  return layers;
}

const tipStyle = {
  backgroundColor: 'rgba(8,12,20,0.95)',
  color: '#d7dfec',
  border: '1px solid #232d40',
  borderRadius: '3px',
  fontSize: '11.5px',
  lineHeight: '1.5',
  padding: '7px 9px',
  fontFamily: 'IBM Plex Sans, system-ui, sans-serif',
};

export function tooltipFor(info: PickingInfo, s: StoreState) {
  if (!info.object || !info.layer) return null;
  if (info.layer.id === 'buildings') {
    const b = info.object as Building;
    const facts = [
      `${b.floors} floor${b.floors === 1 ? '' : 's'}`,
      b.year_built > 0 ? `built ${b.year_built}` : 'build year unknown',
      b.construction || 'construction unverified',
    ].join(' · ');
    return {
      html: `<b>${b.id}</b> ${b.name}<br/>${facts}<br/>Inspection priority <b>${b.priority}</b>`,
      style: tipStyle,
    };
  }
  if (info.layer.id === 'sensors') {
    const m = info.object as SensorMeta;
    const v = (s.mode === 'realtime' ? s.liveState[m.node_id]?.values : s.nodeState[m.node_id]?.values) ?? {};
    const vals = Object.entries(v).map(([k, x]) => `${k} ${x}`).join(', ');
    const risk = s.risks[m.node_id];
    const sim = m.simulation === false ? '' : '<br/><span style="color:#e8a63c">SIMULATION</span>';
    const riskLine = risk ? `<br/>Risk <b>${risk.score}</b> (${risk.category})` : '';
    return { html: `<b>${m.node_id}</b><br/>${m.label}<br/>${vals}${riskLine}${sim}`, style: tipStyle };
  }
  return null;
}
