import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { useStore, type Layers, type StoreState } from '../store';
import { CONFIG } from '../config';
import { buildLayers, tooltipFor } from '../lib/layers';
import { focusAlert, fmtEta, isOpen } from '../lib/metrics';
import { pointAlong } from '../lib/geo';
import { PROFILE_META } from '../lib/meta';
import { navRouteBounds, navRouteLine, snapToRouteLine } from '../lib/navigation';
import type { LonLat } from '../types';
import { FLAME_SVG, Icon } from './icons';
import { NavOverlay } from './NavOverlay';

const HOME = { center: CONFIG.center, zoom: 13.2, pitch: 0, bearing: 0 };

interface Want { pos: LonLat; cls: string; html: string; anchor: 'bottom' | 'center' }

function syncMarkers(map: mapboxgl.Map, markers: Map<string, mapboxgl.Marker>, s: StoreState) {
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
    if (!r.feasible || r.path.length < 2) continue;
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
      mk = new mapboxgl.Marker({ element: document.createElement('div'), anchor: w.anchor }).setLngLat(w.pos).addTo(map);
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
  lanes: 'Lane network',
  sensors: 'Sensor nodes',
  flood: 'Flood zones',
};

export function MapView() {
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [menu, setMenu] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const layers = useStore((s) => s.layers);
  const toggleLayer = useStore((s) => s.toggleLayer);

  useEffect(() => {
    if (!el.current) return;
    if (!CONFIG.mapboxAccessToken) {
      setMapError('Add VITE_MAPBOX_ACCESS_TOKEN to frontend/.env.local, then restart the frontend.');
      return;
    }

    mapboxgl.accessToken = CONFIG.mapboxAccessToken;
    const map = new mapboxgl.Map({
      container: el.current,
      style: CONFIG.mapStyle,
      center: HOME.center,
      zoom: HOME.zoom,
      pitch: HOME.pitch,
      bearing: HOME.bearing,
      minZoom: 11,
      maxPitch: 0,
      maxBounds: CONFIG.mapBounds,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new mapboxgl.AttributionControl({ compact: true }));
    const geolocate = new mapboxgl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
      showUserLocation: true,
      showAccuracyCircle: true,
    });
    map.addControl(geolocate, 'top-right');
    geolocate.on('geolocate', (event) => {
      const coords = (event as unknown as GeolocationPosition).coords;
      useStore.getState().setNavOrigin({
        id: `geo:${coords.latitude.toFixed(6)},${coords.longitude.toFixed(6)}`,
        label: 'My live location',
        pos: [coords.longitude, coords.latitude],
      });
    });

    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      getTooltip: (info) => tooltipFor(info, useStore.getState()),
      onClick: (info) => {
        if (useStore.getState().navClosureMode) return;
        if (info.layer?.id === 'buildings' && info.object) useStore.getState().selectBuilding((info.object as { id: string }).id);
      },
    });
    map.addControl(overlay as unknown as mapboxgl.IControl);
    map.on('click', (event) => {
      const state = useStore.getState();
      if (!state.navClosureMode) return;
      const clicked: LonLat = [event.lngLat.lng, event.lngLat.lat];
      const drawnLines = [
        navRouteLine(state.navRoute),
        ...Object.values(state.routes).flatMap((rs) =>
          rs.filter((r) => r.feasible).map((r) => r.path),
        ),
      ];
      const pos = snapToRouteLine(clicked, drawnLines);
      void state.addNavClosure({
        lat: pos[1],
        lng: pos[0],
        radius_m: 18,
        reason: 'Road closed at map click',
        source: 'manual',
      });
    });
    map.on('load', () => {
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type === 'fill-extrusion') map.setLayoutProperty(layer.id, 'visibility', 'none');
      }
    });

    const markers = new Map<string, mapboxgl.Marker>();
    const t0 = performance.now();
    let raf = 0;
    const loop = () => {
      overlay.setProps({ layers: buildLayers(useStore.getState(), performance.now() - t0, Date.now(), map.getZoom()) });
      raf = requestAnimationFrame(loop);
    };
    loop();

    const unsub = useStore.subscribe((s, prev) => {
      syncMarkers(map, markers, s);
      if (s.navRoute && s.navRoute !== prev.navRoute) {
        const bounds = navRouteBounds(s.navRoute);
        if (bounds) {
          map.fitBounds(bounds, {
            padding: { top: 90, bottom: 130, left: 60, right: 60 },
            pitch: 0,
            bearing: 0,
            duration: 1200,
            maxZoom: 17.6,
            essential: true,
          });
        }
      } else if (s.selectedAlert && s.selectedAlert !== prev.selectedAlert) {
        const a = s.alerts[s.selectedAlert];
        if (a) map.flyTo({ center: a.pos, zoom: 16.5, pitch: 0, duration: 1400, essential: true });
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

  const ctl = 'btn grid h-8 w-8 place-items-center p-0';
  return (
    <div className="relative h-full w-full">
      <div ref={el} className="absolute inset-0 h-full w-full" />
      <NavOverlay />

      {mapError && (
        <div role="alert" className="panel absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 px-4 py-3 text-center text-sm">
          Mapbox setup required
          <div className="mt-1 text-xs text-dim">{mapError}</div>
        </div>
      )}

      <div className="absolute right-3 top-3 flex flex-col gap-1">
        <button className={ctl} onClick={() => mapRef.current?.zoomIn()} aria-label="Zoom in">
          <Icon name="plus" size={14} />
        </button>
        <button className={ctl} onClick={() => mapRef.current?.zoomOut()} aria-label="Zoom out">
          <Icon name="minus" size={14} />
        </button>
        <button className={ctl} onClick={() => mapRef.current?.easeTo({ ...HOME, duration: 900 })} aria-label="Reset view">
          <Icon name="compass" size={14} />
        </button>
        <div className="relative">
          <button className={ctl} onClick={() => setMenu(!menu)} aria-label="Map layers" aria-expanded={menu}>
            <Icon name="layers" size={14} />
          </button>
          {menu && (
            <div className="panel absolute right-10 top-0 w-48 p-1.5 text-[11.5px]">
              {(Object.keys(LAYER_LABEL) as (keyof Layers)[]).map((k) => (
                <label key={k} className="flex cursor-pointer items-center gap-2 px-1.5 py-1 hover:bg-raise">
                  <input type="checkbox" checked={layers[k]} onChange={() => toggleLayer(k)} className="accent-[#4d9fff]" />
                  {LAYER_LABEL[k]}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="panel pointer-events-none absolute bottom-3 left-3 hidden px-2.5 py-2 text-[10.5px] text-dim lg:block">
        <div className="label mb-1">Legend</div>
        {(['fire_truck', 'medical', 'evacuation'] as const).map((p) => (
          <div key={p} className="flex items-center gap-2">
            <i className="inline-block h-[2px] w-5" style={{ background: PROFILE_META[p].color }} />
            {PROFILE_META[p].label}
          </div>
        ))}
        <div className="mt-1.5 flex items-center gap-2">
          <i className="inline-block h-2 w-2 bg-[#e35d6a]/60" /> Fire danger zone
        </div>
        <div className="mt-0.5 flex items-center gap-2">
          <i className="inline-block h-2 w-2 bg-[#4d9fff]/60" /> Flooded lane
        </div>
      </div>
    </div>
  );
}
