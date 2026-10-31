"""Deterministic risk engine: snapshot -> numeric GPS risk (numbers owner).

The LLM never computes numbers; it only renders the fixed values produced
here into prose (backend/llm.py). Thresholds live in this one file.

Location is applied here, not by copying the snapshot per city. Planetary
Kp is never relabeled as a local K. A geomagnetic-latitude band scales only
the Kp term. Local solar time drops the flare bonus on the night side.
"""
import math
from datetime import datetime, timezone

LEVELS = ("LOW", "MODERATE", "CRITICAL")

# Score weights (0-100 total, additive, clamped).
W_KP = 10          # per Kp point on the 0-9 scale (max ~90)
W_FLARE = {"M": 15, "X": 25}
W_CME_24H = 20     # Earth arrival within 24h
W_TEC_HIGH = 10    # local TEC >= TEC_HIGH_TECU
TEC_HIGH_TECU = 50

# Centered-dipole north pole, IGRF-13 approximation (degrees).
# https://www.ngdc.noaa.gov/geomag/geomag.shtml dipole axis, ~2020.
GEOMAG_POLE_LAT = 80.6
GEOMAG_POLE_LON = -72.6

# Share of the planetary Kp term kept in each |geomagnetic latitude| band.
# High latitudes keep the full term. Low latitudes differ mainly by TEC.
MLAT_HIGH = 55.0
MLAT_MID = 30.0
KP_FACTOR_HIGH = 1.0
KP_FACTOR_MID = 0.8
KP_FACTOR_LOW = 0.6

# Local solar hour is dayside on [06:00, 18:00).
DAYSIDE_START = 6.0
DAYSIDE_END = 18.0


def _flare_bonus(flares_worst):
    if not flares_worst:
        return 0
    return W_FLARE.get(str(flares_worst)[:1].upper(), 0)


def _cme_bonus(arrivals, now_iso=None):
    # Simplified: any predicted Earth arrival listed counts (conservative).
    return W_CME_24H if arrivals else 0


def geomagnetic_latitude(lat, lon):
    """Dipole geomagnetic latitude in degrees. Not a local K index."""
    lat_r = math.radians(float(lat))
    lon_r = math.radians(float(lon))
    plat = math.radians(GEOMAG_POLE_LAT)
    plon = math.radians(GEOMAG_POLE_LON)
    m = (math.sin(lat_r) * math.sin(plat)
         + math.cos(lat_r) * math.cos(plat) * math.cos(lon_r - plon))
    m = max(-1.0, min(1.0, m))
    return math.degrees(math.asin(m))


def latitude_band(lat, lon):
    """Return (band name, Kp-term factor, geomagnetic latitude)."""
    mlat = geomagnetic_latitude(lat, lon)
    am = abs(mlat)
    if am >= MLAT_HIGH:
        return "high", KP_FACTOR_HIGH, mlat
    if am >= MLAT_MID:
        return "mid", KP_FACTOR_MID, mlat
    return "low", KP_FACTOR_LOW, mlat


def local_solar_hour(fetched_at, lon):
    text = str(fetched_at).replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    return (utc + float(lon) / 15.0) % 24.0


def is_dayside(fetched_at, lon):
    """True when local solar time is in [06:00, 18:00). Missing clock stays dayside."""
    if not fetched_at or lon is None:
        return True
    try:
        hour = local_solar_hour(fetched_at, lon)
    except (TypeError, ValueError):
        return True
    return DAYSIDE_START <= hour < DAYSIDE_END


def score_for(kp=None, forecast_max_kp=None, worst_flare=None,
              cme_arrivals=None, tec_local=None, dayside=True, kp_factor=1.0):
    base_kp = max([v for v in (kp, forecast_max_kp) if v is not None], default=0) or 0
    flare = _flare_bonus(worst_flare) if dayside else 0
    s = base_kp * W_KP * kp_factor + flare + _cme_bonus(cme_arrivals or [])
    if tec_local is not None and tec_local >= TEC_HIGH_TECU:
        s += W_TEC_HIGH
    s = max(0, min(100, round(s)))
    level = "CRITICAL" if s >= 70 else ("MODERATE" if s >= 40 else "LOW")
    return {"score": s, "level": level}


def assess(snapshot, tec_local=None, lat=None, lon=None, dayside=None):
    now, fc, ev = snapshot.get("now", {}), snapshot.get("forecast_3d", {}), snapshot.get("events", {})
    if dayside is None:
        dayside = is_dayside(snapshot.get("fetched_at"), lon) if lon is not None else True
    band, factor, mlat = (None, 1.0, None)
    if lat is not None and lon is not None:
        band, factor, mlat = latitude_band(lat, lon)
    r = score_for(kp=now.get("kp"), forecast_max_kp=fc.get("max_kp"),
                  worst_flare=ev.get("worst_flare_7d"),
                  cme_arrivals=ev.get("cme_earth_arrivals"), tec_local=tec_local,
                  dayside=dayside, kp_factor=factor)
    r["inputs"] = {
        "kp": now.get("kp"), "kp_1m": now.get("kp_1m"),
        "forecast_max_kp": fc.get("max_kp"),
        "worst_flare_7d": ev.get("worst_flare_7d"),
        "sw_speed": now.get("sw_speed"), "bz_gsm": now.get("bz_gsm"),
        "tec_local": tec_local,
        "degraded": snapshot.get("degraded"),
        "lat": lat, "lon": lon, "dayside": dayside,
        "kp_factor": factor, "kp_band": band, "geomagnetic_lat": mlat,
    }
    r["advisory"] = advisory_text(r, snapshot)
    return r


def advisory_text(r, snapshot):
    parts = [f"GPS risk {r['level']} ({r['score']}/100)."]
    i = r["inputs"]
    if i["kp"] is not None:
        parts.append(f"Planetary Kp {i['kp']}.")
    if i.get("lat") is not None and i.get("lon") is not None:
        parts.append(
            f"Scored at {float(i['lat']):.2f}, {float(i['lon']):.2f} "
            f"({i.get('kp_band')} geomagnetic latitude, Kp term x{i.get('kp_factor')})."
        )
    if i.get("tec_local") is not None:
        parts.append(f"Local TEC {float(i['tec_local']):.0f} TECU.")
    if i.get("dayside") is False:
        parts.append("Night side at this longitude: flare bonus omitted.")
    if i.get("forecast_max_kp"):
        parts.append(f"3-day forecast max Kp {i['forecast_max_kp']}.")
    if i.get("worst_flare_7d"):
        parts.append(f"Strongest flare in 7d: {i['worst_flare_7d']}.")
    if snapshot.get("degraded"):
        parts.append("DEGRADED MODE: some feeds unavailable; SWPC baseline only.")
    if r["level"] == "CRITICAL":
        parts.append("Avoid precision-GPS-dependent routing; prefer inertial/map fallback.")
    elif r["level"] == "MODERATE":
        parts.append("Expect intermittent GPS degradation; keep HD map fallback ready.")
    else:
        parts.append("No significant GPS disruption expected.")
    return " ".join(parts)


def route_segments(snapshot, samples):
    """samples: [{label, lat, lon, tec}] -> per-segment scores (same assess())."""
    out = []
    for s in samples:
        r = assess(snapshot, tec_local=s.get("tec"), lat=s.get("lat"), lon=s.get("lon"))
        out.append({"label": s.get("label"), "lat": s.get("lat"), "lon": s.get("lon"),
                    "tec": s.get("tec"), "score": r["score"], "level": r["level"],
                    "advisory": r["advisory"]})
    return out
