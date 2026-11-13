import { useMemo } from 'react';
import { useStore } from '../store';
import { useNow } from '../hooks';
import { fmtElapsed, isOpen, sortAlerts } from '../lib/metrics';
import { SEV_META } from '../lib/meta';

const STATUS = {
  sim: { text: 'SIMULATED FEED', color: 'var(--amber)' },
  live: { text: 'LIVE BACKEND', color: 'var(--green)' },
  connecting: { text: 'CONNECTING', color: 'var(--cyan)' },
  offline: { text: 'BACKEND OFFLINE', color: 'var(--red)' },
} as const;

export function TopBar() {
  const alerts = useStore((s) => s.alerts);
  const status = useStore((s) => s.feedStatus);
  const rain = useStore((s) => s.rainHistory[s.rainHistory.length - 1]?.rain ?? 0);
  const selectAlert = useStore((s) => s.selectAlert);
  const now = useNow(1000);

  const top = useMemo(() => sortAlerts(Object.values(alerts)).find(isOpen), [alerts]);
  const st = STATUS[status];
  const clock = new Date(now).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false });

  return (
    <header className="panel flex h-12 shrink-0 items-center gap-3 border-x-0 border-t-0 px-3 sm:px-4">
      <div className="flex min-w-0 items-center gap-2.5">
        <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true" className="shrink-0">
          <rect x="1" y="1" width="24" height="24" rx="5" fill="#0f2b52" stroke="#3db4ff" strokeWidth="1.2" />
          <path d="M5 17l4-5 4 3 4-7 4 5" fill="none" stroke="#3db4ff" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
          <circle cx="17" cy="8" r="1.8" fill="#2fe39a" />
        </svg>
        <div className="min-w-0 leading-tight">
          <div className="truncate font-display text-[14px] font-semibold tracking-wide">OLD JAMMU · RISK INTELLIGENCE</div>
          <div className="hidden truncate text-[11px] text-dim sm:block">Urban digital twin · pilot zone · Detect, Understand, Prioritize, Act, Learn</div>
        </div>
      </div>

      <div className="ml-2 hidden min-w-0 flex-1 justify-center md:flex">
        {top ? (
          <button
            onClick={() => selectAlert(top.id)}
            className="flex max-w-full items-center gap-2 rounded-md border px-3 py-1 font-display text-[13px] font-semibold"
            style={{ borderColor: SEV_META[top.severity].color, color: SEV_META[top.severity].color, background: `${SEV_META[top.severity].color}1f` }}
            title="Focus this incident"
          >
            <span className="blink inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: SEV_META[top.severity].color }} />
            <span className="truncate">{top.title}</span>
            <span className="num shrink-0 font-mono text-[12px] font-normal">{fmtElapsed(now - top.created_at)}</span>
          </button>
        ) : (
          <span className="text-[12px] text-good">No open incidents</span>
        )}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-3 text-[12px]">
        <span className="hidden items-center gap-1.5 rounded-md border border-line px-2 py-1 text-dim sm:flex">
          Rain <b className="num font-mono text-ink">{rain.toFixed(0)}</b> mm/h
        </span>
        <span className="flex items-center gap-1.5 rounded-md border border-line px-2 py-1 font-display text-[11px] tracking-wider" style={{ color: st.color }}>
          <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: st.color }} />
          {st.text}
        </span>
        <span className="num hidden font-mono text-[13px] text-ink md:block">
          {clock} <span className="text-dim">IST</span>
        </span>
      </div>
    </header>
  );
}
