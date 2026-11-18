import type { ReactNode } from 'react';
import { useStore } from '../store';
import { useNow } from '../hooks';
import { fmtElapsed } from '../lib/metrics';
import type { RiskState, SensorKind, Telemetry } from '../types';
import { Section } from './cards';

type NodeKey = 'fire' | 'structure' | 'storm';

interface NodeCfg {
  deviceId: string;
  sensorCode: string;
  kind: SensorKind;
  title: string;
  buildingNo: string;
  target: string;
  healthFlags: string[];
}

const NODES: Record<NodeKey, NodeCfg> = {
  fire: {
    deviceId: 'JURAS-FIRE-001',
    sensorCode: 'JM-014',
    kind: 'smoke_temp',
    title: 'Old Jammu Heritage Building',
    buildingNo: 'JURAS-BLD-001',
    target: 'Backend: B-014 · JM-014',
    healthFlags: ['dht_ok', 'mq2_ok'],
  },
  structure: {
    deviceId: 'JURAS-STRUCT-001',
    sensorCode: 'JM-S07',
    kind: 'structure',
    title: 'Residential Structure — Purani Mandi',
    buildingNo: 'JURAS-BLD-002',
    target: 'Backend: B-007 · JM-S07',
    healthFlags: ['mpu_ok', 'crack_ok'],
  },
  storm: {
    deviceId: 'JURAS-STORM-001',
    sensorCode: 'JM-R01',
    kind: 'rain_level',
    title: 'Flood-Prone Lane Building — Purani Mandi',
    buildingNo: 'JURAS-BLD-003',
    target: 'Backend: lane node I · JM-R01',
    healthFlags: ['dht_ok', 'sonar_ok', 'ultrasonic_ok', 'rain_ok'],
  },
};

const RISK_COLOR: Record<string, string> = {
  normal: 'var(--green)',
  low: 'var(--green)',
  warning: 'var(--amber)',
  high: 'var(--orange)',
  critical: 'var(--red)',
  waiting: 'var(--dim)',
};

type Health = 'ONLINE' | 'STALE' | 'OFFLINE' | 'SENSOR ERROR' | 'SIMULATED';

const HEALTH_COLOR: Record<Health, string> = {
  ONLINE: 'var(--green)',
  STALE: 'var(--amber)',
  OFFLINE: 'var(--red)',
  'SENSOR ERROR': 'var(--red)',
  SIMULATED: 'var(--accent)',
};

const num = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined;

function measure(v: unknown, digits = 1, unit = ''): string {
  const n = num(v);
  return n === undefined ? 'N/A' : `${n.toFixed(digits)}${unit ? ` ${unit}` : ''}`;
}

function first(values: Record<string, number> | undefined, keys: string[]): number | undefined {
  if (!values) return undefined;
  for (const key of keys) {
    const n = num(values[key]);
    if (n !== undefined) return n;
  }
  return undefined;
}

function nodeHealth(cfg: NodeCfg, telemetry: Telemetry | undefined, now: number): Health {
  const values = telemetry?.values;
  const observed = telemetry?.observed_at ? Date.parse(telemetry.observed_at) : telemetry?.ts;
  const age = typeof observed === 'number' && Number.isFinite(observed) ? now - observed : Infinity;
  if (!values || !Object.keys(values).length) return 'OFFLINE';
  if (age > 180_000) return 'OFFLINE';
  if (cfg.healthFlags.some((flag) => num(values[flag]) === 0)) return 'SENSOR ERROR';
  if (telemetry?.stale || age > 30_000) return 'STALE';
  return 'ONLINE';
}

function useNode(key: NodeKey) {
  const cfg = NODES[key];
  const mode = useStore((s) => s.mode);
  const sensor = useStore((s) =>
    s.sensors.find((x) => x.device_id === cfg.deviceId) ?? s.sensors.find((x) => x.node_id === cfg.sensorCode),
  );
  const simTelemetry = useStore((s) => s.nodeState[sensor?.node_id ?? cfg.sensorCode]);
  const liveTelemetry = useStore((s) => s.liveState[sensor?.node_id ?? cfg.sensorCode]);
  const simRisk = useStore((s) => s.risks[sensor?.node_id ?? cfg.sensorCode]);
  const liveRisk = useStore((s) => s.liveRisks[sensor?.node_id ?? cfg.sensorCode]);
  const realtime = mode === 'realtime';
  const telemetry = realtime ? liveTelemetry : simTelemetry;
  const risk: RiskState | undefined = realtime ? liveRisk : simRisk;
  return { cfg, sensor, telemetry, risk, realtime };
}

function Value({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] text-dim">{label}</div>
      <div className="num truncate font-mono text-[13px] text-ink">{children}</div>
    </div>
  );
}

function Metrics({
  nodeKey,
  telemetry,
  realtime,
}: {
  nodeKey: NodeKey;
  telemetry: Telemetry | undefined;
  realtime: boolean;
}) {
  const v = telemetry?.values;
  // Hardware readings keep source="simulation" on the wire (Wokwi is simulated
  // hardware), so Realtime Mode shows the environment the values came from.
  const sourceLabel = !telemetry ? 'N/A' : realtime ? 'Wokwi env' : telemetry.source ?? 'simulation';
  if (nodeKey === 'fire') {
    const flame = first(v, ['flame']);
    return (
      <div className="grid grid-cols-3 gap-2">
        <Value label="Temperature">{measure(first(v, ['temp_c', 'temperature_c']), 1, '°C')}</Value>
        <Value label="Humidity">{measure(first(v, ['humidity_pct']), 1, '%')}</Value>
        <Value label="Smoke">{measure(first(v, ['smoke_level', 'smoke_ppm']), 1)}</Value>
        <Value label="Flame">{flame === undefined ? 'N/A' : flame > 0 ? 'DETECTED' : 'CLEAR'}</Value>
        <Value label="Last update">{telemetry?.observed_at ? new Date(telemetry.observed_at).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false }) : 'N/A'}</Value>
        <Value label="Source">{sourceLabel}</Value>
      </div>
    );
  }
  if (nodeKey === 'structure') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <Value label="Tilt">{measure(first(v, ['tilt_deg']), 2, '°')}</Value>
        <Value label="Crack simulation">{measure(first(v, ['crack_mm']), 2, 'mm')}</Value>
        <Value label="Vibration">{measure(first(v, ['vib_rms']), 3, 'm/s²')}</Value>
        <Value label="Deviation">{measure(first(v, ['deviation_mm']), 1, 'mm')}</Value>
        <Value label="Last update">{telemetry?.observed_at ? new Date(telemetry.observed_at).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false }) : 'N/A'}</Value>
        <Value label="Source">{sourceLabel}</Value>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-3 gap-2">
      <Value label="Water level">{measure(first(v, ['water_level_cm', 'level_cm']), 1, 'cm')}</Value>
      <Value label="Rain (raw)">{measure(first(v, ['rain_mmh', 'rain_raw']), 1)}</Value>
      <Value label="Temperature">{measure(first(v, ['temp_c', 'temperature_c']), 1, '°C')}</Value>
      <Value label="Humidity">{measure(first(v, ['humidity_pct']), 1, '%')}</Value>
      <Value label="Last update">{telemetry?.observed_at ? new Date(telemetry.observed_at).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false }) : 'N/A'}</Value>
      <Value label="Source">{sourceLabel}</Value>
    </div>
  );
}

function NodeCard({ nodeKey }: { nodeKey: NodeKey }) {
  const { cfg, sensor, telemetry, risk, realtime } = useNode(nodeKey);
  const now = useNow(1000);
  const health: Health = realtime ? nodeHealth(cfg, telemetry, now) : 'SIMULATED';
  const category = risk?.category ?? (realtime ? undefined : telemetry?.risk?.category) ?? 'waiting';
  const riskColor = RISK_COLOR[category] ?? 'var(--dim)';
  const observed = telemetry?.observed_at ? Date.parse(telemetry.observed_at) : telemetry?.ts;
  const lastReading = typeof observed === 'number' && Number.isFinite(observed) ? fmtElapsed(now - observed) : null;
  const reason = risk?.reasons?.find((r) => r.text)?.text;

  return (
    <Section
      title={cfg.title}
      hint={
        <span className="flex items-center gap-1.5">
          <span className="num font-mono text-[10px] text-dim">{cfg.buildingNo}</span>
          <span className="flex items-center gap-1 text-[10px]" style={{ color: riskColor }}>
            <i className="inline-block h-1.5 w-1.5" style={{ background: riskColor }} />
            {realtime ? (risk?.category ? String(risk.category).toUpperCase() : 'N/A') : String(category).toUpperCase()}
          </span>
        </span>
      }
    >
      <div className="mb-1.5 flex items-center justify-between gap-2 text-[10.5px] text-dim">
        <span className="truncate">
          {cfg.deviceId} · {sensor?.label ?? cfg.sensorCode}
        </span>
        <span className="num flex shrink-0 items-center gap-1 font-mono" style={{ color: HEALTH_COLOR[health] }}>
          <i className="inline-block h-1.5 w-1.5" style={{ background: HEALTH_COLOR[health] }} />
          {health}
        </span>
      </div>

      <Metrics nodeKey={nodeKey} telemetry={telemetry} realtime={realtime} />

      <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-dim">
        <span className="truncate">{cfg.target}</span>
        {risk && (
          <span className="num shrink-0 font-mono">
            risk {risk.score} · {risk.category}
          </span>
        )}
      </div>
      {lastReading && <div className="mt-1 text-[10px] text-faint">Last reading: {lastReading} ago</div>}
      {reason && <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-faint">{reason}</p>}
    </Section>
  );
}

export function FireNodeCard() {
  return <NodeCard nodeKey="fire" />;
}

export function StructuralNodeCard() {
  return <NodeCard nodeKey="structure" />;
}

export function StormNodeCard() {
  return <NodeCard nodeKey="storm" />;
}

export function IoTPanel({ only }: { only?: NodeKey }) {
  if (only === 'fire') return <FireNodeCard />;
  if (only === 'structure') return <StructuralNodeCard />;
  if (only === 'storm') return <StormNodeCard />;
  return (
    <>
      <FireNodeCard />
      <StructuralNodeCard />
      <StormNodeCard />
    </>
  );
}
