import { CONFIG } from '../config';
import type { LonLat, NavProfile, NavResponse } from '../types';

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

export async function fetchNavigation(
  origin: LonLat,
  destination: LonLat,
  profile: NavProfile,
  signal?: AbortSignal,
): Promise<NavResponse> {
  const response = await fetch(`${CONFIG.apiUrl}/api/v1/routes/navigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: { lat: origin[1], lng: origin[0] },
      destination: { lat: destination[1], lng: destination[0] },
      profile,
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
