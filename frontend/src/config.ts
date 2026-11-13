export const CONFIG = {
  /** Backend WebSocket. Empty = run on the built-in hardware simulator. */
  wsUrl: (import.meta.env.VITE_WS_URL as string | undefined) ?? '',
  /** Any MapLibre style. CARTO dark-matter needs no API key. */
  mapStyle:
    (import.meta.env.VITE_MAP_STYLE as string | undefined) || 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  center: [74.8575, 32.7285] as [number, number],
  /** Demo only: responders move this many times faster than real time. */
  timeScale: 5,
};
