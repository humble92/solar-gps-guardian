"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import {
  DEMO_RISK, DEMO_SNAPSHOT, SIM_RISK, fetchLocalScore, fetchPlanetaryRisk, fetchRouteScore,
  fetchSnapshot, geocode, osrmRoute, reverseGeocode, sampleRoute, subscribe,
  type Risk, type Snapshot,
} from "@/lib/api";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

type ViewMode = "live" | "storm" | "route";

const TORONTO: [number, number] = [43.65, -79.38];
const TORONTO_ZOOM = 9;

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
  const [mode, setMode] = useState<ViewMode>("live");
  const [busy, setBusy] = useState(false);
  const [loc, setLoc] = useState<[number, number]>(TORONTO);
  const [locName, setLocName] = useState("Toronto (default)");
  const [from, setFrom] = useState("Toronto, ON");
  const [to, setTo] = useState("Hamilton, ON");
  const [route, setRoute] = useState<[number, number][] | undefined>();
  const [routeInfo, setRouteInfo] = useState("");
  const [email, setEmail] = useState("");
  const [region, setRegion] = useState("Toronto, ON");
  const [subMsg, setSubMsg] = useState("");
  const [err, setErr] = useState("");
  const [ready, setReady] = useState(false);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [routeLevel, setRouteLevel] = useState<string | undefined>();

  const shown = mode === "storm" ? SIM_STORM : snap;

  useEffect(() => {
    fetchSnapshot().then(({ snap, live }) => { setSnap(snap); setLive(live); setReady(true); })
      .catch((e) => { setErr(String(e)); setReady(true); });
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (p) => {
          const lat = p.coords.latitude;
          const lon = p.coords.longitude;
          setLoc([lat, lon]);
          setLocName("Your location");
          reverseGeocode(lat, lon)
            .then((name) => { if (name) setLocName(name); })
            .catch(() => {});
        },
        () => {}, { timeout: 8000 });
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (mode === "storm") { setRisk(SIM_RISK); return; }
    if (!live) { setRisk(DEMO_RISK); return; }
    let cancel = false;
    fetchLocalScore(loc[0], loc[1])
      .then(async (local) => {
        if (cancel) return;
        if (local) { setRisk(local); return; }
        const planetary = await fetchPlanetaryRisk();
        if (!cancel) setRisk(planetary);
      })
      .catch(() => { if (!cancel) setRisk(null); });
    return () => { cancel = true; };
  }, [ready, live, mode, loc, snap.fetched_at]);

  async function drawScoredRoute(prefix: string, stormCard: boolean, scenario?: "storm") {
    setRouteInfo(prefix + "Routing...");
    const a = await geocode(from); const b = await geocode(to);
    if (!a || !b) throw new Error("Place not found (Nominatim)");
    const r = await osrmRoute(a, b);
    setRoute(r.coords);
    const head = prefix + `${a.name.split(",")[0]} -> ${b.name.split(",")[0]}: ` +
      `${r.distanceKm.toFixed(1)} km, ~${Math.round(r.durationMin)} min. `;
    if (stormCard) {
      setRouteLevel("CRITICAL");
      setRouteInfo(head + "Simulation uses the storm card, not a sampled corridor.");
      return;
    }
    const scored = await fetchRouteScore(sampleRoute(r.coords), scenario);
    if (!scored || !scored.worst) {
      setRouteLevel(undefined);
      setRouteInfo(head + "Local route score unavailable.");
      return;
    }
    const scores = scored.segments.map((s) => s.score);
    const lo = Math.min(...scores);
    const hi = Math.max(...scores);
    const hypo = scenario === "storm"
      ? "Hypothetical superstorm on this corridor (Kp 9, flare X4.2, Earth-arrival CME). "
      : "";
    setRouteLevel(scored.worst.level);
    setRouteInfo(head + hypo +
      `GPS risk along corridor: ${scored.worst.level} (${scored.worst.score}/100), ` +
      `sampled ${scored.segments.length} points (${lo}-${hi}). ${scored.worst.advisory || ""}`);
  }

  async function planRoute() {
    setErr("");
    try {
      await drawScoredRoute("", mode === "storm");
    } catch (e) {
      setRoute(undefined);
      setRouteLevel(undefined);
      const banner = risk ? `${risk.level} (${risk.score}/100)` : "unavailable";
      setRouteInfo(`Routing failed (${String(e)}). No corridor samples. Position score: ${banner}.`);
    }
  }

  async function cycleView() {
    if (busy) return;
    if (mode === "live") {
      setLoc(TORONTO);
      setLocName("Toronto");
      setFrom("Toronto, ON");
      setTo("Hamilton, ON");
      setRoute(undefined);
      setRouteInfo("");
      setRouteLevel(undefined);
      setMode("storm");
      return;
    }
    if (mode === "storm") {
      setMode("route");
      setBusy(true);
      setErr("");
      try {
        await drawScoredRoute("Route risk simulation. ", false, "storm");
      } catch (e) {
        setRoute(undefined);
        setRouteLevel(undefined);
        const banner = risk ? `${risk.level} (${risk.score}/100)` : "unavailable";
        setRouteInfo(`Routing failed (${String(e)}). No corridor samples. Position score: ${banner}.`);
      } finally {
        setBusy(false);
      }
      return;
    }
    setMode("live");
    setRoute(undefined);
    setRouteInfo("");
    setRouteLevel(undefined);
  }

  async function doSubscribe() {
    setSubMsg("");
    try {
      const g = await geocode(region);
      const lat = g?.lat ?? loc[0]; const lon = g?.lon ?? loc[1];
      const res = await subscribe(email, lat, lon, region) as { demo?: boolean; id?: number };
      setSubMsg(res.demo
        ? "Demo mode: no backend configured, subscription NOT stored. Set NEXT_PUBLIC_API_BASE."
        : `Subscribed (id ${res.id}). Daily digest and critical alarms use this region's local score.`);
    } catch (e) { setSubMsg(`Subscribe failed: ${String(e)}`); }
  }

  return (
    <main>
      <h1>Solar-GPS-Guardian</h1>
      <div className="sub">Space-weather GPS hazard shield - live where configured, degraded-safe otherwise.</div>

      <div className={`banner ${risk?.level === "CRITICAL" ? "critical" : ""}`}>
        {risk ? (<>
          <span className={`badge ${risk.level}`}>{risk.level}</span>{" "}
          <strong>{risk.score}/100</strong> - {risk.advisory}{" "}
        </>) : <span>Scoring this position...</span>}{" "}
        <span className={`badge ${live ? "live" : "degraded"}`}>{mode === "storm" ? "SIMULATED STORM" : live ? "LIVE" : "DEMO DATA"}</span>{" "}
        {shown.degraded && mode !== "storm" && <span className="badge degraded">DEGRADED MODE</span>}
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
          <div className="muted">{loc[0].toFixed(3)}, {loc[1].toFixed(3)}
            {risk?.inputs?.tec_local != null
              ? ` - local TEC ${Number(risk.inputs.tec_local).toFixed(0)} TECU`
              : ` - TEC feed ${shown.tec.available ? "available" : "unavailable"}`}
            {risk?.inputs?.kp_band ? ` - ${String(risk.inputs.kp_band)} geomagnetic latitude` : ""}
          </div></div>
      </div>

      <section>
        <h2>Map</h2>
        <MapView center={loc} route={route} storm={mode === "storm"} routeLevel={routeLevel}
          zoom={mode === "storm" ? TORONTO_ZOOM : undefined}
          markers={[{ lat: loc[0], lon: loc[1], label: locName }]} />
      </section>

      <section>
        <h2>Route risk</h2>
        <div className="row">
          <input value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" />
          <input value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" />
          <button onClick={planRoute}>Assess route</button>
          <button className="ghost" onClick={cycleView} disabled={busy}>
            {mode === "live" ? "Simulate solar superstorm"
              : mode === "storm" ? "Simulate Route Risk"
              : "Back to Live"}</button>
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
        <p className="muted">Daily digest at 13:00 UTC, plus a critical alarm when the score at this region reaches CRITICAL. Both use that region's local score. Unsubscribe link in every mail.</p>
      </section>

      {err && <p className="err">{err}</p>}
      <p className="muted">Data: NOAA SWPC, NASA DONKI, Kyoto WDC, GFZ. Routing: OSRM. Map: OpenStreetMap/Leaflet.</p>
    </main>
  );
}
