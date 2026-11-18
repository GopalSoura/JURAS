// Headless check of the frontend live-state reducers used by the Zustand store.
// Run: npm run live:check
import { mergeRisks, mergeTelemetry, sensorForDevice } from '../src/lib/live';
import type { RiskState, SensorMeta, Telemetry } from '../src/types';

let failed = 0;
const check = (ok: boolean, msg: string) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${msg}`);
  if (!ok) failed++;
};

const sensor = (node_id: string, kind: SensorMeta['kind'], device_id: string): SensorMeta => ({
  node_id,
  kind,
  pos: [74.85, 32.72],
  label: node_id,
  building_id: kind === 'rain_level' ? undefined : 'B-007',
  node_code: kind === 'rain_level' ? 'I' : null,
  device_id,
  source: 'simulation',
  simulation: true,
});

const telemetry = (node_id: string, kind: SensorMeta['kind'], values: Record<string, number>, device: string): Telemetry => ({
  node_id,
  kind,
  ts: 1_700_000_000_000,
  battery: 90,
  values,
  device_id: device,
  source: 'simulation',
  simulation: true,
  live: true,
  observed_at: '2026-11-18T10:00:00+00:00',
});

const sensors = [
  sensor('JM-014', 'smoke_temp', 'JURAS-FIRE-001'),
  sensor('JM-S07', 'structure', 'JURAS-STRUCT-001'),
  sensor('JM-R01', 'rain_level', 'JURAS-STORM-001'),
];

check(sensorForDevice(sensors, 'JURAS-FIRE-001')?.node_id === 'JM-014', 'device lookup: fire');
check(sensorForDevice(sensors, 'JURAS-STRUCT-001')?.node_id === 'JM-S07', 'device lookup: structural');
check(sensorForDevice(sensors, 'JURAS-STORM-001')?.node_id === 'JM-R01', 'device lookup: stormwater');
check(sensorForDevice(sensors, 'JURAS-UNKNOWN') === undefined, 'device lookup: unknown returns undefined');

const empty = {};
check(mergeTelemetry(empty, []) === empty, 'empty telemetry frame keeps state identity');
check(mergeRisks(empty, []) === empty, 'empty risk snapshot keeps state identity');

const first = mergeTelemetry(empty, [
  telemetry('JM-014', 'smoke_temp', { smoke_ppm: 40, temp_c: 31.8 }, 'JURAS-FIRE-001'),
  telemetry('JM-S07', 'structure', { tilt_deg: 0.05, crack_mm: 0.12 }, 'JURAS-STRUCT-001'),
  telemetry('JM-R01', 'rain_level', { level_cm: 2, rain_mmh: 0 }, 'JURAS-STORM-001'),
]);
check(Object.keys(first).length === 3, 'telemetry frame stores all three nodes');
check(first['JM-014'].values.smoke_ppm === 40, 'fire telemetry value preserved');
check(first['JM-014'].simulation === true, 'fire telemetry keeps simulation flag');

const second = mergeTelemetry(first, [
  telemetry('JM-014', 'smoke_temp', { smoke_ppm: 720, temp_c: 58.5 }, 'JURAS-FIRE-001'),
]);
check(first['JM-014'].values.smoke_ppm === 40, 'previous telemetry object is not mutated');
check(second['JM-014'].values.smoke_ppm === 720, 'new fire telemetry replaces old value');
check(second['JM-S07'].values.tilt_deg === 0.05, 'unrelated structural telemetry kept');
check(Object.keys(second).length === 3, 'telemetry merge does not drop nodes');

const risk = (sensor_code: string | undefined, entity_code: string, score: number, category: RiskState['category']): RiskState => ({
  sensor_code,
  device_id: 'JURAS-STRUCT-001',
  hazard: 'structural',
  entity_type: 'building',
  entity_code,
  building_code: entity_code,
  node_code: null,
  score,
  category,
  reasons: [{ rule: 'STRUCT-R1', text: 'tilt over threshold' }],
  assessed_at: '2026-11-18T10:00:00+00:00',
  simulation: true,
});

const risks0 = mergeRisks(empty, [risk('JM-014', 'B-014', 2, 'normal'), risk('JM-S07', 'B-007', 30, 'low')]);
check(Object.keys(risks0).length === 2, 'snapshot risks are keyed by sensor code');
check(risks0['JM-S07'].score === 30, 'snapshot structural risk preserved');

const risks1 = mergeRisks(risks0, risk('JM-S07', 'B-007', 92, 'critical'));
check(risks1['JM-S07'].score === 92, 'risk frame replaces the same sensor');
check(risks1['JM-S07'].category === 'critical', 'risk frame category reaches the card');
check(risks1['JM-014'].score === 2, 'risk frame keeps other sensors');
check(risks0['JM-S07'].score === 30, 'previous risk object is not mutated');

const fallback = mergeRisks(empty, risk(undefined, 'I', 60, 'warning'));
check(fallback['I']?.score === 60, 'risk without sensor_code falls back to entity_code');

console.log(failed ? `LIVE CHECK FAILED: ${failed}` : 'ALL LIVE CHECKS PASSED');
process.exitCode = failed ? 1 : 0;
