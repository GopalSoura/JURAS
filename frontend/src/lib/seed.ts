import type { Alert, Building, Intervention, LaneEdge, LaneNode, SensorMeta } from '../types';
import { distM, rectPolygon, xy } from './geo';
import type { Posts } from './routing';

// ILLUSTRATIVE pilot-zone data. Coordinates are placed on a local metre grid around Old Jammu
// and are NOT surveyed. Replace with JMC GIS / OSM-derived layers from the backend snapshot.

const node = (id: string, x: number, y: number, kind: LaneNode['kind'], label?: string): LaneNode => ({
  id,
  pos: xy(x, y),
  kind,
  label: label ?? `Junction ${id}`,
});

export const LANE_NODES: LaneNode[] = [
  node('A', -300, -160, 'fire_post', 'Fire Post (demo)'),
  node('B', -150, -160, 'junction'),
  node('C', 0, -160, 'junction'),
  node('D', 160, -160, 'junction'),
  node('E', 300, -160, 'medical_post', 'Medical Post (demo)'),
  node('F', -300, 0, 'junction'),
  node('G', -300, 140, 'assembly', 'Assembly AP-1'),
  node('H', -150, -40, 'junction'),
  node('I', -150, 70, 'junction'),
  node('J', -150, 170, 'junction'),
  node('K', 0, -60, 'junction'),
  node('L', 0, 50, 'junction'),
  node('M', 0, 160, 'junction'),
  node('N', 160, -60, 'junction'),
  node('O', 160, 60, 'junction'),
  node('P', 160, 170, 'junction'),
  node('Q', 300, 40, 'assembly', 'Assembly AP-2'),
];

const edge = (a: string, b: string, width_m: number, stairs = false): LaneEdge => ({ id: `${a}-${b}`, a, b, width_m, stairs });

export const LANE_EDGES: LaneEdge[] = [
  edge('A', 'B', 7), edge('B', 'C', 7), edge('C', 'D', 7), edge('D', 'E', 7),
  edge('A', 'F', 6), edge('F', 'G', 5),
  edge('B', 'H', 3.2), edge('H', 'I', 3.8), edge('I', 'J', 4),
  edge('C', 'K', 4.2), edge('K', 'L', 2.4), edge('L', 'M', 2.4),
  edge('D', 'N', 3.6), edge('N', 'O', 1.8, true), edge('O', 'P', 1.8),
  edge('H', 'K', 3.6), edge('K', 'N', 3.6),
  edge('I', 'L', 3.2), edge('L', 'O', 1.6, true),
  edge('J', 'M', 3), edge('M', 'P', 2),
  edge('G', 'J', 4.5), edge('F', 'H', 2.8),
  edge('E', 'Q', 6), edge('Q', 'O', 2.8),
];

export const POSTS: Posts = { fire: 'A', medical: 'E', assemblies: ['G', 'Q'] };

interface Def {
  id: string; name: string; x: number; y: number; w: number; d: number; rot: number;
  floors: number; year: number; use: string; construction: string; occ: number; priority: number;
  tilt?: number; crack?: number; inspected: string;
}

const DEFS: Def[] = [
  { id: 'B-014', name: 'Raghunath Bazaar Block 14', x: -60, y: -100, w: 22, d: 14, rot: 8, floors: 3, year: 1928, use: 'Mixed use', construction: 'Brick masonry', occ: 140, priority: 62, inspected: '2025-11-14' },
  { id: 'B-021', name: 'Purani Mandi Timber Store', x: 30, y: 70, w: 18, d: 12, rot: -6, floors: 2, year: 1951, use: 'Storage', construction: 'Timber frame', occ: 12, priority: 71, inspected: '2025-08-02' },
  { id: 'B-007', name: 'Mohalla Haveli Complex', x: -190, y: 100, w: 26, d: 20, rot: 4, floors: 4, year: 1910, use: 'Residential', construction: 'Brick-lime masonry', occ: 96, priority: 82, tilt: 0.52, crack: 0.6, inspected: '2025-03-21' },
  { id: 'B-032', name: 'Kanak Mandi Textile Shops', x: -110, y: -110, w: 24, d: 12, rot: 0, floors: 2, year: 1962, use: 'Commercial', construction: 'Brick masonry', occ: 60, priority: 48, inspected: '2026-01-09' },
  { id: 'B-045', name: 'Rani Bagh Row Houses', x: -230, y: -60, w: 30, d: 12, rot: -3, floors: 3, year: 1974, use: 'Residential', construction: 'RCC frame', occ: 110, priority: 39, inspected: '2026-02-17' },
  { id: 'B-052', name: 'Mubarak Dharamshala', x: 110, y: -110, w: 20, d: 20, rot: 10, floors: 3, year: 1936, use: 'Institutional', construction: 'Stone masonry', occ: 80, priority: 77, tilt: 0.18, crack: 0.2, inspected: '2025-05-30' },
  { id: 'B-061', name: 'Gole Market Arcade', x: 200, y: -105, w: 28, d: 14, rot: 0, floors: 2, year: 1968, use: 'Commercial', construction: 'RCC frame', occ: 90, priority: 44, inspected: '2026-03-04' },
  { id: 'B-066', name: 'Bazaar Chowk Sweet Shops', x: 75, y: -35, w: 16, d: 12, rot: 5, floors: 2, year: 1955, use: 'Food and commercial', construction: 'Mixed masonry', occ: 45, priority: 58, inspected: '2025-10-12' },
  { id: 'B-073', name: 'Shiv Gali Tenements', x: -80, y: 10, w: 18, d: 14, rot: -8, floors: 4, year: 1940, use: 'Residential', construction: 'Brick-lime masonry', occ: 88, priority: 68, tilt: 0.21, crack: 0.3, inspected: '2025-07-19' },
  { id: 'B-081', name: 'Old Post Office Annex', x: -45, y: 115, w: 22, d: 16, rot: 0, floors: 2, year: 1925, use: 'Government', construction: 'Stone masonry', occ: 35, priority: 55, tilt: 0.12, crack: 0.15, inspected: '2025-12-01' },
  { id: 'B-088', name: 'Chowk Residential Block', x: 215, y: 20, w: 20, d: 16, rot: 6, floors: 3, year: 1981, use: 'Residential', construction: 'RCC frame', occ: 74, priority: 33, inspected: '2026-04-22' },
  { id: 'B-095', name: 'Lakhdata Bazaar Shops', x: 120, y: 130, w: 26, d: 14, rot: 0, floors: 2, year: 1948, use: 'Commercial', construction: 'Brick masonry', occ: 52, priority: 64, inspected: '2025-09-08' },
  { id: 'B-102', name: 'Temple Lane Guest House', x: -235, y: 170, w: 18, d: 16, rot: -4, floors: 3, year: 1990, use: 'Hospitality', construction: 'RCC frame', occ: 40, priority: 30, inspected: '2026-05-11' },
  { id: 'B-109', name: 'Mandi Warehouse', x: 245, y: -50, w: 24, d: 18, rot: 0, floors: 1, year: 1971, use: 'Storage', construction: 'Steel and brick', occ: 8, priority: 52, inspected: '2025-06-26' },
];

export function makeBuildings(): Building[] {
  return DEFS.map((d) => {
    const center = xy(d.x, d.y);
    let access = LANE_NODES[0];
    let best = Infinity;
    for (const n of LANE_NODES) {
      const dist = distM(n.pos, center);
      if (dist < best) {
        best = dist;
        access = n;
      }
    }
    return {
      id: d.id,
      name: d.name,
      center,
      footprint: rectPolygon(center, d.w, d.d, d.rot),
      floors: d.floors,
      height_m: Math.round(d.floors * 3.3 * 10) / 10,
      year_built: d.year,
      use: d.use,
      construction: d.construction,
      occupancy: d.occ,
      priority: d.priority,
      status: (d.tilt ?? 0) >= 0.45 ? 'watch' : 'ok',
      tilt_deg: d.tilt ?? 0.06,
      crack_mm: d.crack ?? 0.1,
      last_inspection: d.inspected,
      access_node: access.id,
    };
  });
}

const sensor = (node_id: string, kind: SensorMeta['kind'], pos: SensorMeta['pos'], label: string, building_id?: string): SensorMeta => ({ node_id, kind, pos, label, building_id });

export function makeSensors(buildings: Building[]): SensorMeta[] {
  const c = (id: string) => buildings.find((b) => b.id === id)!.center;
  const sm: [string, string, string][] = [
    ['JM-014', 'B-014', 'Smoke + temp, B-014'],
    ['JM-021a', 'B-021', 'Smoke + temp, B-021 front'],
    ['JM-021b', 'B-021', 'Smoke + temp, B-021 rear'],
    ['JM-052', 'B-052', 'Smoke + temp, B-052'],
    ['JM-066', 'B-066', 'Smoke + temp, B-066'],
    ['JM-073', 'B-073', 'Smoke + temp, B-073'],
    ['JM-095', 'B-095', 'Smoke + temp, B-095'],
  ];
  const st: [string, string, string][] = [
    ['JM-S07', 'B-007', 'Tilt + crack, B-007'],
    ['JM-S52', 'B-052', 'Tilt + crack, B-052'],
    ['JM-S73', 'B-073', 'Tilt + crack, B-073'],
    ['JM-S81', 'B-081', 'Tilt + crack, B-081'],
  ];
  return [
    ...sm.map(([id, b, label], i) => {
      const p = c(b);
      return sensor(id, 'smoke_temp', [p[0] + (i % 2 ? 0.00004 : -0.00004), p[1]], label, b);
    }),
    ...st.map(([id, b, label]) => sensor(id, 'structure', c(b), label, b)),
    sensor('JM-R01', 'rain_level', xy(-75, 60), 'Lane I-L low point'),
    sensor('JM-R02', 'rain_level', xy(160, 60), 'Junction O'),
    sensor('JM-R03', 'rain_level', xy(0, 160), 'Lane M sump'),
  ];
}

// How strongly each low point collects water during heavy rain.
export const FLOOD_FACTOR: Record<string, number> = { 'JM-R01': 1, 'JM-R02': 0.6, 'JM-R03': 0.8 };

export const INTERVENTION_DEFS: Omit<Intervention, 'rank'>[] = [
  { id: 'IV-1', name: 'Rain garden and bioswale', where: 'Open plot near Junction I', pos: xy(-175, 95), reduces_pct: 28, cost_lakh: 6 },
  { id: 'IV-2', name: 'Desilt and upsize drain', where: 'Junction K', pos: xy(0, -60), reduces_pct: 22, cost_lakh: 3 },
  { id: 'IV-3', name: 'Permeable paving', where: 'Lane I-L', pos: xy(-75, 60), reduces_pct: 18, cost_lakh: 4.5 },
  { id: 'IV-4', name: 'Recharge pit', where: 'Assembly AP-1 ground', pos: xy(-300, 140), reduces_pct: 15, cost_lakh: 2.4 },
];

export function rankInterventions(): Intervention[] {
  return [...INTERVENTION_DEFS]
    .sort((a, b) => b.reduces_pct / b.cost_lakh - a.reduces_pct / a.cost_lakh)
    .map((x, i) => ({ ...x, rank: i + 1 }));
}

export function seedAlerts(now: number, buildings: Building[]): Alert[] {
  const m = 60_000;
  const b7 = buildings.find((b) => b.id === 'B-007')!;
  return [
    {
      id: 'AL-STR-B-007', module: 'structure', severity: 'medium', status: 'ack',
      title: 'Tilt watch, B-007', detail: `${b7.name}, built ${b7.year_built}, ${b7.construction}`,
      building_id: 'B-007', pos: b7.center, confidence: 0.66,
      sources: [{ kind: 'sensor', label: 'JM-S07: tilt 0.52°, crack 0.6 mm', ts: now - 40 * m }],
      created_at: now - 3 * 60 * m, updated_at: now - 40 * m,
      recommendation: 'Keep on weekly review. Engineer to validate if tilt passes 0.8°.',
    },
    {
      id: 'AL-MAP-L-O', module: 'map', severity: 'low', status: 'new',
      title: 'Lane attribute mismatch, L-O', detail: 'Stairs reported on a segment mapped as step-free',
      pos: xy(80, 55), confidence: 0.62,
      sources: [
        { kind: 'citizen', label: '2 rider observations, opt-in', ts: now - 52 * m },
        { kind: 'field', label: 'Pending field verification', ts: now - 52 * m },
      ],
      created_at: now - 55 * m, updated_at: now - 52 * m,
      recommendation: 'Send for field verification. Routing already treats the segment as stairs.',
    },
    {
      id: 'AL-RES-1', module: 'fire', severity: 'low', status: 'resolved',
      title: 'Smoke spike cleared, JM-066', detail: 'Cooking smoke at a sweet shop. Single sensor, not confirmed.',
      building_id: 'B-066', pos: buildings.find((b) => b.id === 'B-066')!.center, confidence: 0.38,
      sources: [{ kind: 'sensor', label: 'JM-066: smoke 210 ppm, 36 °C', ts: now - 5 * 60 * m }],
      created_at: now - 5 * 60 * m, updated_at: now - 4.9 * 60 * m,
    },
    {
      id: 'AL-RES-2', module: 'flood', severity: 'medium', status: 'resolved',
      title: 'Drain overflow, Junction K', detail: 'Cleared after desilting crew visit',
      pos: xy(0, -60), confidence: 0.81,
      sources: [{ kind: 'citizen', label: 'Grievance via digital door number', ts: now - 7 * 60 * m }],
      created_at: now - 7 * 60 * m, updated_at: now - 6 * 60 * m,
    },
    {
      id: 'AL-RES-3', module: 'map', severity: 'low', status: 'resolved',
      title: 'Blocked lane cleared, L-M', detail: 'Temporary obstruction removed, lane re-verified',
      pos: xy(0, 105), confidence: 0.9,
      sources: [{ kind: 'field', label: 'Field team verification', ts: now - 8 * 60 * m }],
      created_at: now - 8 * 60 * m, updated_at: now - 7.5 * 60 * m,
    },
    {
      id: 'AL-RES-4', module: 'structure', severity: 'low', status: 'resolved',
      title: 'Low battery replaced, JM-S81', detail: 'Node back online',
      building_id: 'B-081', pos: buildings.find((b) => b.id === 'B-081')!.center, confidence: 1,
      sources: [{ kind: 'sensor', label: 'JM-S81: battery 9%', ts: now - 9 * 60 * m }],
      created_at: now - 9 * 60 * m, updated_at: now - 8.8 * 60 * m,
    },
  ];
}
