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

export function scoreSnapshot(s: Snapshot): Risk {
  const kp = Math.max(s.now.kp ?? 0, s.forecast_3d.max_kp ?? 0);
  let score = kp * 10;
  const w = s.events.worst_flare_7d || "";
  if (w.startsWith("X")) score += 25; else if (w.startsWith("M")) score += 15;
  if ((s.events.cme_earth_arrivals || []).length) score += 20;
  score = Math.min(100, Math.round(score));
  const level = score >= 70 ? "CRITICAL" : score >= 40 ? "MODERATE" : "LOW";
  return { score, level, advisory: `GPS risk ${level} (${score}/100). Kp now ${s.now.kp}, forecast max ${s.forecast_3d.max_kp}.`, advisory_source: API ? "api" : "demo-local" };
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
