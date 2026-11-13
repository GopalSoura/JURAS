import type { AlertModule, ModuleId, Profile, Severity } from '../types';

export type RGB = [number, number, number];

export const PROFILE_META: Record<Profile, { label: string; color: string; rgb: RGB; glyph: string }> = {
  fire_truck: { label: 'Fire tender', color: '#2fe39a', rgb: [47, 227, 154], glyph: 'F' },
  medical: { label: 'Medical micro-team', color: '#4db5ff', rgb: [77, 181, 255], glyph: 'M' },
  evacuation: { label: 'Evacuation on foot', color: '#ffc233', rgb: [255, 194, 51], glyph: 'E' },
};

export const SEV_META: Record<Severity, { label: string; color: string; rgb: RGB; rank: number; weight: number }> = {
  critical: { label: 'Critical', color: '#ff4d5e', rgb: [255, 77, 94], rank: 0, weight: 28 },
  high: { label: 'High', color: '#ff7a3d', rgb: [255, 122, 61], rank: 1, weight: 14 },
  medium: { label: 'Medium', color: '#ffb02e', rgb: [255, 176, 46], rank: 2, weight: 6 },
  low: { label: 'Low', color: '#6c8fd8', rgb: [108, 143, 216], rank: 3, weight: 2 },
};

export const MODULE_LABEL: Record<AlertModule, string> = {
  fire: 'Fire',
  structure: 'Structure',
  flood: 'Stormwater',
  map: 'Map QA',
};

export const NAV: { id: ModuleId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'fire', label: 'Fire' },
  { id: 'structure', label: 'Structures' },
  { id: 'flood', label: 'Stormwater' },
  { id: 'routing', label: 'Routing' },
  { id: 'sensors', label: 'Sensors' },
];

/** Which alert modules each nav tab shows. */
export const NAV_FILTER: Record<ModuleId, AlertModule[] | null> = {
  overview: null,
  fire: ['fire'],
  structure: ['structure'],
  flood: ['flood'],
  routing: ['fire', 'map'],
  sensors: null,
};
