import { useMemo } from 'react';
import { useStore } from '../store';
import { useNow } from '../hooks';
import { fmtElapsed, isOpen, sortAlerts } from '../lib/metrics';
import { SEV_META } from '../lib/meta';

const STATUS = {
  sim: { text: 'SIMULATED FEED', color: 'var(--amber)' },
  live: { text: 'CONNECTED', color: 'var(--green)' },
  connecting: { text: 'CONNECTING', color: 'var(--accent)' },
  reconnecting: { text: 'RECONNECTING', color: 'var(--amber)' },
  offline: { text: 'DISCONNECTED', color: 'var(--red)' },
} as const;

export function TopBar() {
  const alerts = useStore((s) => s.alerts);
  const status = useStore((s) => s.feedStatus);
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  const simRain = useStore((s) => s.rainHistory[s.rainHistory.length - 1]?.rain);
  const liveRain = useStore((s) => s.liveState['JM-R01']?.values?.rain_mmh);
  const rain = mode === 'realtime' ? liveRain : simRain;
  const rainLabel = typeof rain === 'number' && Number.isFinite(rain) ? rain.toFixed(0) : 'N/A';
  const selectAlert = useStore((s) => s.selectAlert);
  const now = useNow(1000);

  const top = useMemo(() => sortAlerts(Object.values(alerts)).find(isOpen), [alerts]);
  const st = STATUS[status];
  const clock = new Date(now).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false });

  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line bg-panel px-3 sm:px-4">
      <div className="flex min-w-0 items-center gap-2.5">
        <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" className="shrink-0">
          <rect x="1" y="1" width="18" height="18" fill="none" stroke="var(--accent)" strokeWidth="1.2" />
          <path d="M4 14l3.5-4 3 2.5L14 7l2 3" fill="none" stroke="var(--accent)" strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round" />
          <circle cx="14.4" cy="6" r="1.2" fill="var(--green)" />
        </svg>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-[12.5px] font-semibold tracking-[0.08em] text-ink">JURAS · EMERGENCY OPERATIONS CENTER</div>
          <div className="hidden truncate text-[10.5px] text-dim sm:block">Old Jammu pilot zone · urban risk intelligence</div>
        </div>
      </div>

      <div className="ml-2 hidden min-w-0 flex-1 justify-center md:flex">
        {top ? (
          <button
            onClick={() => selectAlert(top.id)}
            className="flex max-w-full items-center gap-2 border bg-panel2 px-2.5 py-1 text-[12px] font-medium"
            style={{ borderColor: SEV_META[top.severity].color + '88', color: SEV_META[top.severity].color }}
            title="Focus this incident"
          >
            <span className="blink inline-block h-1.5 w-1.5 shrink-0" style={{ background: SEV_META[top.severity].color }} />
            <span className="truncate">{top.title}</span>
            <span className="num shrink-0 font-mono text-[11px] font-normal opacity-80">{fmtElapsed(now - top.created_at)}</span>
          </button>
        ) : (
          <span className="text-[11.5px] tracking-wide text-good">No open incidents</span>
        )}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2 text-[11.5px]">
        <div className="flex border border-line" role="group" aria-label="JURAS view mode">
          {(['simulation', 'realtime'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={`px-2 py-1 text-[10px] font-semibold tracking-[0.08em] transition-colors ${
                mode === m ? 'bg-accent text-black' : 'text-dim hover:text-ink'
              }`}
            >
              {m === 'simulation' ? 'SIMULATION' : 'REALTIME'}
            </button>
          ))}
        </div>
        <span className="hidden items-center gap-1.5 border border-line px-2 py-1 text-dim sm:flex">
          Rain <b className="num font-mono text-ink">{rainLabel}</b> mm/h
        </span>
        <span className="flex items-center gap-1.5 border px-2 py-1 text-[10.5px] font-semibold tracking-[0.08em]" style={{ borderColor: st.color + '55', color: st.color }}>
          <span className="inline-block h-1.5 w-1.5" style={{ background: st.color }} />
          {st.text}
        </span>
        <span className="num hidden border border-line px-2 py-1 font-mono text-[12px] text-ink md:block">
          {clock} <span className="text-dim">IST</span>
        </span>
      </div>
    </header>
  );
}
