import { nearestOnSegment } from './geo';
import type { LonLat, NavResponse } from '../types';

export function isValidLonLat(value: unknown): value is LonLat {
  if (!Array.isArray(value) || value.length < 2) return false;
  const [lng, lat] = value;
  return Number.isFinite(lng) && Number.isFinite(lat) && lng >= -180 && lng <= 180 && lat >= -90 && lat <= 90;
}

/** Real backend geometry only: reject incomplete or malformed routes rather than drawing a fake line. */
export function navRouteLine(nav: NavResponse | null): LonLat[] {
  const coordinates = nav?.route?.geometry?.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2) return [];
  if (!coordinates.every(isValidLonLat)) return [];
  return coordinates;
}

/** Snap a map click onto the nearest drawn route so the closure really blocks it. */
export function snapToRouteLine(point: LonLat, lines: LonLat[][], maxDistanceM = 60): LonLat {
  let best = point;
  let bestDistance = maxDistanceM;
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const candidate = nearestOnSegment(point, line[i - 1], line[i]);
      if (candidate.distance_m < bestDistance) {
        bestDistance = candidate.distance_m;
        best = candidate.point;
      }
    }
  }
  return best;
}

export function navRouteBounds(nav: NavResponse | null): [[number, number], [number, number]] | null {
  const line = navRouteLine(nav);
  if (line.length < 2) return null;
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const [lng, lat] of line) {
    minLng = Math.min(minLng, lng);
    minLat = Math.min(minLat, lat);
    maxLng = Math.max(maxLng, lng);
    maxLat = Math.max(maxLat, lat);
  }
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

export function formatDistance(metres: number): string {
  if (!Number.isFinite(metres) || metres < 0) return '—';
  if (metres < 1000) return `${Math.round(metres)} m`;
  return `${(metres / 1000).toFixed(metres < 10000 ? 1 : 0)} km`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return 'ETA unavailable';
  if (seconds < 60) return '< 1 min';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}
