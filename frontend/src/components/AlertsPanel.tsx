import { useMemo } from 'react';
import { useStore } from '../store';
import { useNow } from '../hooks';
import { feed } from '../lib/feed';
import { fmtElapsed, isOpen, sortAlerts } from '../lib/metrics';
import { MODULE_LABEL, NAV_FILTER, SEV_META } from '../lib/meta';
import type { Alert, AlertModule, Severity } from '../types';
import { Icon, type IconName } from './icons';

const MODULE_ICON: Record<AlertModule, IconName> = { fire: 'flame', structure: 'building', flood: 'drop', map: 'route' };
const ACT_LABEL: Record<AlertModule, string> = { fire: 'Dispatch units', structure: 'Assign engineer', flood: 'Send crew', map: 'Send to field' };
const SRC_COLOR: Record<string, string> = { sensor: 'var(--accent)', citizen: 'var(--amber)', camera: '#b08be8', cv: 'var(--green)', field: 'var(--dim)' };
const SRC_LABEL: Record<string, string> = { sensor: 'Sensor', citizen: 'Citizen', camera: 'Camera', cv: 'Photo AI', field: 'Field' };

function AlertRow({ a, now }: { a: Alert; now: number }) {
  const selected = useStore((s) => s.selectedAlert === a.id);
  const selectAlert = useStore((s) => s.selectAlert);
  const navigateToAlert = useStore((s) => s.navigateToAlert);
  const navActive = useStore((s) => s.navTargetId === a.id);
  const sev = SEV_META[a.severity];
  const open = isOpen(a);
  const act = (action: 'ack' | 'dispatch' | 'resolve') => feed.send({ cmd: 'alert_action', id: a.id, action });

  return (
    <div
      className={`card overflow-hidden transition-colors ${selected ? 'border-accent' : ''} ${open ? '' : 'opacity-50'}`}
    >
      <button onClick={() => selectAlert(selected ? null : a.id)} className="block w-full text-left" aria-expanded={selected}>
        <div className="flex items-stretch">
          <div className="w-[2px] shrink-0" style={{ background: sev.color }} aria-hidden="true" />
          <div className="min-w-0 flex-1 px-2.5 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="shrink-0" style={{ color: sev.color }}>
                  <Icon name={MODULE_ICON[a.module]} size={13} />
                </span>
                <span className="truncate text-[12px] font-semibold">{a.title}</span>
              </span>
              <span className="num shrink-0 font-mono text-[10.5px] text-dim">{fmtElapsed(now - a.created_at)}</span>
            </div>
            <div className="mt-0.5 truncate text-[11.5px] text-dim">{a.detail}</div>
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="px-1 py-px text-[9.5px] font-semibold tracking-[0.06em]" style={{ color: sev.color, background: `${sev.color}1c` }}>
                {sev.label.toUpperCase()}
              </span>
              <span className="px-1 py-px text-[9.5px] text-dim" style={{ background: 'var(--raise)' }}>
                {MODULE_LABEL[a.module]}
              </span>
              {[...new Set(a.sources.map((x) => x.kind))].slice(0, 3).map((k) => (
                <span key={k} className="flex items-center gap-1 px-1 py-px text-[9.5px] text-dim" style={{ background: 'var(--raise)' }}>
                  <i className="inline-block h-1 w-1" style={{ background: SRC_COLOR[k] }} />
                  {SRC_LABEL[k]}
                </span>
              ))}
              <span className="ml-auto flex items-center gap-1.5">
                <span className="h-[3px] w-10" style={{ background: 'var(--raise)' }} aria-hidden="true">
                  <span className="block h-full" style={{ width: `${a.confidence * 100}%`, background: sev.color }} />
                </span>
                <span className="num font-mono text-[10.5px] text-dim">{Math.round(a.confidence * 100)}%</span>
              </span>
            </div>
          </div>
        </div>
      </button>

      {selected && (
        <div className="border-t border-line bg-panel px-2.5 py-2 pl-3.5 text-[11.5px]">
          <ul className="mb-2 space-y-0.5 text-dim">
            {a.sources.map((src, i) => (
              <li key={i} className="flex gap-1.5">
                <i className="mt-1.5 inline-block h-1 w-1 shrink-0" style={{ background: SRC_COLOR[src.kind] }} />
                <span>{src.label}</span>
              </li>
            ))}
          </ul>
          {a.recommendation && <p className="mb-2 text-ink">{a.recommendation}</p>}
          <div className="flex flex-wrap gap-1.5">
            {a.status === 'new' && (
              <button className="btn" onClick={() => act('ack')}>
                Acknowledge
              </button>
            )}
            {open && a.status !== 'dispatched' && (
              <button className="btn border-accent text-accent" onClick={() => act('dispatch')}>
                {ACT_LABEL[a.module]}
              </button>
            )}
            {open && a.module === 'fire' && (
              <button
                className="btn border-accent text-accent"
                onClick={() => {
                  selectAlert(a.id);
                  void navigateToAlert(a.id);
                }}
              >
                <Icon name="route" size={12} className="mr-1 inline" />
                {navActive ? 'Recalculate route' : 'Navigate'}
              </button>
            )}
            {open && (
              <button className="btn" onClick={() => act('resolve')}>
                <Icon name="check" size={12} className="mr-1 inline" />
                Resolve
              </button>
            )}
            {a.status === 'dispatched' && <span className="self-center text-[10.5px] text-good">Units dispatched</span>}
            {!open && <span className="self-center text-[10.5px] text-dim">Resolved</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export function AlertsPanel({ className = '' }: { className?: string }) {
  const alerts = useStore((s) => s.alerts);
  const module = useStore((s) => s.module);
  const now = useNow(1000);

  const { list, openCount, rate, bySev } = useMemo(() => {
    const all = Object.values(alerts);
    const filter = NAV_FILTER[module];
    const open = all.filter(isOpen);
    const bySev: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
    open.forEach((a) => bySev[a.severity]++);
    return {
      list: sortAlerts(all).filter((a) => !filter || filter.includes(a.module)),
      openCount: open.length,
      rate: all.length ? Math.round(((all.length - open.length) / all.length) * 100) : 100,
      bySev,
    };
  }, [alerts, module]);

  return (
    <aside className={`panel flex min-h-0 flex-col border-y-0 border-l-0 ${className}`} aria-label="Live alerts">
      <div className="border-b border-line px-3 py-2.5">
        <div className="mb-2 flex items-center justify-between">
          <span className="label">Incident console</span>
          <span className="num font-mono text-[10.5px] text-dim">{rate}% resolved today</span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="num font-mono text-[20px] font-semibold leading-none" style={{ color: openCount ? 'var(--red)' : 'var(--green)' }}>
            {openCount}
          </span>
          <span className="text-[11px] text-dim">open now</span>
          {(Object.keys(bySev) as Severity[]).map((k) =>
            bySev[k] ? (
              <span key={k} className="ml-auto flex items-center gap-1 text-[10.5px] text-dim">
                <i className="inline-block h-1.5 w-1.5" style={{ background: SEV_META[k].color }} />
                <b className="num font-mono text-ink">{bySev[k]}</b>
              </span>
            ) : null,
          )}
        </div>
        <div className="mt-2 flex h-[3px] w-full" style={{ background: 'var(--raise)' }} role="img" aria-label="Open alerts by severity">
          {(Object.keys(bySev) as Severity[]).map((k) =>
            bySev[k] ? <span key={k} style={{ flex: bySev[k], background: SEV_META[k].color }} /> : null,
          )}
        </div>
      </div>

      <div className="scroll min-h-0 flex-1 space-y-1.5 p-2">
        {list.length === 0 && <p className="p-3 text-center text-[11.5px] text-dim">No alerts for this view.</p>}
        {list.map((a) => (
          <AlertRow key={a.id} a={a} now={now} />
        ))}
      </div>
    </aside>
  );
}
