import type { AlertModule, ModuleId, NavProfile, Profile, Severity } from '../types';

export type RGB = [number, number, number];

export const PROFILE_META: Record<Profile, { label: string; color: string; rgb: RGB; glyph: string }> = {
  fire_truck: { label: 'Fire tender', color: '#3fbf85', rgb: [63, 191, 133], glyph: 'F' },
  medical: { label: 'Medical micro-team', color: '#57a8e8', rgb: [87, 168, 232], glyph: 'M' },
  evacuation: { label: 'Evacuation on foot', color: '#d9a83c', rgb: [217, 168, 60], glyph: 'E' },
};

export const NAV_PROFILE_META: Record<NavProfile, { label: string; short: string; color: string; rgb: RGB }> = {
  fire_truck: { label: 'Fire tender', short: 'Truck', color: '#e07a45', rgb: [224, 122, 69] },
  responder_bike: { label: 'Responder bike', short: 'Bike', color: '#4d9fff', rgb: [77, 159, 255] },
  walking: { label: 'Walking responder', short: 'Walk', color: '#46c08a', rgb: [70, 192, 138] },
};

export const SEV_META: Record<Severity, { label: string; color: string; rgb: RGB; rank: number; weight: number }> = {
  critical: { label: 'Critical', color: '#e35d6a', rgb: [227, 93, 106], rank: 0, weight: 28 },
  high: { label: 'High', color: '#e07a45', rgb: [224, 122, 69], rank: 1, weight: 14 },
  medium: { label: 'Medium', color: '#e0a63c', rgb: [224, 166, 60], rank: 2, weight: 6 },
  low: { label: 'Low', color: '#6b83ad', rgb: [107, 131, 173], rank: 3, weight: 2 },
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
