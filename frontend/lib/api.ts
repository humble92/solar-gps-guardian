export type Snapshot = {
  snapshot_version: number;
  fetched_at: string;
  degraded: boolean;
  flags: { donki_available: boolean; tec_available: boolean; stale_sources: string[] };
  now: { kp: number | null; kp_1m: number | null; sw_speed: number | null;
         bz_gsm: number | null; bt: number | null; spacecraft: string | null;
         g_scale?: { Scale?: string } };
  forecast_3d: { max_kp: number | null; storm_expected?: boolean };
  events: { worst_flare_7d: string | null; mx_flares_7d?: number;
            cme_earth_arrivals?: { arrival?: string }[] };
  tec: { available: boolean; latest_time?: string; tec_max?: number | null };
};

export type Risk = {
  score: number; level: "LOW" | "MODERATE" | "CRITICAL";
  advisory: string; advisory_source?: string;
  inputs?: Record<string, unknown>;
};

export type RoutePoint = { lat: number; lon: number; label?: string };

export type RouteSegment = RoutePoint & {
  tec: number | null; score: number; level: Risk["level"]; advisory?: string;
};

export type RouteScore = { segments: RouteSegment[]; worst: RouteSegment | null };

const API = process.env.NEXT_PUBLIC_API_BASE || "";

/** Demo snapshot used when no backend is configured (clearly labeled in UI). */
export const DEMO_SNAPSHOT: Snapshot = {
  snapshot_version: 1, fetched_at: "demo", degraded: true,
  flags: { donki_available: false, tec_available: false, stale_sources: ["demo"] },
  now: { kp: 2.0, kp_1m: 0.0, sw_speed: 378, bz_gsm: 4.8, bt: 6.1, spacecraft: "SOLAR1" },
  forecast_3d: { max_kp: 3.0 },
  events: { worst_flare_7d: "C3.5", cme_earth_arrivals: [] },
  tec: { available: false },
};

/** Fixed label for the canned demo snapshot above. Live scores come from /local-score. */
export const DEMO_RISK: Risk = {
  score: 30, level: "LOW", advisory_source: "demo",
  advisory: "GPS risk LOW (30/100). Demo snapshot (planetary Kp 2, forecast max 3). Set NEXT_PUBLIC_API_BASE for a local score.",
};

/** Fixed label for the simulate toggle. The server does not see this card. */
export const SIM_RISK: Risk = {
  score: 100, level: "CRITICAL", advisory_source: "simulated",
  advisory: "GPS risk CRITICAL (100/100). Simulated superstorm: planetary Kp 8.3, forecast max 9, flare X4.2, Earth-arrival CME. This card is not a local score.",
};

function asRisk(j: unknown): Risk | null {
  if (!j || typeof j !== "object") return null;
  const o = j as Risk;
  if (typeof o.score !== "number" || (o.level !== "LOW" && o.level !== "MODERATE" && o.level !== "CRITICAL")) {
    return null;
  }
  return o;
}

export async function fetchLocalScore(lat: number, lon: number): Promise<Risk | null> {
  if (!API) return null;
  const r = await fetch(`${API}/local-score?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
  if (!r.ok) return null;
  return asRisk(await r.json());
}

export async function fetchPlanetaryRisk(): Promise<Risk | null> {
  if (!API) return null;
  const r = await fetch(`${API}/risk`);
  if (!r.ok) return null;
  return asRisk(await r.json());
}

export function sampleRoute(coords: [number, number][], n = 8): RoutePoint[] {
  if (!coords.length) return [];
  const count = Math.min(n, coords.length);
  const out: RoutePoint[] = [];
  for (let i = 0; i < count; i++) {
    const idx = count === 1 ? 0 : Math.round((i * (coords.length - 1)) / (count - 1));
    const [lon, lat] = coords[idx];
    out.push({ lat, lon, label: `s${i}` });
  }
  return out;
}

export async function fetchRouteScore(points: RoutePoint[], scenario?: "storm"): Promise<RouteScore | null> {
  if (!API) return null;
  const r = await fetch(`${API}/route-score`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(scenario ? { points, scenario } : { points }),
  });
  if (!r.ok) return null;
  const j = await r.json();
  if (!j || !Array.isArray(j.segments)) return null;
  return j as RouteScore;
}

export async function fetchSnapshot(): Promise<{ snap: Snapshot; live: boolean }> {
  if (!API) return { snap: DEMO_SNAPSHOT, live: false };
  const r = await fetch(`${API}/snapshot`);
  if (!r.ok) throw new Error(`snapshot ${r.status}`);
  return { snap: await r.json(), live: true };
}

/** Nearest city, town, or village for a browser position. Null if lookup fails. */
export async function reverseGeocode(lat: number, lon: number): Promise<string | null> {
  const r = await fetch(
    "https://nominatim.openstreetmap.org/reverse?format=json&addressdetails=1&zoom=10" +
    `&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
    { headers: { "User-Agent": "SolarGPSGuardian/1.0" } });
  if (!r.ok) return null;
  const j = await r.json();
  const a = j.address || {};
  const name = a.city || a.town || a.village || a.municipality || a.hamlet;
  return typeof name === "string" && name ? name : null;
}

export async function geocode(q: string): Promise<{ lat: number; lon: number; name: string } | null> {
  const r = await fetch(
    `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`,
    { headers: { "User-Agent": "SolarGPSGuardian/1.0" } });
  const j = await r.json();
  if (!j.length) return null;
  return { lat: parseFloat(j[0].lat), lon: parseFloat(j[0].lon), name: j[0].display_name };
}

export async function osrmRoute(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const r = await fetch(
    `https://router.project-osrm.org/route/v1/driving/${a.lon},${a.lat};${b.lon},${b.lat}?overview=full&geometries=geojson`);
  const j = await r.json();
  if (j.code !== "Ok") throw new Error("OSRM failed");
  const route = j.routes[0];
  return { coords: route.geometry.coordinates as [number, number][],
           distanceKm: route.distance / 1000, durationMin: route.duration / 60 };
}

export async function subscribe(email: string, lat: number, lon: number, region: string) {
  if (!API) return { demo: true };
  const r = await fetch(`${API}/subscribe`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, lat, lon, region_name: region, radius_km: 100 }),
  });
  if (!r.ok) throw new Error(`subscribe ${r.status}`);
  return r.json();
}
