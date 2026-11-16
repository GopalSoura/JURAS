const wsUrl = (import.meta.env.VITE_WS_URL as string | undefined) ?? '';
const derivedApi = wsUrl.replace(/^ws/, 'http').replace(/\/ws(?:\/.*)?$/, '');

export const CONFIG = {
  /** Backend WebSocket. Empty = run on the built-in hardware simulator. */
  wsUrl,
  /** Backend REST base. Derived from VITE_WS_URL unless VITE_API_URL is set. */
  apiUrl: (import.meta.env.VITE_API_URL as string | undefined) || derivedApi || 'http://localhost:8000',
  /** Any MapLibre style. CARTO dark-matter needs no API key. */
  mapStyle:
    (import.meta.env.VITE_MAP_STYLE as string | undefined) || 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  center: [74.8575, 32.7285] as [number, number],
  /** Demo only: responders move this many times faster than real time. */
  timeScale: 5,
};
