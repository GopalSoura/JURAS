import { useMemo, useState } from 'react';
import { useStore } from '../store';
import { CONFIG } from '../config';
import { isOpen, sortAlerts } from '../lib/metrics';
import { NAV_PROFILE_META } from '../lib/meta';
import { formatDistance, formatEta } from '../lib/navigation';
import type { NavOrigin, NavProfile } from '../types';
import { Section } from './cards';
import { Icon } from './icons';

const PROFILES = Object.keys(NAV_PROFILE_META) as NavProfile[];

export function NavigationCard() {
  const alerts = useStore((s) => s.alerts);
  const laneNodes = useStore((s) => s.laneNodes);
  const selectedId = useStore((s) => s.selectedAlert);
  const selectAlert = useStore((s) => s.selectAlert);
  const navTargetId = useStore((s) => s.navTargetId);
  const navStatus = useStore((s) => s.navStatus);
  const navError = useStore((s) => s.navError);
  const navErrorCode = useStore((s) => s.navErrorCode);
  const navRoute = useStore((s) => s.navRoute);
  const navProfile = useStore((s) => s.navProfile);
  const navOrigin = useStore((s) => s.navOrigin);
  const setNavOrigin = useStore((s) => s.setNavOrigin);
  const setNavProfile = useStore((s) => s.setNavProfile);
  const navigateToAlert = useStore((s) => s.navigateToAlert);
  const clearNavigation = useStore((s) => s.clearNavigation);

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

  const [custom, setCustom] = useState(false);
  const [lat, setLat] = useState(() => (activeOrigin?.pos[1] ?? CONFIG.center[1]).toFixed(6));
  const [lng, setLng] = useState(() => (activeOrigin?.pos[0] ?? CONFIG.center[0]).toFixed(6));
  const [originError, setOriginError] = useState<string | null>(null);

  const customActive = custom || !activeOrigin || !!navOrigin?.id.startsWith('custom:');
  const selectValue = customActive ? '__custom' : activeOrigin?.id ?? '__custom';

  const chooseOrigin = (value: string) => {
    if (value === '__custom') {
      setCustom(true);
      setOriginError(null);
      const pos = activeOrigin?.pos ?? CONFIG.center;
      setLat(pos[1].toFixed(6));
      setLng(pos[0].toFixed(6));
      return;
    }
    const node = posts.find((n) => `node:${n.id}` === value);
    if (!node) return;
    setCustom(false);
    setOriginError(null);
    setNavOrigin({ id: value, label: `${node.label} (fire post)`, pos: node.pos });
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

  return (
    <Section title="Emergency navigation" hint="OSM road network · A*">
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
          <label className="label mb-1 block" htmlFor="nav-origin">Responder origin</label>
          <select
            id="nav-origin"
            value={selectValue}
            onChange={(e) => chooseOrigin(e.target.value)}
            className="w-full border border-line2 bg-raise px-2 py-1 text-[11.5px] text-ink"
          >
            {posts.map((n) => (
              <option key={n.id} value={`node:${n.id}`}>{n.label}</option>
            ))}
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
            <div className="num font-mono text-[10px] opacity-80">{navErrorCode}</div>
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
              {NAV_PROFILE_META[route.route.properties.profile].label} · {route.route.properties.edge_count} OSM segments ·{' '}
              {route.route.properties.duration_basis ?? 'class-speed estimate'}
            </div>
            {route.warnings.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-[10px] leading-snug text-faint">
                {route.warnings.slice(0, 3).map((w) => (
                  <li key={w}>· {w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Section>
  );
}
