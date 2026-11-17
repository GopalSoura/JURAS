const wsUrl = (import.meta.env.VITE_WS_URL as string | undefined) ?? '';
const derivedApi = wsUrl.replace(/^ws/, 'http').replace(/\/ws(?:\/.*)?$/, '');

export const CONFIG = {
  /** Backend WebSocket. Empty = run on the built-in hardware simulator. */
  wsUrl,
  /** Backend REST base. Derived from VITE_WS_URL unless VITE_API_URL is set. */
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) || derivedApi || 'http://localhost:8000',
  mapboxAccessToken: (import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string | undefined) ?? '',
  mapStyle: 'mapbox://styles/mapbox/streets-v12',
  center: [74.8575, 32.7285] as [number, number],
  /** Keep the map focused on Jammu city. */
  mapBounds: [[74.68, 32.6], [75.05, 32.88]] as [[number, number], [number, number]],
  /** Demo only: responders move this many times faster than real time. */
  timeScale: 5,
};
