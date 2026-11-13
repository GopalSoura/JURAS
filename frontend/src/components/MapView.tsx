import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { useStore, type Layers, type StoreState } from '../store';
import { CONFIG } from '../config';
import { buildLayers, tooltipFor } from '../lib/layers';
import { focusAlert, fmtEta, isOpen } from '../lib/metrics';
import { pointAlong } from '../lib/geo';
import { PROFILE_META } from '../lib/meta';
import type { LonLat } from '../types';
import { FLAME_SVG, Icon } from './icons';

const HOME = { center: CONFIG.center, zoom: 16.6, pitch: 58, bearing: -24 };

/** Extrude the OpenStreetMap building footprints that the basemap's vector tiles already carry. */
function add3dBuildings(map: maplibregl.Map) {
  const style = map.getStyle();
  if (!style || map.getLayer('osm-3d')) return;
  const source = Object.entries(style.sources).find(([, s]) => s.type === 'vector')?.[0];
  if (!source) return;
  const firstSymbol = style.layers.find((l) => l.type === 'symbol')?.id;
  map.addLayer(
    {
      id: 'osm-3d',
      type: 'fill-extrusion',
      source,
      'source-layer': 'building',
      minzoom: 14,
      paint: {
        'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, '#16213f', 30, '#27407a', 80, '#3b5a9c'],
        'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 8],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
        'fill-extrusion-opacity': 0.78,
      },
    } as maplibregl.FillExtrusionLayerSpecification,
    firstSymbol,
  );
}

interface Want { pos: LonLat; cls: string; html: string; anchor: 'bottom' | 'center' }

function syncMarkers(map: maplibregl.Map, markers: Map<string, maplibregl.Marker>, s: StoreState) {
  const want = new Map<string, Want>();
  for (const a of Object.values(s.alerts)) {
    if (a.module !== 'fire' || !isOpen(a)) continue;
    want.set(`inc-${a.id}`, {
      pos: a.pos,
      cls: a.severity === 'critical' ? 'mk-incident' : 'mk-incident sev-high',
      html: `${FLAME_SVG}<span>${a.severity === 'critical' ? 'Fire' : 'Possible fire'} ${Math.round(a.confidence * 100)}%</span>`,
      anchor: 'bottom',
    });
  }
  const focus = focusAlert(s.alerts, s.routes, s.selectedAlert);
  const along: Record<string, number> = { fire_truck: 0.4, medical: 0.6, evacuation: 0.5 };
  for (const r of focus ? s.routes[focus.id] ?? [] : []) {
    const m = PROFILE_META[r.profile];
    want.set(`eta-${r.profile}`, {
      pos: pointAlong(r.path, along[r.profile]),
      cls: 'mk-chip',
      html: `<i style="background:${m.color}"></i><span>${m.label} ${fmtEta(r.eta_s)}</span>`,
      anchor: 'center',
    });
  }

  for (const [k, mk] of markers) {
    if (!want.has(k)) {
      mk.remove();
      markers.delete(k);
    }
  }
  for (const [k, w] of want) {
    let mk = markers.get(k);
    if (!mk) {
      mk = new maplibregl.Marker({ element: document.createElement('div'), anchor: w.anchor }).setLngLat(w.pos).addTo(map);
      markers.set(k, mk);
    }
    const el = mk.getElement();
    const inner = `<div class="${w.cls}">${w.html}</div>`;
    if (el.dataset.h !== inner) {
      el.innerHTML = inner;
      el.dataset.h = inner;
    }
    mk.setLngLat(w.pos);
  }
}

const LAYER_LABEL: Record<keyof Layers, string> = {
  osm: 'OSM buildings (3D)',
  lanes: 'Lane network',
  sensors: 'Sensor nodes',
  flood: 'Flood zones',
};

export function MapView() {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [flat, setFlat] = useState(false);
  const [menu, setMenu] = useState(false);
  const layers = useStore((s) => s.layers);
  const toggleLayer = useStore((s) => s.toggleLayer);

  useEffect(() => {
    if (!el.current) return;
    const map = new maplibregl.Map({
      container: el.current,
      style: CONFIG.mapStyle,
      center: HOME.center,
      zoom: HOME.zoom,
      pitch: HOME.pitch,
      bearing: HOME.bearing,
      maxPitch: 80,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      getTooltip: (info) => tooltipFor(info, useStore.getState()),
      onClick: (info) => {
        if (info.layer?.id === 'buildings' && info.object) useStore.getState().selectBuilding((info.object as { id: string }).id);
      },
    });
    map.addControl(overlay as unknown as maplibregl.IControl);
    map.on('load', () => add3dBuildings(map));

    const markers = new Map<string, maplibregl.Marker>();
    const t0 = performance.now();
    let raf = 0;
    const loop = () => {
      overlay.setProps({ layers: buildLayers(useStore.getState(), performance.now() - t0, Date.now(), map.getZoom()) });
      raf = requestAnimationFrame(loop);
    };
    loop();

    const unsub = useStore.subscribe((s, prev) => {
      syncMarkers(map, markers, s);
      if (s.layers.osm !== prev.layers.osm && map.getLayer('osm-3d')) {
        map.setLayoutProperty('osm-3d', 'visibility', s.layers.osm ? 'visible' : 'none');
      }
      if (s.selectedAlert && s.selectedAlert !== prev.selectedAlert) {
        const a = s.alerts[s.selectedAlert];
        if (a) map.flyTo({ center: a.pos, zoom: 17.4, pitch: Math.max(map.getPitch(), 50), duration: 1400, essential: true });
      } else if (s.selectedBuilding && s.selectedBuilding !== prev.selectedBuilding) {
        const b = s.buildings[s.selectedBuilding];
        if (b) map.easeTo({ center: b.center, zoom: Math.max(map.getZoom(), 17.2), duration: 900 });
      }
    });
    syncMarkers(map, markers, useStore.getState());

    return () => {
      unsub();
      cancelAnimationFrame(raf);
      markers.forEach((m) => m.remove());
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const toggle3d = () => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ pitch: flat ? HOME.pitch : 0, bearing: flat ? HOME.bearing : 0, duration: 700 });
    setFlat(!flat);
  };

  const ctl = 'btn grid h-9 w-9 place-items-center p-0';
  return (
    <div className="relative h-full w-full">
      <div ref={el} className="absolute inset-0 h-full w-full" />

      <div className="absolute right-3 top-3 flex flex-col gap-1.5">
        <button className={`${ctl} font-display text-[11px] font-semibold`} onClick={toggle3d} aria-label={flat ? 'Switch to 3D view' : 'Switch to 2D view'} aria-pressed={!flat}>
          {flat ? '2D' : '3D'}
        </button>
        <button className={ctl} onClick={() => mapRef.current?.zoomIn()} aria-label="Zoom in">
          <Icon name="plus" size={16} />
        </button>
        <button className={ctl} onClick={() => mapRef.current?.zoomOut()} aria-label="Zoom out">
          <Icon name="minus" size={16} />
        </button>
        <button className={ctl} onClick={() => mapRef.current?.easeTo({ ...HOME, duration: 900 })} aria-label="Reset view">
          <Icon name="compass" size={16} />
        </button>
        <div className="relative">
          <button className={ctl} onClick={() => setMenu(!menu)} aria-label="Map layers" aria-expanded={menu}>
            <Icon name="layers" size={16} />
          </button>
          {menu && (
            <div className="panel absolute right-11 top-0 w-48 rounded-md p-2 text-[12px]">
              {(Object.keys(LAYER_LABEL) as (keyof Layers)[]).map((k) => (
                <label key={k} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 hover:bg-[#16213f]">
                  <input type="checkbox" checked={layers[k]} onChange={() => toggleLayer(k)} className="accent-[#3db4ff]" />
                  {LAYER_LABEL[k]}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="panel pointer-events-none absolute bottom-3 left-3 hidden rounded-md px-2.5 py-2 text-[11px] text-dim lg:block">
        <div className="label mb-1">Legend</div>
        {(['fire_truck', 'medical', 'evacuation'] as const).map((p) => (
          <div key={p} className="flex items-center gap-2">
            <i className="inline-block h-[3px] w-5 rounded" style={{ background: PROFILE_META[p].color }} />
            {PROFILE_META[p].label}
          </div>
        ))}
        <div className="mt-1 flex items-center gap-2">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#ff4d5e]/60" /> Fire danger zone
        </div>
        <div className="flex items-center gap-2">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#3290ff]/60" /> Flooded lane
        </div>
      </div>
    </div>
  );
}
