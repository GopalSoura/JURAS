// Headless check of the simulator + fusion + routing. Run: npm run sim:check
import { SimFeed } from '../src/lib/simulator';
import type { Alert, Route, ServerMsg } from '../src/types';

const alerts = new Map<string, Alert>();
const routes = new Map<string, Route[]>();
let hazards = 0;
let floodMsgs = 0;

const feed = new SimFeed();
feed.start(
  (m: ServerMsg) => {
    if (m.t === 'snapshot') m.alerts.forEach((a) => alerts.set(a.id, a));
    if (m.t === 'alert') alerts.set(m.alert.id, m.alert);
    if (m.t === 'routes') routes.set(m.alert_id, m.routes);
    if (m.t === 'hazard') hazards++;
    if (m.t === 'flood') floodMsgs++;
  },
  () => {},
);
feed.stop();

let now = Date.now();
const run = (n: number) => {
  for (let i = 0; i < n; i++) feed.step((now += 1000));
};
const fail = (msg: string) => {
  console.error('FAIL:', msg);
  process.exitCode = 1;
};

run(3);
const fire = alerts.get('AL-FIRE-B-021');
console.log('fire alert:', fire?.title, fire?.confidence, fire?.status);
if (!fire || fire.severity !== 'critical') fail('initial fire not confirmed');
const fr = routes.get('AL-FIRE-B-021');
if (!fr || fr.length !== 3) fail('expected 3 routes');
for (const r of fr ?? []) console.log(` ${r.profile.padEnd(10)} ${r.length_m} m  eta ${r.eta_s}s  last ${r.last_mile_m} m  ${r.note}`);
if (fr && fr[0].last_mile_m < 60) fail('tender should stop short in narrow lane');

feed.send({ cmd: 'scenario', name: 'crack' });
run(80);
const st = alerts.get('AL-STR-B-007');
console.log('structure alert:', st?.title, st?.severity, st?.confidence);
if (st?.severity !== 'high') fail('crack scenario did not escalate');

feed.send({ cmd: 'scenario', name: 'flood' });
run(90);
const fl = [...alerts.values()].filter((a) => a.module === 'flood' && a.status !== 'resolved');
console.log('flood alerts:', fl.map((a) => `${a.title} (${a.severity})`).join(' | '), '| zone msgs', floodMsgs);
if (!fl.length) fail('flood scenario did not alert');

const fr2 = routes.get('AL-FIRE-B-021');
console.log('re-planned tender:', fr2?.[0].note, fr2?.[0].eta_s + 's');

feed.send({ cmd: 'alert_action', id: 'AL-FIRE-B-021', action: 'resolve' });
run(2);
console.log('after resolve:', alerts.get('AL-FIRE-B-021')?.status, '| hazard msgs', hazards);
console.log(process.exitCode ? 'CHECK FAILED' : 'ALL CHECKS PASSED');
