// Run: npm test  (node --test with TypeScript type stripping, no extra deps)
import assert from "node:assert/strict";
import test from "node:test";

import { MAX_SAMPLES, haversineKm, sampleCount, sampleRoute } from "./routeSample.ts";

// Points along the equator: 1 degree of longitude is about 111.2 km.
const eq = (lons) => lons.map((lon) => [lon, 0]);

test("sample count follows length, within 2..16", () => {
  assert.equal(sampleCount(0), 2);
  assert.equal(sampleCount(67), 3);    // Toronto-Hamilton
  assert.equal(sampleCount(450), 10);  // Toronto-Ottawa
  assert.equal(sampleCount(839), MAX_SAMPLES);  // Toronto-Chicago, capped
});

test("samples are equally spaced by distance, not by vertex index", () => {
  // Dense vertices in the first 0.1 degree (a "town"), then one long straight leg.
  const coords = eq([0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1, 4]);
  const s = sampleRoute(coords);
  const total = haversineKm(coords[0], coords[coords.length - 1]);
  assert.equal(s.length, sampleCount(total));
  const gaps = s.slice(1).map((p, i) => haversineKm([s[i].lon, s[i].lat], [p.lon, p.lat]));
  const want = total / (s.length - 1);
  for (const g of gaps) assert.ok(Math.abs(g - want) < 0.5, `gap ${g.toFixed(2)} vs ${want.toFixed(2)}`);
});

test("start and end are the route's own endpoints", () => {
  const coords = [[-79.38, 43.65], [-79.6, 43.5], [-79.87, 43.26]];
  const s = sampleRoute(coords);
  assert.deepEqual([s[0].lon, s[0].lat], coords[0]);
  const last = s[s.length - 1];
  assert.ok(Math.abs(last.lon - coords[2][0]) < 1e-9 && Math.abs(last.lat - coords[2][1]) < 1e-9);
  assert.deepEqual(s.map((p) => p.label), s.map((_, i) => `s${i}`));
});

test("degenerate routes", () => {
  assert.deepEqual(sampleRoute([]), []);
  assert.deepEqual(sampleRoute([[1, 2]]), [{ lat: 2, lon: 1, label: "s0" }]);
  const same = sampleRoute([[1, 2], [1, 2]]);  // zero length: start and end only
  assert.equal(same.length, 2);
});
