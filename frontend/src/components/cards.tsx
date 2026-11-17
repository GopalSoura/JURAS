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
    <section className="card p-2.5">
      <div className="mb-2 flex items-baseline justify-between gap-2 border-b border-line pb-1.5">
        <h3 className="label">{title}</h3>
        {hint && <span className="truncate text-[10.5px] text-dim">{hint}</span>}
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
      totalB: bs.length,
      queue: bs.filter((b) => b.priority >= 65).length,
    };
  }, [alerts, buildings, sensors, nodeState]);

  const tiles = [
    { label: 'Open incidents', value: k.open, sub: `${k.critical} critical`, accent: k.critical ? 'var(--red)' : k.open ? 'var(--amber)' : 'var(--green)' },
    { label: 'Sensors online', value: `${k.online}/${k.total}`, sub: 'last 5 s', accent: k.online === k.total ? 'var(--green)' : 'var(--amber)' },
    { label: 'Buildings on watch', value: k.watch, sub: `of ${k.totalB} tracked`, accent: k.watch ? 'var(--amber)' : 'var(--green)' },
    { label: 'Inspection queue', value: k.queue, sub: 'priority 65+', accent: 'var(--accent)' },
  ];
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {tiles.map((t) => (
        <div key={t.label} className="border border-line bg-panel2 p-2.5">
          <div className="num font-mono text-[22px] font-medium leading-none">{t.value}</div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[10.5px] text-dim">
            <i className="inline-block h-1.5 w-1.5" style={{ background: t.accent }} aria-hidden="true" />
            <span className="truncate">{t.label}</span>
          </div>
          <div className="text-[9.5px] text-faint">{t.sub}</div>
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
        <p className="text-[11.5px] leading-snug text-dim">Routes appear here once an incident is confirmed. Each responder gets its own route because lane width and stairs limit them differently.</p>
      ) : (
        <ul className="space-y-1.5">
          {rs.map((r) => {
            const m = PROFILE_META[r.profile];
            const drawable = r.feasible && r.path.length >= 2;
            const progress = focus.dispatched_at && drawable ? Math.min(1, (((now - focus.dispatched_at) / 1000) * CONFIG.timeScale) / Math.max(1, r.travel_s)) : 0;
            return (
              <li key={r.profile} className="border border-line bg-panel px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="num grid h-[18px] w-[18px] shrink-0 place-items-center border font-mono text-[10px]" style={{ borderColor: m.color + '77', color: m.color }}>
                    {m.glyph}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium">{m.label}</span>
                  <span className={`num font-mono text-[13px] font-medium${drawable ? '' : ' text-crit'}`} style={drawable ? { color: m.color } : undefined}>
                    {drawable ? fmtEta(r.eta_s) : 'No route'}
                  </span>
                </div>
                <div className="mt-1 text-[10.5px] leading-snug text-dim">
                  {drawable ? (
                    <>
                      {fmtDist(r.length_m)}
                      {r.last_mile_m > 8 && r.profile !== 'evacuation' ? ` + ${r.last_mile_m} m on foot` : ''} · {r.note}
                    </>
                  ) : (
                    <span className="text-crit">{r.note}</span>
                  )}
                </div>
                {focus.dispatched_at && drawable && (
                  <div className="mt-1.5 h-[2px] w-full" style={{ background: 'var(--raise)' }} aria-hidden="true">
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
      tooltip: { trigger: 'axis', backgroundColor: '#101623', borderColor: '#232d40', textStyle: { color: '#d7dfec', fontSize: 11 } },
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
          lineStyle: { color, width: 1.5 },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '40' }, { offset: 1, color: color + '00' }] } },
          markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: CHART.red, type: 'dashed', opacity: 0.45 }, data: [{ yAxis: 55 }] },
        },
      ],
    }),
    [hist, color],
  );

  return (
    <Section title="City safety score" hint="dashed line = escalation level">
      <div className="mb-1 flex items-end gap-3">
        <span className="num font-mono text-[26px] font-medium leading-none" style={{ color }}>
          {score}
        </span>
        <span className="pb-0.5 text-[10.5px] text-dim">out of 100, weighted by open alerts and confidence</span>
      </div>
      <Chart option={option} height={104} />
    </Section>
  );
}

/* ---------------- building passport + inspection queue ---------------- */
function Meter({ label, value, unit, warn, max }: { label: string; value: number; unit: string; warn: number; max: number }) {
  const over = value >= warn;
  return (
    <div>
      <div className="flex justify-between text-[10.5px]">
        <span className="text-dim">{label}</span>
        <span className="num font-mono" style={{ color: over ? 'var(--orange)' : 'var(--text)' }}>
          {value.toFixed(2)} {unit}
        </span>
      </div>
      <div className="relative mt-1 h-[3px]" style={{ background: 'var(--raise)' }}>
        <div className="h-full" style={{ width: `${Math.min(100, (value / max) * 100)}%`, background: over ? 'var(--orange)' : 'var(--accent)' }} />
        <i className="absolute top-[-2px] h-[7px] w-px bg-white/50" style={{ left: `${(warn / max) * 100}%` }} aria-hidden="true" />
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
        <div className="mb-2.5 border border-line bg-panel p-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-semibold">
                {b.id} <span className="font-normal text-dim">{b.name}</span>
              </div>
              <div className="text-[10.5px] text-dim">
                {b.use || '—'} · {b.construction || 'construction unverified'}
              </div>
            </div>
            <button className="btn px-2 py-0.5 text-[10.5px]" onClick={() => select(null)}>
              Close
            </button>
          </div>
          <dl className="num mt-2 grid grid-cols-4 gap-2 text-[10.5px]">
            {[['Built', b.year_built > 0 ? b.year_built : '—'], ['Floors', b.floors], ['Occupants', `~${b.occupancy}`], ['Inspected', b.last_inspection ? b.last_inspection.slice(0, 7) : '—']].map(([k, v]) => (
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
          <div className="mt-2.5 flex items-center gap-2 text-[10.5px]">
            <span className="text-dim">Priority</span>
            <span className="num font-mono text-[13px]" style={{ color: statusColor[b.status] }}>
              {b.priority}
            </span>
            <span className="px-1.5 py-px text-[9.5px] font-semibold tracking-[0.06em]" style={{ color: statusColor[b.status], background: statusColor[b.status] + '1c' }}>
              {b.status.toUpperCase()}
            </span>
          </div>
          <p className="mt-2 text-[10px] leading-snug text-faint">AI ranks inspection priority from sensors and photos. A structural engineer validates safety.</p>
        </div>
      )}
      <ol className="space-y-0.5">
        {queue.map((q, i) => (
          <li key={q.id}>
            <button onClick={() => select(q.id)} className={`flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-raise ${q.id === selected ? 'bg-raise' : ''}`}>
              <span className="num w-4 font-mono text-[10.5px] text-faint">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate text-[11.5px]">
                <b className="font-medium">{q.id}</b> <span className="text-dim">{q.name}</span>
              </span>
              <span className="h-[3px] w-10" style={{ background: 'var(--raise)' }} aria-hidden="true">
                <span className="block h-full" style={{ width: `${q.priority}%`, background: statusColor[q.status] }} />
              </span>
              <span className="num w-6 text-right font-mono text-[11.5px]">{q.priority}</span>
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
      tooltip: { trigger: 'axis', backgroundColor: '#101623', borderColor: '#232d40', textStyle: { color: '#d7dfec', fontSize: 11 } },
      xAxis: { type: 'category', data: hist.map((h) => timeLabel(h.ts).slice(3)), axisLabel: { color: CHART.text, fontSize: 10, interval: 'auto' }, axisLine: { lineStyle: { color: CHART.axis } }, axisTick: { show: false } },
      yAxis: [
        { type: 'value', name: 'mm/h', nameTextStyle: { color: CHART.text, fontSize: 10 }, min: 0, max: 80, splitNumber: 2, axisLabel: { color: CHART.text, fontSize: 10 }, splitLine: { lineStyle: { color: CHART.grid } } },
        { type: 'value', name: 'cm', nameTextStyle: { color: CHART.text, fontSize: 10 }, min: 0, max: 40, splitNumber: 2, axisLabel: { color: CHART.text, fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: 'Rainfall mm/h', type: 'bar', data: hist.map((h) => h.rain), itemStyle: { color: '#3a6db0' }, barMaxWidth: 5 },
        { name: 'Water level cm', type: 'line', yAxisIndex: 1, data: hist.map((h) => h.level), showSymbol: false, smooth: true, lineStyle: { color: CHART.cyan, width: 1.5 }, markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: CHART.red, type: 'dashed', opacity: 0.45 }, data: [{ yAxis: 25 }] } },
      ],
    }),
    [hist],
  );

  return (
    <Section title="Stormwater" hint="dashed line = tender-blocking depth">
      <div className="mb-1 grid grid-cols-3 gap-2 text-[10.5px]">
        <div>
          <div className="text-dim">Rainfall</div>
          <div className="num font-mono text-[14px]">{(last?.rain ?? 0).toFixed(0)} <span className="text-[10.5px] text-dim">mm/h</span></div>
        </div>
        <div>
          <div className="text-dim">Peak level</div>
          <div className="num font-mono text-[14px]">{(last?.level ?? 0).toFixed(0)} <span className="text-[10.5px] text-dim">cm</span></div>
        </div>
        <div>
          <div className="text-dim">Flooded lanes</div>
          <div className="num font-mono text-[14px]">{zones.length}</div>
        </div>
      </div>
      <Chart option={option} height={112} />
      <div className="mt-2">
        <div className="label mb-1">Suggested interventions</div>
        {iv.length === 0 ? (
          <p className="text-[11.5px] text-dim">No waterlogging now. Ranked fixes appear once a hotspot forms.</p>
        ) : (
          <ol className="space-y-1">
            {iv.map((x) => (
              <li key={x.id} className="flex items-center gap-2 bg-panel px-2 py-1.5 text-[11.5px]">
                <span className="num grid h-[18px] w-[18px] shrink-0 place-items-center border border-line font-mono text-[10px] text-dim">{x.rank}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{x.name}</span>
                  <span className="block truncate text-[10.5px] text-dim">{x.where}</span>
                </span>
                <span className="num shrink-0 text-right font-mono text-[10.5px]">
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
      <ul className="num space-y-0.5 font-mono text-[10.5px]" aria-live="off">
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
