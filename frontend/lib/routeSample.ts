/**
 * Route samples for POST /route-score, evenly spaced by distance along the road.
 *
 * OSRM puts vertices densely in towns and on curves and sparsely on straight
 * highway, so picking every k-th vertex bunched samples near cities (Toronto
 * to Ottawa gaps ran 17 to 104 km). Samples here are interpolated at equal
 * distances along the polyline. The count follows the length: about one per
 * SAMPLE_SPACING_KM, at least MIN_SAMPLES (start and end), at most
 * MAX_SAMPLES (the server's limit).
 */
export const SAMPLE_SPACING_KM = 50;
export const MIN_SAMPLES = 2;
export const MAX_SAMPLES = 16;

export type SamplePoint = { lat: number; lon: number; label?: string };

const EARTH_KM = 6371;

/** Great-circle distance in km between two [lon, lat] points. */
export function haversineKm(a: [number, number], b: [number, number]): number {
  const rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad;
  const dLon = (b[0] - a[0]) * rad;
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** How many samples a route of this length gets. */
export function sampleCount(lengthKm: number): number {
  const n = Math.ceil(lengthKm / SAMPLE_SPACING_KM) + 1;
  return Math.max(MIN_SAMPLES, Math.min(MAX_SAMPLES, n));
}

/** coords are OSRM [lon, lat] pairs. Returns samples from start to end. */
export function sampleRoute(coords: [number, number][]): SamplePoint[] {
  if (!coords.length) return [];
  if (coords.length === 1) return [{ lat: coords[0][1], lon: coords[0][0], label: "s0" }];
  const cum = [0];
  for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + haversineKm(coords[i - 1], coords[i]));
  const total = cum[cum.length - 1];
  const n = sampleCount(total);
  const out: SamplePoint[] = [];
  let j = 0;
  for (let k = 0; k < n; k++) {
    const target = (total * k) / (n - 1);
    while (j < cum.length - 2 && cum[j + 1] < target) j++;
    const seg = cum[j + 1] - cum[j];
    const f = seg > 0 ? Math.min(1, Math.max(0, (target - cum[j]) / seg)) : 0;
    const [lon0, lat0] = coords[j];
    const [lon1, lat1] = coords[j + 1];
    out.push({ lat: lat0 + f * (lat1 - lat0), lon: lon0 + f * (lon1 - lon0), label: `s${k}` });
  }
  return out;
}
