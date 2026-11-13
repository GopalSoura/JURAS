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
const SRC_COLOR: Record<string, string> = { sensor: '#3db4ff', citizen: '#ffb02e', camera: '#c08bff', cv: '#2fe39a', field: '#8495bf' };
const SRC_LABEL: Record<string, string> = { sensor: 'Sensor', citizen: 'Citizen', camera: 'Camera', cv: 'Photo AI', field: 'Field' };

function Ring({ pct }: { pct: number }) {
  const r = 24;
  const c = 2 * Math.PI * r;
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" role="img" aria-label={`Resolution rate ${pct} percent`}>
      <circle cx="32" cy="32" r={r} fill="none" stroke="#1b2a4d" strokeWidth="6" />
      <circle cx="32" cy="32" r={r} fill="none" stroke="#2fe39a" strokeWidth="6" strokeLinecap="round" strokeDasharray={`${(c * pct) / 100} ${c}`} transform="rotate(-90 32 32)" />
      <text x="32" y="37" textAnchor="middle" fontSize="14" fontFamily="Chakra Petch" fontWeight="600" fill="#dbe6ff">
        {pct}%
      </text>
    </svg>
  );
}

function AlertCard({ a, now }: { a: Alert; now: number }) {
  const selected = useStore((s) => s.selectedAlert === a.id);
  const selectAlert = useStore((s) => s.selectAlert);
  const sev = SEV_META[a.severity];
  const open = isOpen(a);
  const act = (action: 'ack' | 'dispatch' | 'resolve') => feed.send({ cmd: 'alert_action', id: a.id, action });

  return (
    <div
      className={`card overflow-hidden transition-colors ${selected ? 'border-cyan' : ''} ${open ? '' : 'opacity-55'}`}
      style={selected ? { boxShadow: '0 0 0 1px var(--cyan), 0 0 18px rgba(61,180,255,.25)' } : undefined}
    >
      <button onClick={() => selectAlert(selected ? null : a.id)} className="block w-full text-left" aria-expanded={selected}>
        <div className="flex items-stretch">
          <div className="w-[3px] shrink-0" style={{ background: sev.color }} aria-hidden="true" />
          <div className="min-w-0 flex-1 p-2.5">
            <div className="flex items-start gap-2">
              <span className="mt-0.5 shrink-0" style={{ color: sev.color }}>
                <Icon name={MODULE_ICON[a.module]} size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-display text-[13px] font-semibold">{a.title}</span>
                  <span className="num shrink-0 font-mono text-[11px] text-dim">{fmtElapsed(now - a.created_at)}</span>
                </div>
                <div className="truncate text-[12px] text-dim">{a.detail}</div>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="rounded px-1.5 py-0.5 font-display text-[10px] tracking-wider" style={{ color: sev.color, background: `${sev.color}22` }}>
                {sev.label.toUpperCase()}
              </span>
              <span className="rounded bg-[#16213f] px-1.5 py-0.5 text-[10px] text-dim">{MODULE_LABEL[a.module]}</span>
              {[...new Set(a.sources.map((x) => x.kind))].map((k) => (
                <span key={k} className="flex items-center gap-1 rounded bg-[#16213f] px-1.5 py-0.5 text-[10px] text-dim">
                  <i className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: SRC_COLOR[k] }} />
                  {SRC_LABEL[k]}
                </span>
              ))}
              <span className="ml-auto flex items-center gap-1.5">
                <span className="h-1 w-12 overflow-hidden rounded bg-[#16213f]" aria-hidden="true">
                  <span className="block h-full" style={{ width: `${a.confidence * 100}%`, background: sev.color }} />
                </span>
                <span className="num font-mono text-[11px]">{Math.round(a.confidence * 100)}%</span>
              </span>
            </div>
          </div>
        </div>
      </button>

      {selected && (
        <div className="border-t border-line bg-[#0a1226] p-2.5 pl-4 text-[12px]">
          <ul className="mb-2 space-y-1 text-dim">
            {a.sources.map((src, i) => (
              <li key={i} className="flex gap-1.5">
                <i className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: SRC_COLOR[src.kind] }} />
                <span>{src.label}</span>
              </li>
            ))}
          </ul>
          {a.recommendation && <p className="mb-2.5 text-ink">{a.recommendation}</p>}
          <div className="flex flex-wrap gap-1.5">
            {a.status === 'new' && (
              <button className="btn" onClick={() => act('ack')}>
                Acknowledge
              </button>
            )}
            {open && a.status !== 'dispatched' && (
              <button className="btn border-cyan text-cyan" onClick={() => act('dispatch')}>
                {ACT_LABEL[a.module]}
              </button>
            )}
            {open && (
              <button className="btn" onClick={() => act('resolve')}>
                <Icon name="check" size={13} className="mr-1 inline" />
                Resolve
              </button>
            )}
            {a.status === 'dispatched' && <span className="self-center text-[11px] text-good">Units dispatched</span>}
            {!open && <span className="self-center text-[11px] text-dim">Resolved</span>}
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
    <aside className={`panel min-h-0 flex-col border-y-0 border-l-0 ${className}`} aria-label="Live alerts">
      <div className="border-b border-line p-3">
        <div className="mb-2 flex items-center gap-1.5">
          <Icon name="bell" size={15} className="text-cyan" />
          <span className="label">Live alerts</span>
        </div>
        <div className="flex items-center gap-4">
          <div>
            <div className="num font-display text-[40px] font-semibold leading-none" style={{ color: openCount ? 'var(--red)' : 'var(--green)' }}>
              {openCount}
            </div>
            <div className="mt-1 text-[11px] text-dim">open now</div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Ring pct={rate} />
            <div className="text-[11px] leading-tight text-dim">
              Resolution
              <br />
              rate today
            </div>
          </div>
        </div>
        <div className="mt-3 flex h-2 overflow-hidden rounded bg-[#16213f]" role="img" aria-label="Open alerts by severity">
          {(Object.keys(bySev) as Severity[]).map((k) =>
            bySev[k] ? <span key={k} style={{ flex: bySev[k], background: SEV_META[k].color }} /> : null,
          )}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-dim">
          {(Object.keys(bySev) as Severity[]).map((k) => (
            <span key={k} className="flex items-center gap-1">
              <i className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: SEV_META[k].color }} />
              {SEV_META[k].label} <b className="num text-ink">{bySev[k]}</b>
            </span>
          ))}
        </div>
      </div>

      <div className="scroll min-h-0 flex-1 space-y-2 p-2.5">
        {list.length === 0 && <p className="p-3 text-center text-[12px] text-dim">No alerts for this view.</p>}
        {list.map((a) => (
          <AlertCard key={a.id} a={a} now={now} />
        ))}
      </div>
    </aside>
  );
}
