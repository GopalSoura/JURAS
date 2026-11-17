import { CONFIG } from '../config';
import type { LonLat, NavClosure, NavDepartment, NavOriginMode, NavProfile, NavResponse } from '../types';

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

export interface NavigationRequest {
  origin?: LonLat;
  destination: LonLat;
  profile: NavProfile;
  originMode?: NavOriginMode;
  department?: NavDepartment;
}

export async function fetchNavigation(
  request: NavigationRequest,
  signal?: AbortSignal,
): Promise<NavResponse> {
  const { origin, destination, profile, originMode = 'coordinates', department } = request;
  const response = await fetch(`${CONFIG.apiUrl}/api/v1/routes/navigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...(origin ? { origin: { lat: origin[1], lng: origin[0] } } : {}),
      destination: { lat: destination[1], lng: destination[0] },
      profile,
      origin_mode: originMode,
      ...(department ? { department } : {}),
    }),
    signal,
  });
  const body = (await response.json().catch(() => null)) as
    | (NavResponse & { error?: { code?: string; message?: string } })
    | { error?: { code?: string; message?: string } }
    | null;
  if (!response.ok) {
    const err = body && 'error' in body ? body.error : undefined;
    throw new ApiError(err?.code ?? `HTTP_${response.status}`, err?.message ?? 'Navigation request failed', response.status);
  }
  return body as NavResponse;
}

export interface ClosureInput {
  lat: number;
  lng: number;
  radius_m?: number;
  reason?: string;
  source?: 'manual' | 'simulated';
}

async function closureRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${CONFIG.apiUrl}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body = (await response.json().catch(() => null)) as
    | (T & { error?: { code?: string; message?: string } })
    | { error?: { code?: string; message?: string } }
    | null;
  if (!response.ok) {
    const err = body && 'error' in body ? body.error : undefined;
    throw new ApiError(err?.code ?? `HTTP_${response.status}`, err?.message ?? 'Road closure request failed', response.status);
  }
  return body as T;
}

export async function fetchClosures(): Promise<NavClosure[]> {
  const body = await closureRequest<{ closures: NavClosure[] }>('/api/v1/routes/closures');
  return body.closures;
}

export async function createClosure(input: ClosureInput): Promise<NavClosure> {
  return closureRequest<NavClosure>('/api/v1/routes/closures', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function deleteClosure(id: string): Promise<void> {
  await closureRequest(`/api/v1/routes/closures/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function clearClosures(): Promise<void> {
  await closureRequest('/api/v1/routes/closures', { method: 'DELETE' });
}
