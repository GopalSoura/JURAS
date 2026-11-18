import type { RiskState, SensorMeta, Telemetry } from '../types';

/** Merge one `/ws` telemetry frame into the node map without mutating state. */
export function mergeTelemetry(
  prev: Record<string, Telemetry>,
  items: Telemetry[],
): Record<string, Telemetry> {
  if (!items.length) return prev;
  const next = { ...prev };
  for (const item of items) next[item.node_id] = item;
  return next;
}

/**
 * Merge hardware-reading frames into Realtime Mode state only.  A frame with
 * no `live_values` is ignored: missing data must stay N/A, never normal.
 */
export function mergeLiveTelemetry(
  prev: Record<string, Telemetry>,
  items: Telemetry[],
): Record<string, Telemetry> {
  const live = items.filter((item) => item.live_values && Object.keys(item.live_values).length > 0);
  if (!live.length) return prev;
  const next = { ...prev };
  for (const item of live) {
    next[item.node_id] = { ...item, values: item.live_values! };
  }
  return next;
}

/** Merge a snapshot risk list or a single `risk` frame, keyed by sensor code. */
export function mergeRisks(
  prev: Record<string, RiskState>,
  incoming: RiskState[] | RiskState,
): Record<string, RiskState> {
  const list = Array.isArray(incoming) ? incoming : [incoming];
  if (!list.length) return prev;
  const next = { ...prev };
  for (const risk of list) next[risk.sensor_code ?? risk.entity_code] = risk;
  return next;
}

/** Resolve the IoT card for a device even before the first telemetry arrives. */
export function sensorForDevice(sensors: SensorMeta[], deviceId: string): SensorMeta | undefined {
  return sensors.find((sensor) => sensor.device_id === deviceId);
}
