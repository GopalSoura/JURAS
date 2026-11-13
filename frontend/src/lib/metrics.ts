import type { Alert } from '../types';
import { SEV_META } from './meta';

export const isOpen = (a: Alert) => a.status !== 'resolved';

export function sortAlerts(list: Alert[]): Alert[] {
  return [...list].sort((a, b) => {
    const ra = isOpen(a) ? 0 : 1;
    const rb = isOpen(b) ? 0 : 1;
    if (ra !== rb) return ra - rb;
    const s = SEV_META[a.severity].rank - SEV_META[b.severity].rank;
    return s !== 0 ? s : b.created_at - a.created_at;
  });
}

export function safetyScore(alerts: Record<string, Alert>): number {
  let penalty = 0;
  for (const a of Object.values(alerts)) if (isOpen(a)) penalty += SEV_META[a.severity].weight * (0.5 + a.confidence / 2);
  return Math.round(Math.max(5, 100 - penalty));
}

/** The alert the map and route panel focus on: the selected one, else the worst open fire/any alert. */
export function focusAlert(alerts: Record<string, Alert>, routes: Record<string, unknown>, selected: string | null): Alert | undefined {
  if (selected && alerts[selected]) return alerts[selected];
  const open = sortAlerts(Object.values(alerts)).filter(isOpen);
  return open.find((a) => routes[a.id]) ?? open[0];
}

const pad = (n: number) => String(n).padStart(2, '0');

/** 12′45″ style elapsed time, like an operations-room incident clock. */
export function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${pad(Math.floor((s % 3600) / 60))}′`;
  return `${pad(Math.floor(s / 60))}′${pad(s % 60)}″`;
}

export function fmtEta(sec: number): string {
  const s = Math.round(sec);
  return `${Math.floor(s / 60)}′${pad(s % 60)}″`;
}

export const fmtDist = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);
