import type { LonLat } from '../types';

// Local metre grid around the pilot zone centre (Old Jammu, near Raghunath Bazaar).
export const ORIGIN: LonLat = [74.8575, 32.7285];
const M_LAT = 110574;
const M_LON = 111320 * Math.cos((ORIGIN[1] * Math.PI) / 180);

export const xy = (x: number, y: number): LonLat => [ORIGIN[0] + x / M_LON, ORIGIN[1] + y / M_LAT];

export const distM = (a: LonLat, b: LonLat): number =>
  Math.hypot((a[0] - b[0]) * M_LON, (a[1] - b[1]) * M_LAT);

export const midpoint = (a: LonLat, b: LonLat): LonLat => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

/** Closest point on a segment, in the same local metre grid used by distM. */
export function nearestOnSegment(p: LonLat, a: LonLat, b: LonLat): { point: LonLat; distance_m: number } {
  const px = (p[0] - ORIGIN[0]) * M_LON;
  const py = (p[1] - ORIGIN[1]) * M_LAT;
  const ax = (a[0] - ORIGIN[0]) * M_LON;
  const ay = (a[1] - ORIGIN[1]) * M_LAT;
  const dx = (b[0] - a[0]) * M_LON;
  const dy = (b[1] - a[1]) * M_LAT;
  const lenSq = dx * dx + dy * dy;
  if (lenSq <= 0) return { point: [...a] as LonLat, distance_m: distM(p, a) };
  const u = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq));
  const point: LonLat = [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
  return { point, distance_m: distM(p, point) };
}

export function cumulative(path: LonLat[]): number[] {
  const out = [0];
  for (let i = 1; i < path.length; i++) out.push(out[i - 1] + distM(path[i - 1], path[i]));
  return out;
}

export const pathLength = (path: LonLat[]): number => {
  const c = cumulative(path);
  return c[c.length - 1] ?? 0;
};

export function pointAlong(path: LonLat[], frac: number): LonLat {
  if (path.length === 0) return ORIGIN;
  if (path.length === 1) return path[0];
  const cum = cumulative(path);
  const target = Math.min(1, Math.max(0, frac)) * cum[cum.length - 1];
  for (let i = 1; i < cum.length; i++) {
    if (target <= cum[i]) {
      const seg = cum[i] - cum[i - 1] || 1;
      const k = (target - cum[i - 1]) / seg;
      return [path[i - 1][0] + (path[i][0] - path[i - 1][0]) * k, path[i - 1][1] + (path[i][1] - path[i - 1][1]) * k];
    }
  }
  return path[path.length - 1];
}

function offset(center: LonLat, dx: number, dy: number, rotDeg: number): LonLat {
  const r = (rotDeg * Math.PI) / 180;
  const x = dx * Math.cos(r) - dy * Math.sin(r);
  const y = dx * Math.sin(r) + dy * Math.cos(r);
  return [center[0] + x / M_LON, center[1] + y / M_LAT];
}

export function rectPolygon(center: LonLat, w: number, d: number, rotDeg: number): LonLat[] {
  const hw = w / 2;
  const hd = d / 2;
  const pts = [offset(center, -hw, -hd, rotDeg), offset(center, hw, -hd, rotDeg), offset(center, hw, hd, rotDeg), offset(center, -hw, hd, rotDeg)];
  return [...pts, pts[0]];
}

export function ellipse(center: LonLat, rx: number, ry: number, rotDeg: number, n = 28): LonLat[] {
  const pts: LonLat[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    pts.push(offset(center, Math.cos(a) * rx, Math.sin(a) * ry, rotDeg));
  }
  return [...pts, pts[0]];
}
