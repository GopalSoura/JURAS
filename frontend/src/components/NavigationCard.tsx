import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../store';
import { CONFIG } from '../config';
import { isOpen, sortAlerts } from '../lib/metrics';
import { NAV_PROFILE_META } from '../lib/meta';
import { formatDistance, formatEta } from '../lib/navigation';
import type { NavDepartment, NavOrigin, NavProfile } from '../types';
import { Section } from './cards';
import { Icon } from './icons';

const PROFILES = Object.keys(NAV_PROFILE_META) as NavProfile[];
// Backend warnings that describe real conditions on the route. Technical
// provenance strings (OSM/demo-grid, A*, geometry validation, snap jargon)
// stay in the API response but are not shown to operators.
const HAZARD_WARNING = /fire hazard/i;
const FLOOD_WARNING = /waterlogged|flood/i;
const DEPARTMENTS: { id: NavDepartment; label: string; icon: 'flame' | 'drop' | 'warn' }[] = [
  { id: 'fire', label: 'Fire', icon: 'flame' },
  { id: 'medical', label: 'Medical', icon: 'drop' },
  { id: 'police', label: 'Police', icon: 'warn' },
];

export function NavigationCard() {
  const alerts = useStore((s) => s.alerts);
  const laneNodes = useStore((s) => s.laneNodes);
  const selectedId = useStore((s) => s.selectedAlert);
  const selectAlert = useStore((s) => s.selectAlert);
  const navTargetId = useStore((s) => s.navTargetId);
  const navStatus = useStore((s) => s.navStatus);
  const navError = useStore((s) => s.navError);
  const navRoute = useStore((s) => s.navRoute);
  const navProfile = useStore((s) => s.navProfile);
  const navOrigin = useStore((s) => s.navOrigin);
  const navDepartment = useStore((s) => s.navDepartment);
  const navOriginMode = useStore((s) => s.navOriginMode);
  const setNavOrigin = useStore((s) => s.setNavOrigin);
  const setNavProfile = useStore((s) => s.setNavProfile);
  const setNavDepartment = useStore((s) => s.setNavDepartment);
  const setNavOriginMode = useStore((s) => s.setNavOriginMode);
  const navigateToAlert = useStore((s) => s.navigateToAlert);
  const clearNavigation = useStore((s) => s.clearNavigation);
  const navClosures = useStore((s) => s.navClosures);
  const navClosureMode = useStore((s) => s.navClosureMode);
  const navClosureError = useStore((s) => s.navClosureError);
  const navClosureBusy = useStore((s) => s.navClosureBusy);
  const loadNavClosures = useStore((s) => s.loadNavClosures);
  const setNavClosureMode = useStore((s) => s.setNavClosureMode);
  const addNavClosure = useStore((s) => s.addNavClosure);
  const removeNavClosure = useStore((s) => s.removeNavClosure);
  const clearNavClosures = useStore((s) => s.clearNavClosures);

  useEffect(() => {
    void loadNavClosures();
  }, [loadNavClosures]);

  const posts = useMemo(() => laneNodes.filter((n) => n.kind === 'fire_post'), [laneNodes]);
  const openFire = useMemo(() => sortAlerts(Object.values(alerts)).filter((a) => a.module === 'fire' && isOpen(a)), [alerts]);
  const selected = selectedId ? alerts[selectedId] : undefined;
  const targetId = navTargetId ?? (selected?.module === 'fire' ? selected.id : null);
  const target = targetId ? alerts[targetId] : undefined;
  const fallbackOrigin = posts[0] ? { id: `node:${posts[0].id}`, label: `${posts[0].label} (fire post)`, pos: posts[0].pos } : null;
  const activeOrigin = navOrigin ?? fallbackOrigin;
  const isCurrent = !!target && navTargetId === target.id;
  const status = isCurrent ? navStatus : 'idle';
  const route = isCurrent ? navRoute : null;
  const routeNotes = useMemo(() => {
    if (!route) return [];
    const notes: string[] = [];
    if (route.warnings.some((w) => HAZARD_WARNING.test(w))) notes.push('Avoids active fire hazard zones.');
    if (route.warnings.some((w) => FLOOD_WARNING.test(w))) notes.push('Avoids waterlogged roads where possible.');
    return notes;
  }, [route]);
  const startGap = route?.route.properties.origin_snap_distance_m ?? 0;
  const endGap = route?.route.properties.destination_snap_distance_m ?? 0;
  const snapGaps = [
    startGap > 5 ? `${Math.round(startGap)} m from the start` : null,
    endGap > 5 ? `${Math.round(endGap)} m from the incident` : null,
  ].filter((gap): gap is string => !!gap);

  const [custom, setCustom] = useState(false);
  const [lat, setLat] = useState(() => (activeOrigin?.pos[1] ?? CONFIG.center[1]).toFixed(6));
  const [lng, setLng] = useState(() => (activeOrigin?.pos[0] ?? CONFIG.center[0]).toFixed(6));
  const [originError, setOriginError] = useState<string | null>(null);
  const [geoBusy, setGeoBusy] = useState(false);

  const nearest = navOriginMode === 'nearest_station';
  const isPostOrigin = !!activeOrigin && posts.some((n) => `node:${n.id}` === activeOrigin.id);
  const customActive = custom || !activeOrigin;
  const selectValue = customActive ? '__custom' : activeOrigin.id;

  const chooseOrigin = (value: string) => {
    if (value === '__custom') {
      setCustom(true);
      setOriginError(null);
      const pos = activeOrigin?.pos ?? CONFIG.center;
      setLat(pos[1].toFixed(6));
      setLng(pos[0].toFixed(6));
      return;
    }
    if (value === activeOrigin?.id) {
      setCustom(false);
      return;
    }
    const node = posts.find((n) => `node:${n.id}` === value);
    if (!node) return;
    setCustom(false);
    setOriginError(null);
    setNavOrigin({ id: value, label: `${node.label} (fire post)`, pos: node.pos });
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setOriginError('Geolocation is not supported by this browser.');
      return;
    }
    setGeoBusy(true);
    setOriginError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        setGeoBusy(false);
        setCustom(false);
        setLat(latitude.toFixed(6));
        setLng(longitude.toFixed(6));
        setNavOrigin({
          id: `geo:${latitude.toFixed(6)},${longitude.toFixed(6)}`,
          label: 'My live location',
          pos: [longitude, latitude],
        });
      },
      (error) => {
        setGeoBusy(false);
        setOriginError(
          error.code === error.PERMISSION_DENIED
            ? 'Location permission denied. Allow location access in the browser.'
            : 'Could not read your live location. Try again or enter coordinates.',
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    );
  };

  const applyCustomOrigin = () => {
    const nextLat = Number(lat);
    const nextLng = Number(lng);
    if (!Number.isFinite(nextLat) || !Number.isFinite(nextLng) || nextLat < -90 || nextLat > 90 || nextLng < -180 || nextLng > 180) {
      setOriginError('Enter valid WGS84 coordinates.');
      return;
    }
    const origin: NavOrigin = {
      id: `custom:${nextLat},${nextLng}`,
      label: `Custom ${nextLat.toFixed(5)}, ${nextLng.toFixed(5)}`,
      pos: [nextLng, nextLat],
    };
    setOriginError(null);
    setCustom(false);
    setNavOrigin(origin);
  };

  const start = () => {
    if (!target) return;
    if (selectedId !== target.id) selectAlert(target.id);
    void navigateToAlert(target.id);
  };

  const blockRouteAhead = () => {
    const coords = route?.route.geometry.coordinates;
    if (!coords || coords.length < 2) return;
    const index = coords.length > 2 ? Math.max(1, Math.floor(coords.length * 0.55)) : 0;
    const point =
      coords.length > 2
        ? coords[Math.min(index, coords.length - 2)]
        : [
            (coords[0][0] + coords[1][0]) / 2,
            (coords[0][1] + coords[1][1]) / 2,
          ];
    void addNavClosure({
      lat: point[1],
      lng: point[0],
      radius_m: 18,
      reason: 'Road blocked on active route',
      source: 'manual',
    });
  };

  return (
    <Section title="Emergency navigation" hint="Fastest road route">
      <div className="space-y-2">
        <div>
          <div className="label mb-1">Destination</div>
          {target ? (
            <div className="border border-line bg-panel px-2 py-1.5">
              <div className="flex items-center gap-1.5 truncate text-[11.5px] font-medium">
                <Icon name="flame" size={12} className="shrink-0 text-crit" />
                <span className="truncate">{target.id} · {target.title}</span>
              </div>
              <div className="num mt-0.5 font-mono text-[10px] text-faint">
                {target.pos[1].toFixed(5)}, {target.pos[0].toFixed(5)}
              </div>
            </div>
          ) : (
            <div className="border border-line bg-panel px-2 py-1.5 text-[11px] text-dim">
              <p>Select a fire incident to navigate.</p>
              {openFire.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {openFire.slice(0, 3).map((a) => (
                    <button key={a.id} className="btn px-1.5 py-0.5 text-[10px]" onClick={() => selectAlert(a.id)}>
                      {a.id}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div>
          <div className="label mb-1">Responder origin</div>
          <div className="mb-1.5 grid grid-cols-2 gap-1">
            <button
              onClick={() => setNavOriginMode('nearest_station')}
              aria-pressed={nearest}
              className="border px-1 py-1 text-[10.5px]"
              style={{
                borderColor: nearest ? 'var(--accent)' : 'var(--line-strong)',
                color: nearest ? 'var(--accent)' : 'var(--dim)',
                background: nearest ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--raise)',
              }}
            >
              Nearest station
            </button>
            <button
              onClick={() => setNavOriginMode('coordinates')}
              aria-pressed={!nearest}
              className="border px-1 py-1 text-[10.5px]"
              style={{
                borderColor: !nearest ? 'var(--accent)' : 'var(--line-strong)',
                color: !nearest ? 'var(--accent)' : 'var(--dim)',
                background: !nearest ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--raise)',
              }}
            >
              Manual origin
            </button>
          </div>

          {nearest ? (
            <>
              <div className="grid grid-cols-3 gap-1">
                {DEPARTMENTS.map((d) => {
                  const on = d.id === navDepartment;
                  return (
                    <button
                      key={d.id}
                      onClick={() => setNavDepartment(d.id)}
                      aria-pressed={on}
                      className="border px-1 py-1 text-[10.5px]"
                      style={{
                        borderColor: on ? 'var(--accent)' : 'var(--line-strong)',
                        color: on ? 'var(--accent)' : 'var(--dim)',
                        background: on ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--raise)',
                      }}
                    >
                      <Icon name={d.icon} size={11} className="mr-1 inline" />
                      {d.label}
                    </button>
                  );
                })}
              </div>
              <div className="mt-1 text-[10px] leading-snug text-faint">
                Nearest {navDepartment} stations to the incident; the fastest reachable one is used automatically.
              </div>
            </>
          ) : (
            <>
              <select
                id="nav-origin"
                value={selectValue}
                onChange={(e) => chooseOrigin(e.target.value)}
                className="w-full border border-line2 bg-raise px-2 py-1 text-[11.5px] text-ink"
              >
                {posts.map((n) => (
                  <option key={n.id} value={`node:${n.id}`}>{n.label}</option>
                ))}
                {activeOrigin && !isPostOrigin && !custom && (
                  <option value={activeOrigin.id}>{activeOrigin.label}</option>
                )}
                <option value="__custom">Custom coordinates…</option>
              </select>
              {customActive && (
                <div className="mt-1.5">
                  <div className="grid grid-cols-2 gap-1.5">
                    <label className="text-[10px] text-dim">
                      Latitude
                      <input
                        value={lat}
                        onChange={(e) => setLat(e.target.value)}
                        inputMode="decimal"
                        className="num mt-0.5 w-full border border-line2 bg-raise px-1.5 py-1 font-mono text-[11px] text-ink"
                      />
                    </label>
                    <label className="text-[10px] text-dim">
                      Longitude
                      <input
                        value={lng}
                        onChange={(e) => setLng(e.target.value)}
                        inputMode="decimal"
                        className="num mt-0.5 w-full border border-line2 bg-raise px-1.5 py-1 font-mono text-[11px] text-ink"
                      />
                    </label>
                  </div>
                  {originError && <div className="mt-1 text-[10.5px] text-crit">{originError}</div>}
                  <button className="btn mt-1.5 px-2 py-0.5 text-[10.5px]" onClick={applyCustomOrigin}>Use coordinates</button>
                </div>
              )}
              {activeOrigin && !customActive && (
                <div className="num mt-1 font-mono text-[10px] text-faint">
                  {activeOrigin.pos[1].toFixed(5)}, {activeOrigin.pos[0].toFixed(5)}
                </div>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <button className="btn px-2 py-0.5 text-[10.5px]" onClick={useMyLocation} disabled={geoBusy}>
                  <Icon name="compass" size={11} className="mr-1 inline" />
                  {geoBusy ? 'Locating…' : 'Use my location'}
                </button>
                {originError && !customActive && <span className="text-[10px] text-crit">{originError}</span>}
              </div>
            </>
          )}
        </div>

        <div>
          <div className="label mb-1">Profile</div>
          <div className="grid grid-cols-3 gap-1">
            {PROFILES.map((p) => {
              const meta = NAV_PROFILE_META[p];
              const on = p === navProfile;
              return (
                <button
                  key={p}
                  onClick={() => setNavProfile(p)}
                  aria-pressed={on}
                  className="border px-1 py-1 text-[10.5px]"
                  style={{
                    borderColor: on ? meta.color : 'var(--line-strong)',
                    color: on ? meta.color : 'var(--dim)',
                    background: on ? `${meta.color}18` : 'var(--raise)',
                  }}
                >
                  {meta.short}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button className="btn border-accent text-accent" disabled={!target || status === 'loading'} onClick={start}>
            <Icon name="route" size={12} className="mr-1 inline" />
            {status === 'loading' ? 'Computing…' : 'Navigate to incident'}
          </button>
          {(status === 'ready' || status === 'error') && (
            <button className="btn px-2 py-0.5 text-[10.5px]" onClick={clearNavigation}>Clear</button>
          )}
        </div>

        {status === 'error' && (
          <div className="border border-crit/40 bg-crit/10 px-2 py-1.5 text-[11px] text-crit">
            {navError}
          </div>
        )}

        {status === 'ready' && route && (
          <div className="border border-line bg-panel px-2 py-2">
            <div className="flex items-end justify-between gap-2">
              <div>
                <div className="num font-mono text-[20px] font-medium leading-none">
                  {formatDistance(route.route.properties.distance_m)}
                </div>
                <div className="mt-0.5 text-[10px] text-dim">route distance</div>
              </div>
              <div className="text-right">
                <div className="num font-mono text-[20px] font-medium leading-none" style={{ color: NAV_PROFILE_META[route.route.properties.profile].color }}>
                  {formatEta(route.route.properties.duration_s)}
                </div>
                <div className="mt-0.5 text-[10px] text-dim">ETA estimate</div>
              </div>
            </div>
            <div className="mt-1.5 text-[10.5px] leading-snug text-dim">
              {NAV_PROFILE_META[route.route.properties.profile].label}
            </div>
            {route.origin_station && (
              <div className="mt-1.5 border-t border-line pt-1.5 text-[10.5px] leading-snug text-dim">
                <span className="text-faint">Station: </span>
                {route.origin_station.name}
                {route.origin_station.address ? ` · ${route.origin_station.address}` : ''}
                <span className="text-faint"> — {formatDistance(route.origin_station.distance_m)} from incident</span>
              </div>
            )}
            {(route.route.properties.closures_considered ?? 0) > 0 && (
              <div className="mt-1.5 border border-accent/40 bg-accent/10 px-1.5 py-1 text-[10.5px] text-accent">
                Re-routed around {route.route.properties.closures_considered} active road closure(s).
              </div>
            )}
            {snapGaps.length > 0 && (
              <div className="mt-1.5 border border-warn/40 bg-warn/10 px-1.5 py-1 text-[10.5px] leading-snug text-warn">
                Route stays on mapped roads. Nearest road is {snapGaps.join('; ')}.
              </div>
            )}
            {routeNotes.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-[10px] leading-snug text-faint">
                {routeNotes.map((note) => (
                  <li key={note}>· {note}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="border-t border-line pt-2">
          <div className="flex items-center justify-between gap-2">
            <div className="label">Road closures / obstacles</div>
            <span className="num font-mono text-[10px] text-faint">{navClosures.length} active</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <button
              className="btn px-2 py-0.5 text-[10.5px]"
              disabled={!route || navClosureBusy}
              onClick={blockRouteAhead}
            >
              {navClosureBusy ? 'Updating…' : 'Block route ahead'}
            </button>
            <button
              className="btn px-2 py-0.5 text-[10.5px]"
              aria-pressed={navClosureMode}
              disabled={navClosureBusy}
              onClick={() => setNavClosureMode(!navClosureMode)}
            >
              {navClosureMode ? 'Click on map…' : 'Pick closure on map'}
            </button>
            {navClosures.length > 0 && (
              <button className="btn px-2 py-0.5 text-[10.5px]" disabled={navClosureBusy} onClick={() => void clearNavClosures()}>
                Clear all
              </button>
            )}
          </div>
          {navClosureMode && (
            <div className="mt-1 text-[10px] leading-snug text-accent">
              Click anywhere on the map to drop a closure. The active route re-plans automatically.
            </div>
          )}
          {navClosureError && <div className="mt-1 text-[10px] text-crit">{navClosureError}</div>}
          {navClosures.length > 0 && (
            <ul className="mt-1.5 space-y-0.5 text-[10px] leading-snug text-dim">
              {navClosures.slice(-3).map((closure) => (
                <li key={closure.id} className="flex items-center justify-between gap-2">
                  <span className="truncate">
                    · {closure.reason}{' '}
                    <span className="text-faint">
                      ({closure.lat.toFixed(4)}, {closure.lng.toFixed(4)}, {Math.round(closure.radius_m)} m)
                    </span>
                  </span>
                  <button
                    className="text-faint hover:text-crit"
                    aria-label={`Remove ${closure.reason}`}
                    onClick={() => void removeNavClosure(closure.id)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Section>
  );
}
