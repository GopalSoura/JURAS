import { PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import type { Layer, PickingInfo } from '@deck.gl/core';
import type { Building, FloodZone, Hazard, LaneEdge, LaneNode, LonLat, Route, SensorMeta } from '../types';
import type { StoreState } from '../store';
import { CONFIG } from '../config';
import { cumulative, distM, midpoint, pointAlong } from './geo';
import { focusAlert, isOpen } from './metrics';
import { PROFILE_META, type RGB } from './meta';

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
  if (b.status === 'fire') return [255, 70, 60, Math.round(185 + pulse * 60)];
  if (s.selectedBuilding === b.id) return [90, 205, 255, 235];
  if (s.module === 'structure') {
    const k = Math.min(1, Math.max(0, (b.priority - 30) / 60));
    return [Math.round(60 + 195 * k), Math.round(115 + 40 * (1 - k)), Math.round(180 - 120 * k), 215];
  }
  if (b.status === 'inspect') return [255, 140, 60, 220];
  if (b.status === 'watch') return [255, 190, 60, 205];
  return [72, 112, 178, 200];
}

function sensorColor(m: SensorMeta, s: StoreState): { c: RGBA; hot: boolean } {
  const v = s.nodeState[m.node_id]?.values;
  if (v) {
    if (m.kind === 'smoke_temp' && (v.smoke_ppm > 120 || v.temp_c > 45)) return { c: [255, 77, 94, 255], hot: true };
    if (m.kind === 'structure' && (v.tilt_deg >= 0.45 || v.crack_mm >= 0.55)) return { c: [255, 150, 60, 255], hot: true };
    if (m.kind === 'rain_level' && v.level_cm >= 3) return { c: [80, 170, 255, 255], hot: true };
  }
  if (m.kind === 'smoke_temp') return { c: [255, 170, 120, 235], hot: false };
  if (m.kind === 'structure') return { c: [190, 160, 255, 235], hot: false };
  return { c: [110, 210, 255, 235], hot: false };
}

export function buildLayers(s: StoreState, t: number, now: number, zoom: number): Layer[] {
  const pulse = 0.5 + 0.5 * Math.sin(t / 260);
  const nodePos = new Map<string, LonLat>(s.laneNodes.map((n) => [n.id, n.pos]));
  const buildings = Object.values(s.buildings);
  const height = new Map(buildings.map((b) => [b.id, b.height_m]));
  const focus = focusAlert(s.alerts, s.routes, s.selectedAlert);
  const routes = focus ? s.routes[focus.id] ?? [] : [];
  const hazards = Object.values(s.hazards).filter((h) => h.active);
  const layers: Layer[] = [];

  // ---- lane network, coloured by what can use it ----
  if (s.layers.lanes) {
    const flooded = (e: LaneEdge) => {
      const a = nodePos.get(e.a);
      const b = nodePos.get(e.b);
      if (!a || !b) return false;
      const mid = midpoint(a, b);
      return s.floodZones.some((z) => distM(mid, z.center) <= z.radius_m + 6);
    };
    layers.push(
      new PathLayer<LaneEdge>({
        id: 'lanes',
        data: s.laneEdges,
        getPath: (e) => [nodePos.get(e.a) ?? [0, 0], nodePos.get(e.b) ?? [0, 0]],
        getColor: (e) => (flooded(e) ? [70, 160, 255, 210] : e.stairs ? [255, 176, 46, 170] : e.width_m >= 3.5 ? [90, 200, 255, 120] : [110, 140, 205, 110]),
        getWidth: (e) => Math.max(1.4, e.width_m * 0.5),
        widthUnits: 'meters',
        widthMinPixels: 1.5,
        capRounded: true,
        jointRounded: true,
        updateTriggers: { getColor: [s.floodZones] },
      }),
    );
  }

  // ---- flood zones ----
  if (s.layers.flood && s.floodZones.length) {
    layers.push(
      new PolygonLayer<FloodZone>({
        id: 'flood',
        data: s.floodZones,
        getPolygon: (z) => z.polygon,
        getFillColor: [50, 140, 255, 95],
        getLineColor: [130, 205, 255, 220],
        lineWidthMinPixels: 2,
        stroked: true,
        filled: true,
        getElevation: 0.3,
      }),
      new TextLayer<FloodZone>({
        id: 'flood-labels',
        data: s.floodZones,
        getPosition: (z) => [...z.center, 2],
        getText: (z) => z.label,
        getSize: 12,
        getColor: [200, 235, 255, 255],
        fontFamily: FONT,
        background: true,
        getBackgroundColor: [8, 20, 44, 220],
        backgroundPadding: [4, 2],
      }),
    );
  }

  // ---- fire hazard zone ----
  if (hazards.length) {
    layers.push(
      new ScatterplotLayer<Hazard>({
        id: 'hazard-fill',
        data: hazards,
        getPosition: (h) => h.pos,
        getRadius: (h) => h.radius_m * (1 + 0.04 * pulse),
        getFillColor: [255, 60, 50, Math.round(46 + 34 * pulse)],
        stroked: true,
        getLineColor: [255, 90, 80, 230],
        lineWidthMinPixels: 2,
        updateTriggers: { getRadius: [Math.round(t / 80)], getFillColor: [Math.round(t / 80)] },
      }),
      new ScatterplotLayer<Hazard>({
        id: 'hazard-ring',
        data: hazards,
        getPosition: (h) => h.pos,
        getRadius: (h) => h.radius_m * (0.55 + 0.9 * ((t / 1800) % 1)),
        filled: false,
        stroked: true,
        getLineColor: [255, 110, 90, Math.round(200 * (1 - ((t / 1800) % 1)))],
        lineWidthMinPixels: 2,
        updateTriggers: { getRadius: [Math.round(t / 40)], getLineColor: [Math.round(t / 40)] },
      }),
    );
  }

  // ---- buildings (digital passports) ----
  layers.push(
    new PolygonLayer<Building>({
      id: 'buildings',
      data: buildings,
      getPolygon: (b) => b.footprint,
      extruded: true,
      getElevation: (b) => b.height_m,
      getFillColor: (b) => buildingColor(b, s, pulse),
      getLineColor: [170, 205, 255, 150],
      lineWidthMinPixels: 1,
      pickable: true,
      autoHighlight: true,
      highlightColor: [120, 210, 255, 210],
      material: { ambient: 0.55, diffuse: 0.7, shininess: 24, specularColor: [90, 120, 190] },
      updateTriggers: { getFillColor: [Math.round(t / 80), s.selectedBuilding, s.module] },
    }),
    new TextLayer<Building>({
      id: 'building-labels',
      data: buildings.filter((b) => b.status === 'fire' || b.id === s.selectedBuilding),
      getPosition: (b) => [...b.center, b.height_m + 4],
      getText: (b) => b.id,
      getSize: 12,
      getColor: [235, 244, 255, 255],
      fontFamily: FONT,
      background: true,
      getBackgroundColor: [8, 14, 30, 230],
      backgroundPadding: [4, 2],
    }),
  );

  // ---- response routes ----
  if (routes.length) {
    layers.push(
      new PathLayer<Route>({
        id: 'route-base',
        data: routes,
        getPath: (r) => r.path,
        getColor: (r) => rgba(PROFILE_META[r.profile].rgb, 95),
        getWidth: 4,
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
      }),
      new PathLayer<Route>({
        id: 'route-foot',
        data: routes.filter((r) => r.foot_path && r.last_mile_m > 8),
        getPath: (r) => r.foot_path ?? [],
        getColor: (r) => rgba(PROFILE_META[r.profile].rgb, 150),
        getWidth: 2.5,
        widthUnits: 'pixels',
      }),
      new TripsLayer<Route>({
        id: 'route-flow',
        data: routes.filter((r) => r.feasible),
        getPath: (r) => r.path,
        getTimestamps: (r) => timestamps(r),
        getColor: (r) => rgba(PROFILE_META[r.profile].rgb, 255),
        widthMinPixels: 5,
        fadeTrail: true,
        trailLength: 140,
        currentTime: (t * 0.14) % 700,
        capRounded: true,
        jointRounded: true,
      }),
    );

    // moving responders after dispatch
    if (focus?.dispatched_at && isOpen(focus)) {
      const elapsed = ((now - focus.dispatched_at) / 1000) * CONFIG.timeScale;
      const units: Unit[] = routes
        .filter((r) => r.feasible && r.travel_s > 0)
        .map((r) => {
          const p = Math.min(1, elapsed / r.travel_s);
          return { pos: pointAlong(r.path, p), route: r, arrived: p >= 1 };
        });
      layers.push(
        new ScatterplotLayer<Unit>({
          id: 'units',
          data: units,
          getPosition: (u) => [...u.pos, 3],
          getRadius: 11,
          radiusUnits: 'pixels',
          getFillColor: (u) => rgba(PROFILE_META[u.route.profile].rgb, 255),
          stroked: true,
          getLineColor: [255, 255, 255, 255],
          lineWidthMinPixels: 2,
          updateTriggers: { getPosition: [Math.round(t / 100)] },
        }),
        new TextLayer<Unit>({
          id: 'unit-glyph',
          data: units,
          getPosition: (u) => [...u.pos, 3],
          getText: (u) => PROFILE_META[u.route.profile].glyph,
          getSize: 13,
          getColor: [6, 10, 20, 255],
          fontFamily: FONT,
          fontWeight: 700,
          updateTriggers: { getPosition: [Math.round(t / 100)] },
        }),
      );
    }
  }

  // ---- fire post, medical post, assembly points ----
  const posts = s.laneNodes.filter((n) => n.kind !== 'junction');
  const postColor = (n: LaneNode): RGBA => (n.kind === 'fire_post' ? [255, 90, 80, 255] : n.kind === 'medical_post' ? [77, 181, 255, 255] : [47, 227, 154, 255]);
  layers.push(
    new ScatterplotLayer<LaneNode>({
      id: 'posts',
      data: posts,
      getPosition: (n) => n.pos,
      getRadius: 9,
      radiusUnits: 'pixels',
      getFillColor: postColor,
      stroked: true,
      getLineColor: [255, 255, 255, 230],
      lineWidthMinPixels: 2,
    }),
    new TextLayer<LaneNode>({
      id: 'post-labels',
      data: posts,
      getPosition: (n) => n.pos,
      getText: (n) => n.label.toUpperCase(),
      getSize: 11,
      getColor: [210, 225, 255, 255],
      getPixelOffset: [0, 22],
      fontFamily: FONT,
      background: true,
      getBackgroundColor: [8, 14, 30, 220],
      backgroundPadding: [4, 2],
    }),
  );

  // ---- sensor nodes ----
  if (s.layers.sensors) {
    layers.push(
      new ScatterplotLayer<SensorMeta>({
        id: 'sensors',
        data: s.sensors,
        getPosition: (m) => [...m.pos, (height.get(m.building_id ?? '') ?? 0) + 1.5],
        getRadius: (m) => (sensorColor(m, s).hot ? 5 + 4 * pulse : 4.5),
        radiusUnits: 'pixels',
        getFillColor: (m) => sensorColor(m, s).c,
        stroked: true,
        getLineColor: [10, 16, 32, 255],
        lineWidthMinPixels: 1.5,
        pickable: true,
        updateTriggers: { getRadius: [Math.round(t / 80), s.nodeState], getFillColor: [s.nodeState] },
      }),
    );
    if (zoom >= 17.2) {
      layers.push(
        new TextLayer<SensorMeta>({
          id: 'sensor-labels',
          data: s.sensors,
          getPosition: (m) => [...m.pos, (height.get(m.building_id ?? '') ?? 0) + 1.5],
          getText: (m) => m.node_id,
          getSize: 10,
          getColor: [150, 170, 215, 255],
          getPixelOffset: [0, -13],
          fontFamily: FONT,
        }),
      );
    }
  }

  return layers;
}

const tipStyle = {
  backgroundColor: 'rgba(8,14,30,0.95)',
  color: '#dbe6ff',
  border: '1px solid #1d2b4d',
  borderRadius: '6px',
  fontSize: '12px',
  lineHeight: '1.5',
  padding: '8px 10px',
  fontFamily: 'IBM Plex Sans, system-ui, sans-serif',
};

export function tooltipFor(info: PickingInfo, s: StoreState) {
  if (!info.object || !info.layer) return null;
  if (info.layer.id === 'buildings') {
    const b = info.object as Building;
    return {
      html: `<b>${b.id}</b> ${b.name}<br/>${b.floors} floors, built ${b.year_built}<br/>${b.construction}<br/>Inspection priority <b>${b.priority}</b>`,
      style: tipStyle,
    };
  }
  if (info.layer.id === 'sensors') {
    const m = info.object as SensorMeta;
    const v = s.nodeState[m.node_id]?.values ?? {};
    const vals = Object.entries(v).map(([k, x]) => `${k} ${x}`).join(', ');
    return { html: `<b>${m.node_id}</b><br/>${m.label}<br/>${vals}`, style: tipStyle };
  }
  return null;
}
