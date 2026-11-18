const configuredWsUrl = (import.meta.env.VITE_WS_URL as string | undefined) ?? '';
const configuredApiUrl = (import.meta.env.VITE_API_URL as string | undefined) ?? '';
const isDev = import.meta.env.DEV;
const pageOrigin =
  typeof window !== 'undefined' && window.location.origin && window.location.origin !== 'null'
    ? window.location.origin
    : '';
const browserHost =
  typeof window !== 'undefined' && window.location.hostname ? window.location.hostname : 'localhost';
const isLoopback = (host: string) => host === 'localhost' || host === '127.0.0.1' || host === '[::1]';

function pointsAtLoopback(value: string): boolean {
  if (!value) return false;
  try {
    return isLoopback(new URL(value, pageOrigin || undefined).hostname);
  } catch {
    return false;
  }
}

/** Keep localhost defaults working when the dashboard is opened from a LAN IP/phone. */
function retargetLoopback(value: string): string {
  if (!value || isLoopback(browserHost)) return value;
  try {
    const url = new URL(value);
    if (!isLoopback(url.hostname)) return value;
    url.hostname = browserHost;
    return url.toString().replace(/\/$/, '');
  } catch {
    return value;
  }
}

// In development the Vite server proxies /api and /ws, so the dashboard works
// on localhost, a LAN IP, or a phone without CORS or a second open port.
const wsUrl =
  isDev && pageOrigin && pointsAtLoopback(configuredWsUrl)
    ? `${pageOrigin.replace(/^http/, 'ws')}/ws`
    : retargetLoopback(configuredWsUrl);
const derivedApi = wsUrl.replace(/^ws/, 'http').replace(/\/ws(?:\/.*)?$/, '');
const useDevApiProxy =
  isDev && !!pageOrigin && (!configuredApiUrl || pointsAtLoopback(configuredApiUrl));

export const CONFIG = {
  /** Backend WebSocket. Empty = run on the built-in hardware simulator. */
  wsUrl,
  /** Backend REST base. Same-origin in development, configurable in builds. */
  apiUrl: useDevApiProxy
    ? pageOrigin
    : retargetLoopback(configuredApiUrl) || derivedApi || `http://${browserHost}:8000`,
  mapboxAccessToken: (import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string | undefined) ?? '',
  mapStyle: 'mapbox://styles/mapbox/streets-v12',
  center: [74.8575, 32.7285] as [number, number],
  /** Keep the map focused on Jammu city. */
  mapBounds: [[74.68, 32.6], [75.05, 32.88]] as [[number, number], [number, number]],
  /** Demo only: responders move this many times faster than real time. */
  timeScale: 5,
};
