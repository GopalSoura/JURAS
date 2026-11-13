import type { Building, LaneEdge, LaneNode, LonLat, Profile, Route } from '../types';
import { distM, midpoint } from './geo';

interface Arc {
  to: string;
  edge: LaneEdge;
  len: number;
}
export interface Graph {
  nodes: Map<string, LaneNode>;
  adj: Map<string, Arc[]>;
}
export interface Ctx {
  hazards: { pos: LonLat; radius_m: number }[];
  floods: { pos: LonLat; radius_m: number; depth_cm: number }[];
}
export interface Posts {
  fire: string;
  medical: string;
  assemblies: string[];
}

export function buildGraph(nodes: LaneNode[], edges: LaneEdge[]): Graph {
  const nm = new Map(nodes.map((n) => [n.id, n]));
  const adj = new Map<string, Arc[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    const a = nm.get(e.a);
    const b = nm.get(e.b);
    if (!a || !b) continue;
    const len = distM(a.pos, b.pos);
    adj.get(e.a)!.push({ to: e.b, edge: e, len });
    adj.get(e.b)!.push({ to: e.a, edge: e, len });
  }
  return { nodes: nm, adj };
}

// Vehicle / responder constraints. Width in metres is the clear lane width.
const SPEC: Record<Profile, { minWidth: number; stairs: boolean }> = {
  fire_truck: { minWidth: 3.5, stairs: false },
  medical: { minWidth: 1.2, stairs: false },
  evacuation: { minWidth: 0.9, stairs: true },
};

function speed(p: Profile, e: LaneEdge): number {
  if (p === 'fire_truck') return e.width_m >= 6 ? 8 : 4.2;
  if (p === 'medical') return e.width_m >= 2.4 ? 5.5 : 1.5;
  return e.stairs ? 0.8 : 1.3;
}

function arcCost(g: Graph, p: Profile, arc: Arc, from: string, ctx: Ctx): number | null {
  const e = arc.edge;
  if (e.width_m < SPEC[p].minWidth) return null;
  if (e.stairs && !SPEC[p].stairs) return null;
  const mid = midpoint(g.nodes.get(from)!.pos, g.nodes.get(arc.to)!.pos);
  let mult = 1;
  for (const h of ctx.hazards) if (distM(mid, h.pos) <= h.radius_m + 10) mult *= 6;
  for (const f of ctx.floods) {
    if (distM(mid, f.pos) <= f.radius_m + 6) {
      if (p === 'fire_truck' && f.depth_cm >= 25) return null;
      mult *= 1 + f.depth_cm / 30;
    }
  }
  return (arc.len / speed(p, e)) * mult;
}

interface Search {
  cost: Map<string, number>;
  prev: Map<string, { from: string; arc: Arc }>;
}

function dijkstra(g: Graph, src: string, p: Profile, ctx: Ctx): Search {
  const cost = new Map<string, number>([[src, 0]]);
  const prev = new Map<string, { from: string; arc: Arc }>();
  const done = new Set<string>();
  for (;;) {
    let u: string | null = null;
    let best = Infinity;
    for (const [id, c] of cost) {
      if (!done.has(id) && c < best) {
        best = c;
        u = id;
      }
    }
    if (u === null) break;
    done.add(u);
    for (const arc of g.adj.get(u) ?? []) {
      const c = arcCost(g, p, arc, u, ctx);
      if (c === null) continue;
      const nc = best + c;
      if (nc < (cost.get(arc.to) ?? Infinity)) {
        cost.set(arc.to, nc);
        prev.set(arc.to, { from: u, arc });
      }
    }
  }
  return { cost, prev };
}

function chain(s: Search, to: string): { ids: string[]; arcs: Arc[] } {
  const ids = [to];
  const arcs: Arc[] = [];
  let cur = to;
  while (s.prev.has(cur)) {
    const { from, arc } = s.prev.get(cur)!;
    arcs.unshift(arc);
    ids.unshift(from);
    cur = from;
  }
  return { ids, arcs };
}

const travelTime = (p: Profile, arcs: Arc[]) => arcs.reduce((t, a) => t + a.len / speed(p, a.edge), 0);
const lengthOf = (arcs: Arc[]) => arcs.reduce((t, a) => t + a.len, 0);
const round = (v: number) => Math.round(v);

export function planRoutes(g: Graph, args: { building: Building; posts: Posts; ctx: Ctx }): Route[] {
  const { building: b, posts, ctx } = args;
  const name = (id: string) => g.nodes.get(id)?.label ?? id;
  const pos = (id: string) => g.nodes.get(id)!.pos;
  const out: Route[] = [];

  // ---- fire tender: may stop short of the building and lay hose ----
  {
    const s = dijkstra(g, posts.fire, 'fire_truck', ctx);
    let target = b.access_node;
    if (!s.cost.has(target)) {
      let best = Infinity;
      for (const id of s.cost.keys()) {
        const d = distM(pos(id), b.center);
        if (d < best) {
          best = d;
          target = id;
        }
      }
    }
    const { ids, arcs } = chain(s, target);
    const lastMile = distM(pos(target), b.center);
    const full = target === b.access_node && lastMile < 45;
    const travel = travelTime('fire_truck', arcs);
    const tightest = Math.min(...arcs.map((a) => a.edge.width_m));
    out.push({
      profile: 'fire_truck',
      path: ids.map(pos),
      foot_path: [pos(target), b.center],
      length_m: round(lengthOf(arcs)),
      travel_s: round(travel),
      eta_s: round(travel + lastMile / 1.2),
      feasible: true,
      last_mile_m: round(lastMile),
      note: full
        ? `Full tender access. Tightest lane ${tightest.toFixed(1)} m.`
        : `Tender stops at ${name(target)}. Last ${round(lastMile)} m by hose lay.`,
      from: name(posts.fire),
      to: name(target),
    });
  }

  // ---- medical micro-team: narrow-lane capable, no stairs (stretcher) ----
  {
    const s = dijkstra(g, posts.medical, 'medical', ctx);
    const ok = s.cost.has(b.access_node);
    let target = b.access_node;
    if (!ok) {
      let best = Infinity;
      for (const id of s.cost.keys()) {
        const d = distM(pos(id), b.center);
        if (d < best) {
          best = d;
          target = id;
        }
      }
    }
    const { ids, arcs } = chain(s, target);
    const lastMile = distM(pos(target), b.center);
    const travel = travelTime('medical', arcs);
    out.push({
      profile: 'medical',
      path: ids.map(pos),
      foot_path: [pos(target), b.center],
      length_m: round(lengthOf(arcs)),
      travel_s: round(travel),
      eta_s: round(travel + lastMile / 1.3),
      feasible: true,
      last_mile_m: round(lastMile),
      note: ok ? 'Light vehicle to the lane head, then on foot with stretcher.' : `Stops at ${name(target)}; stairs block stretcher access.`,
      from: name(posts.medical),
      to: name(target),
    });
  }

  // ---- evacuation: on foot from the building to the nearest assembly point ----
  {
    const s = dijkstra(g, b.access_node, 'evacuation', ctx);
    let best = Infinity;
    let target = posts.assemblies[0];
    for (const id of posts.assemblies) {
      const c = s.cost.get(id);
      if (c !== undefined && c < best) {
        best = c;
        target = id;
      }
    }
    const reachable = s.cost.has(target);
    const { ids, arcs } = reachable ? chain(s, target) : { ids: [b.access_node], arcs: [] as Arc[] };
    const first = distM(b.center, pos(b.access_node));
    const stairs = arcs.filter((a) => a.edge.stairs).length;
    out.push({
      profile: 'evacuation',
      path: [b.center, ...ids.map(pos)],
      length_m: round(lengthOf(arcs) + first),
      travel_s: round(travelTime('evacuation', arcs) + first / 1.3),
      eta_s: round(travelTime('evacuation', arcs) + first / 1.3),
      feasible: reachable,
      last_mile_m: 0,
      note: reachable
        ? `To ${name(target)}. ${stairs ? `${stairs} stair segment${stairs > 1 ? 's' : ''}, assist elderly.` : 'Step-free route.'}`
        : 'No safe route found. Shelter in place and call for rescue.',
      from: b.name,
      to: name(target),
    });
  }

  return out;
}
