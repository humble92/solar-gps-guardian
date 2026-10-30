"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import {
  DEMO_SNAPSHOT, fetchSnapshot, geocode, osrmRoute, scoreSnapshot, subscribe,
  type Risk, type Snapshot,
} from "@/lib/api";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

const SIM_STORM: Snapshot = {
  ...DEMO_SNAPSHOT, degraded: false,
  flags: { donki_available: true, tec_available: true, stale_sources: [] },
  now: { kp: 8.3, kp_1m: 8.0, sw_speed: 920, bz_gsm: -28, bt: 34, spacecraft: "SOLAR1 (simulated)" },
  forecast_3d: { max_kp: 9.0, storm_expected: true },
  events: { worst_flare_7d: "X4.2", cme_earth_arrivals: [{ arrival: "+18h" }] },
  tec: { available: true, tec_max: 120 },
};

export default function Home() {
  const [snap, setSnap] = useState<Snapshot>(DEMO_SNAPSHOT);
  const [live, setLive] = useState(false);
  const [sim, setSim] = useState(false);
  const [loc, setLoc] = useState<[number, number]>([43.65, -79.38]);
  const [locName, setLocName] = useState("Toronto (default)");
  const [from, setFrom] = useState("Toronto, ON");
  const [to, setTo] = useState("Hamilton, ON");
  const [route, setRoute] = useState<[number, number][] | undefined>();
  const [routeInfo, setRouteInfo] = useState("");
  const [email, setEmail] = useState("");
  const [region, setRegion] = useState("Toronto, ON");
  const [subMsg, setSubMsg] = useState("");
  const [err, setErr] = useState("");

  const shown = sim ? SIM_STORM : snap;
  const risk: Risk = useMemo(() => scoreSnapshot(shown), [shown]);

  useEffect(() => {
    fetchSnapshot().then(({ snap, live }) => { setSnap(snap); setLive(live); })
      .catch((e) => setErr(String(e)));
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (p) => { setLoc([p.coords.latitude, p.coords.longitude]); setLocName("Your location"); },
        () => {}, { timeout: 8000 });
    }
  }, []);

  async function planRoute() {
    setErr(""); setRouteInfo("Routing...");
    try {
      const a = await geocode(from); const b = await geocode(to);
      if (!a || !b) throw new Error("Place not found (Nominatim)");
      const r = await osrmRoute(a, b);
      setRoute(r.coords);
      const seg = scoreSnapshot(shown);
      setRouteInfo(`${a.name.split(",")[0]} -> ${b.name.split(",")[0]}: ` +
        `${r.distanceKm.toFixed(1)} km, ~${Math.round(r.durationMin)} min. ` +
        `GPS risk along corridor: ${seg.level} (${seg.score}/100). ${seg.advisory}`);
    } catch (e) {
      setRoute(undefined);
      setRouteInfo(`Routing failed (${String(e)}). Straight-line corridor fallback: ` +
        `risk ${risk.level} (${risk.score}/100).`);
    }
  }

  async function doSubscribe() {
    setSubMsg("");
    try {
      const g = await geocode(region);
      const lat = g?.lat ?? loc[0]; const lon = g?.lon ?? loc[1];
      const res = await subscribe(email, lat, lon, region) as { demo?: boolean; id?: number };
      setSubMsg(res.demo
        ? "Demo mode: no backend configured, subscription NOT stored. Set NEXT_PUBLIC_API_BASE."
        : `Subscribed (id ${res.id}). Daily digest + storm alerts enabled.`);
    } catch (e) { setSubMsg(`Subscribe failed: ${String(e)}`); }
  }

  return (
    <main>
      <h1>Solar-GPS-Guardian</h1>
      <div className="sub">Space-weather GPS hazard shield - live where configured, degraded-safe otherwise.</div>

      <div className={`banner ${risk.level === "CRITICAL" ? "critical" : ""}`}>
        <span className={`badge ${risk.level}`}>{risk.level}</span>{" "}
        <strong>{risk.score}/100</strong> - {risk.advisory}{" "}
        <span className={`badge ${live ? "live" : "degraded"}`}>{sim ? "SIMULATED STORM" : live ? "LIVE" : "DEMO DATA"}</span>{" "}
        {shown.degraded && !sim && <span className="badge degraded">DEGRADED MODE</span>}
      </div>

      <div className="grid">
        <div className="card"><h3>Now - {shown.now.spacecraft || "L1"}</h3>
          <div className="big">Kp {shown.now.kp ?? "-"}</div>
          <div className="muted">wind {shown.now.sw_speed ?? "-"} km/s - Bz {shown.now.bz_gsm ?? "-"} nT</div></div>
        <div className="card"><h3>3-day forecast</h3>
          <div className="big">max Kp {shown.forecast_3d.max_kp ?? "-"}</div>
          <div className="muted">{shown.forecast_3d.storm_expected ? "Storm expected" : "No storm expected"}</div></div>
        <div className="card"><h3>Strongest flare (7d)</h3>
          <div className="big">{shown.events.worst_flare_7d || "-"}</div>
          <div className="muted">M/X flares: {shown.events.mx_flares_7d ?? 0}</div></div>
        <div className="card"><h3>Your position</h3>
          <div className="big" style={{ fontSize: 20 }}>{locName}</div>
          <div className="muted">{loc[0].toFixed(3)}, {loc[1].toFixed(3)} - TEC feed {shown.tec.available ? "available" : "unavailable"}</div></div>
      </div>

      <section>
        <h2>Map</h2>
        <MapView center={loc} route={route} storm={sim}
          markers={[{ lat: loc[0], lon: loc[1], label: locName }]} />
      </section>

      <section>
        <h2>Route risk</h2>
        <div className="row">
          <input value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" />
          <input value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" />
          <button onClick={planRoute}>Assess route</button>
          <button className="ghost" onClick={() => setSim(!sim)}>
            {sim ? "Back to live" : "Simulate solar superstorm"}</button>
        </div>
        {routeInfo && <p className="muted">{routeInfo}</p>}
      </section>

      <section>
        <h2>Solar wind alerts (email + region, no account)</h2>
        <div className="row">
          <input type="email" placeholder="you@example.com" value={email}
            onChange={(e) => setEmail(e.target.value)} aria-label="Email" />
          <input value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region" />
          <button onClick={doSubscribe}>Subscribe</button>
        </div>
        {subMsg && <p className={subMsg.includes("NOT") || subMsg.includes("failed") ? "err" : "ok"}>{subMsg}</p>}
        <p className="muted">Daily digest + extra sends on G/R storm triggers. Unsubscribe link in every mail.</p>
      </section>

      {err && <p className="err">{err}</p>}
      <p className="muted">Data: NOAA SWPC, NASA DONKI, Kyoto WDC, GFZ. Routing: OSRM. Map: OpenStreetMap/Leaflet.</p>
    </main>
  );
}
