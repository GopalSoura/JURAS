// Pure navigation contract checks. Run: npm run nav:check
import { formatDistance, formatEta, isValidLonLat, navRouteBounds, navRouteLine } from '../src/lib/navigation';
import type { NavResponse } from '../src/types';

const fail = (msg: string) => {
  console.error('FAIL:', msg);
  process.exitCode = 1;
};

const nav = {
  route: {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: [
        [74.859, 32.729],
        [74.8595, 32.729],
        [74.86, 32.7292],
      ],
    },
    properties: {
      distance_m: 128,
      duration_s: 46,
      profile: 'fire_truck',
      weighting: 'time',
      algorithm: 'astar_osm',
      geometry_source: 'openstreetmap',
      edge_count: 2,
      edge_ids: ['osm/1#1', 'osm/2#1'],
      warnings: ['test warning'],
      origin_snap_distance_m: 0,
      destination_snap_distance_m: 0,
    },
  },
  origin: {} as NavResponse['origin'],
  destination: {} as NavResponse['destination'],
  warnings: ['test warning'],
} satisfies NavResponse;

const line = navRouteLine(nav);
if (line.length !== 3) fail('valid LineString was not read');
const bounds = navRouteBounds(nav);
if (!bounds || bounds[0][0] !== 74.859 || bounds[1][0] !== 74.86) fail('route bounds are wrong');

if (navRouteLine({ ...nav, route: { ...nav.route, geometry: { type: 'LineString', coordinates: [[74.859, 32.729]] } } }).length !== 0) {
  fail('single-point route must be rejected');
}
if (navRouteLine({ ...nav, route: { ...nav.route, geometry: { type: 'LineString', coordinates: [[74.859, NaN], [74.86, 32.729]] } } }).length !== 0) {
  fail('non-finite route coordinate must be rejected');
}
if (navRouteBounds(null) !== null) fail('null route must have no bounds');
if (!isValidLonLat([74.859, 32.729]) || isValidLonLat([181, 32])) fail('lon/lat validation is wrong');

if (formatDistance(840) !== '840 m') fail('metre formatting is wrong');
if (formatDistance(7379) !== '7.4 km') fail('kilometre formatting is wrong');
if (formatEta(46) !== '< 1 min') fail('short ETA formatting is wrong');
if (formatEta(995) !== '17 min') fail('minute ETA formatting is wrong');
if (formatEta(null) !== 'ETA unavailable') fail('missing ETA fallback is wrong');

console.log('navigation geometry:', line.length, 'points | bounds', JSON.stringify(bounds));
console.log('distance:', formatDistance(nav.route.properties.distance_m), '| eta:', formatEta(nav.route.properties.duration_s));
console.log(process.exitCode ? 'CHECK FAILED' : 'ALL NAV CHECKS PASSED');
