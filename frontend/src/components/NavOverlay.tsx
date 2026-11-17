import { useStore } from '../store';
import { NAV_PROFILE_META } from '../lib/meta';
import { formatDistance, formatEta } from '../lib/navigation';
import { Icon } from './icons';

export function NavOverlay() {
  const alerts = useStore((s) => s.alerts);
  const status = useStore((s) => s.navStatus);
  const targetId = useStore((s) => s.navTargetId);
  const route = useStore((s) => s.navRoute);
  const error = useStore((s) => s.navError);
  const clear = useStore((s) => s.clearNavigation);

  if (!targetId && status === 'idle') return null;
  const target = targetId ? alerts[targetId] : undefined;
  const meta = route ? NAV_PROFILE_META[route.route.properties.profile] : null;

  return (
    <div
      className="panel absolute bottom-16 left-1/2 z-10 w-[min(92%,560px)] -translate-x-1/2 px-3 py-2"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        <span style={{ color: meta?.color ?? 'var(--accent)' }}>
          <Icon name="route" size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11.5px] font-medium">
            {target ? `${target.id} · ${target.title}` : 'Navigation'}
          </div>
          {status === 'loading' && <div className="text-[10.5px] text-dim">Computing route…</div>}
          {status === 'error' && (
            <div className="truncate text-[10.5px] text-crit">{error}</div>
          )}
          {status === 'ready' && route && (
            <div className="num flex flex-wrap items-baseline gap-x-2 font-mono text-[11px]">
              <b className="text-[14px]">{formatDistance(route.route.properties.distance_m)}</b>
              <span style={{ color: meta?.color }}>{formatEta(route.route.properties.duration_s)}</span>
              <span className="text-dim">{meta?.label}</span>
            </div>
          )}
        </div>
        <button className="btn shrink-0 px-2 py-0.5 text-[10.5px]" onClick={clear}>Clear</button>
      </div>
    </div>
  );
}
