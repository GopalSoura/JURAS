import { useMemo, type ReactNode } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useStore } from '../store';
import { useNow } from '../hooks';
import { CONFIG } from '../config';
import { focusAlert, fmtDist, fmtEta, isOpen, safetyScore } from '../lib/metrics';
import { PROFILE_META, SEV_META } from '../lib/meta';
import { Chart, CHART } from './Chart';

export function Section({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="card p-3">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="label">{title}</h3>
        {hint && <span className="truncate text-[11px] text-dim">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

const timeLabel = (ts: number) => new Date(ts).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false });

/* ---------------- KPI tiles ---------------- */
export function Kpis() {
  const alerts = useStore((s) => s.alerts);
  const buildings = useStore((s) => s.buildings);
  const sensors = useStore((s) => s.sensors);
  const nodeState = useStore((s) => s.nodeState);

  const k = useMemo(() => {
    const open = Object.values(alerts).filter(isOpen);
    const bs = Object.values(buildings);
    return {
      open: open.length,
      critical: open.filter((a) => a.severity === 'critical').length,
      online: sensors.filter((x) => nodeState[x.node_id]).length,
      total: sensors.length,
      watch: bs.filter((b) => b.status !== 'ok').length,
      queue: bs.filter((b) => b.priority >= 65).length,
    };
  }, [alerts, buildings, sensors, nodeState]);

  const tiles = [
    { label: 'Open incidents', value: k.open, sub: `${k.critical} critical`, bg: 'linear-gradient(135deg,#1c4f9c,#1a3a78)', ring: '#3d7be0' },
    { label: 'Sensors online', value: `${k.online}/${k.total}`, sub: 'last 5 s', bg: 'linear-gradient(135deg,#127a58,#0f5a47)', ring: '#2fe39a' },
    { label: 'Buildings on watch', value: k.watch, sub: 'of 14 passports', bg: 'linear-gradient(135deg,#9a6a12,#6f4c10)', ring: '#ffb02e' },
    { label: 'Inspection queue', value: k.queue, sub: 'priority 65+', bg: 'linear-gradient(135deg,#2a3558,#1b2442)', ring: '#6c8fd8' },
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-md border p-2.5" style={{ background: t.bg, borderColor: t.ring + '66' }}>
          <div className="num font-display text-[26px] font-semibold leading-none">{t.value}</div>
          <div className="mt-1.5 text-[11px] text-white/85">{t.label}</div>
          <div className="text-[10px] text-white/55">{t.sub}</div>
        </div>
      ))}
    </div>
  );
}

/* ---------------- response routes ---------------- */
export function RoutesCard() {
  const alerts = useStore((s) => s.alerts);
  const routes = useStore((s) => s.routes);
  const selected = useStore((s) => s.selectedAlert);
  const now = useNow(1000);
  const focus = focusAlert(alerts, routes, selected);
  const rs = focus ? routes[focus.id] : undefined;

  return (
    <Section title="Response routes" hint={focus && rs ? focus.title : undefined}>
      {!focus || !rs ? (
        <p className="text-[12px] text-dim">Routes appear here once an incident is confirmed. Each responder gets its own route because lane width and stairs limit them differently.</p>
      ) : (
        <ul className="space-y-2">
          {rs.map((r) => {
            const m = PROFILE_META[r.profile];
            const progress = focus.dispatched_at ? Math.min(1, (((now - focus.dispatched_at) / 1000) * CONFIG.timeScale) / Math.max(1, r.travel_s)) : 0;
            return (
              <li key={r.profile} className="rounded-md border border-line bg-[#0a1226] p-2">
                <div className="flex items-center gap-2">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full font-display text-[12px] font-bold text-[#060a14]" style={{ background: m.color }}>
                    {m.glyph}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px] font-medium">{m.label}</span>
                  <span className="num font-mono text-[15px] font-medium" style={{ color: m.color }}>
                    {fmtEta(r.eta_s)}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-dim">
                  {fmtDist(r.length_m)}
                  {r.last_mile_m > 8 && r.profile !== 'evacuation' ? ` + ${r.last_mile_m} m on foot` : ''} · {r.note}
                </div>
                {focus.dispatched_at && (
                  <div className="mt-1.5 h-1 overflow-hidden rounded bg-[#16213f]" aria-hidden="true">
                    <div className="h-full" style={{ width: `${progress * 100}%`, background: m.color }} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

/* ---------------- safety score + trend ---------------- */
export function SafetyCard() {
  const alerts = useStore((s) => s.alerts);
  const hist = useStore((s) => s.riskHistory);
  const score = safetyScore(alerts);
  const color = score >= 80 ? CHART.green : score >= 55 ? CHART.amber : CHART.red;

  const option = useMemo<EChartsCoreOption>(
    () => ({
      animation: false,
      grid: { left: 28, right: 12, top: 8, bottom: 20 },
      tooltip: { trigger: 'axis', backgroundColor: '#0a1226', borderColor: '#1d2b4d', textStyle: { color: '#dbe6ff', fontSize: 11 } },
      xAxis: {
        type: 'time',
        axisLabel: { color: CHART.text, fontSize: 10, formatter: (v: number) => timeLabel(v).slice(3) },
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      yAxis: { type: 'value', min: 0, max: 100, interval: 50, axisLabel: { color: CHART.text, fontSize: 10 }, splitLine: { lineStyle: { color: CHART.grid } } },
      series: [
        {
          type: 'line',
          data: hist.map((h) => [h.ts, h.score]),
          showSymbol: false,
          smooth: true,
          lineStyle: { color, width: 2 },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '55' }, { offset: 1, color: color + '00' }] } },
          markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: CHART.red, type: 'dashed', opacity: 0.5 }, data: [{ yAxis: 55 }] },
        },
      ],
    }),
    [hist, color],
  );

  return (
    <Section title="City safety score" hint="dashed line = escalation level">
      <div className="mb-1 flex items-end gap-3">
        <span className="num font-display text-[34px] font-semibold leading-none" style={{ color }}>
          {score}
        </span>
        <span className="pb-1 text-[11px] text-dim">out of 100, weighted by open alerts and confidence</span>
      </div>
      <Chart option={option} height={108} />
    </Section>
  );
}

/* ---------------- building passport + inspection queue ---------------- */
function Meter({ label, value, unit, warn, max }: { label: string; value: number; unit: string; warn: number; max: number }) {
  const over = value >= warn;
  return (
    <div>
      <div className="flex justify-between text-[11px]">
        <span className="text-dim">{label}</span>
        <span className="num font-mono" style={{ color: over ? 'var(--orange)' : 'var(--text)' }}>
          {value.toFixed(2)} {unit}
        </span>
      </div>
      <div className="relative mt-1 h-1.5 rounded bg-[#16213f]">
        <div className="h-full rounded" style={{ width: `${Math.min(100, (value / max) * 100)}%`, background: over ? 'var(--orange)' : 'var(--cyan)' }} />
        <i className="absolute top-[-2px] h-[10px] w-px bg-white/60" style={{ left: `${(warn / max) * 100}%` }} aria-hidden="true" />
      </div>
    </div>
  );
}

export function BuildingCard() {
  const buildings = useStore((s) => s.buildings);
  const selected = useStore((s) => s.selectedBuilding);
  const select = useStore((s) => s.selectBuilding);
  const queue = useMemo(() => Object.values(buildings).sort((a, b) => b.priority - a.priority).slice(0, 6), [buildings]);
  const b = selected ? buildings[selected] : undefined;
  const statusColor = { ok: 'var(--green)', watch: 'var(--amber)', inspect: 'var(--orange)', fire: 'var(--red)' } as const;

  return (
    <Section title={b ? 'Building passport' : 'Inspection queue'} hint={b ? undefined : 'ranked by AI priority'}>
      {b && (
        <div className="mb-3 rounded-md border border-line bg-[#0a1226] p-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate font-display text-[14px] font-semibold">
                {b.id} <span className="font-sans font-normal text-dim">{b.name}</span>
              </div>
              <div className="text-[11px] text-dim">
                {b.use} · {b.construction}
              </div>
            </div>
            <button className="btn px-2 py-0.5 text-[11px]" onClick={() => select(null)}>
              Close
            </button>
          </div>
          <dl className="num mt-2 grid grid-cols-4 gap-2 text-[11px]">
            {[['Built', b.year_built], ['Floors', b.floors], ['Occupants', `~${b.occupancy}`], ['Inspected', b.last_inspection.slice(0, 7)]].map(([k, v]) => (
              <div key={String(k)}>
                <dt className="text-dim">{k}</dt>
                <dd className="font-mono text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-2.5 space-y-2">
            <Meter label="Tilt" value={b.tilt_deg} unit="°" warn={0.8} max={1.6} />
            <Meter label="Crack width" value={b.crack_mm} unit="mm" warn={1.0} max={2} />
          </div>
          <div className="mt-2.5 flex items-center gap-2 text-[11px]">
            <span className="text-dim">Priority</span>
            <span className="num font-mono text-[14px]" style={{ color: statusColor[b.status] }}>
              {b.priority}
            </span>
            <span className="rounded px-1.5 py-0.5 font-display text-[10px] tracking-wider" style={{ color: statusColor[b.status], background: statusColor[b.status] + '22' }}>
              {b.status.toUpperCase()}
            </span>
          </div>
          <p className="mt-2 text-[10.5px] leading-snug text-dim">AI ranks inspection priority from sensors and photos. A structural engineer validates safety.</p>
        </div>
      )}
      <ol className="space-y-1">
        {queue.map((q, i) => (
          <li key={q.id}>
            <button onClick={() => select(q.id)} className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-[#16213f] ${q.id === selected ? 'bg-[#16213f]' : ''}`}>
              <span className="num w-4 font-mono text-[11px] text-dim">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate text-[12px]">
                <b className="font-medium">{q.id}</b> <span className="text-dim">{q.name}</span>
              </span>
              <span className="h-1 w-10 overflow-hidden rounded bg-[#16213f]" aria-hidden="true">
                <span className="block h-full" style={{ width: `${q.priority}%`, background: statusColor[q.status] }} />
              </span>
              <span className="num w-6 text-right font-mono text-[12px]">{q.priority}</span>
            </button>
          </li>
        ))}
      </ol>
    </Section>
  );
}

/* ---------------- stormwater ---------------- */
export function StormCard() {
  const hist = useStore((s) => s.rainHistory);
  const zones = useStore((s) => s.floodZones);
  const iv = useStore((s) => s.interventions);
  const last = hist[hist.length - 1];

  const option = useMemo<EChartsCoreOption>(
    () => ({
      animation: false,
      grid: { left: 30, right: 30, top: 14, bottom: 20 },
      tooltip: { trigger: 'axis', backgroundColor: '#0a1226', borderColor: '#1d2b4d', textStyle: { color: '#dbe6ff', fontSize: 11 } },
      xAxis: { type: 'category', data: hist.map((h) => timeLabel(h.ts).slice(3)), axisLabel: { color: CHART.text, fontSize: 10, interval: 'auto' }, axisLine: { lineStyle: { color: CHART.axis } }, axisTick: { show: false } },
      yAxis: [
        { type: 'value', name: 'mm/h', nameTextStyle: { color: CHART.text, fontSize: 10 }, min: 0, max: 80, splitNumber: 2, axisLabel: { color: CHART.text, fontSize: 10 }, splitLine: { lineStyle: { color: CHART.grid } } },
        { type: 'value', name: 'cm', nameTextStyle: { color: CHART.text, fontSize: 10 }, min: 0, max: 40, splitNumber: 2, axisLabel: { color: CHART.text, fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: 'Rainfall mm/h', type: 'bar', data: hist.map((h) => h.rain), itemStyle: { color: '#2b6fd6' }, barMaxWidth: 6 },
        { name: 'Water level cm', type: 'line', yAxisIndex: 1, data: hist.map((h) => h.level), showSymbol: false, smooth: true, lineStyle: { color: CHART.cyan, width: 2 }, markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: CHART.red, type: 'dashed', opacity: 0.5 }, data: [{ yAxis: 25 }] } },
      ],
    }),
    [hist],
  );

  return (
    <Section title="Stormwater" hint="dashed line = tender-blocking depth">
      <div className="mb-1 grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <div className="text-dim">Rainfall</div>
          <div className="num font-mono text-[15px]">{(last?.rain ?? 0).toFixed(0)} <span className="text-[11px] text-dim">mm/h</span></div>
        </div>
        <div>
          <div className="text-dim">Peak level</div>
          <div className="num font-mono text-[15px]">{(last?.level ?? 0).toFixed(0)} <span className="text-[11px] text-dim">cm</span></div>
        </div>
        <div>
          <div className="text-dim">Flooded lanes</div>
          <div className="num font-mono text-[15px]">{zones.length}</div>
        </div>
      </div>
      <Chart option={option} height={118} />
      <div className="mt-2">
        <div className="label mb-1">Suggested interventions</div>
        {iv.length === 0 ? (
          <p className="text-[12px] text-dim">No waterlogging now. Ranked fixes appear once a hotspot forms.</p>
        ) : (
          <ol className="space-y-1">
            {iv.map((x) => (
              <li key={x.id} className="flex items-center gap-2 rounded bg-[#0a1226] px-2 py-1.5 text-[12px]">
                <span className="num grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[#16213f] font-mono text-[11px]">{x.rank}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{x.name}</span>
                  <span className="block truncate text-[11px] text-dim">{x.where}</span>
                </span>
                <span className="num shrink-0 text-right font-mono text-[11px]">
                  <span className="text-good">-{x.reduces_pct}%</span>
                  <br />
                  <span className="text-dim">₹{x.cost_lakh} L</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Section>
  );
}

/* ---------------- raw sensor feed ---------------- */
export function FeedCard() {
  const log = useStore((s) => s.log);
  const sensors = useStore((s) => s.sensors);
  return (
    <Section title="Sensor feed" hint={`${sensors.length} nodes · 1 Hz`}>
      <ul className="num space-y-0.5 font-mono text-[11px]" aria-live="off">
        {log.slice(0, 9).map((l, i) => (
          <li key={`${l.ts}-${i}`} className="flex gap-2 truncate" style={{ color: l.hot ? SEV_META.critical.color : 'var(--dim)' }}>
            <span className="shrink-0 opacity-60">{timeLabel(l.ts)}</span>
            <span className="truncate">{l.text}</span>
          </li>
        ))}
        {log.length === 0 && <li className="text-dim">Waiting for telemetry…</li>}
      </ul>
    </Section>
  );
}
