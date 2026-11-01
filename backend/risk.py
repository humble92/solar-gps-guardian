"""Deterministic risk engine: snapshot -> numeric GPS risk (numbers owner).

The LLM never computes numbers; it only renders the fixed values produced
here into prose (backend/llm.py). Thresholds live in this one file.

The Kp term uses the largest of SWPC Kp, the SWPC 3-day forecast maximum,
and the GFZ Kp nowcast (cross-check, conservative on mismatch).

Location is applied here, not by copying the snapshot per city. Planetary
Kp is never relabeled as a local K. A geomagnetic-latitude band scales only
the Kp term; its high band reaches farther toward the equator as Kp rises,
because the auroral zone does, and also covers any place OVATION puts under
the auroral oval right now (night-side substorms included). The flare term is the GOES X-ray flux at
snapshot time: a flare's X-rays disturb only the sunlit ionosphere, and only
while the flare lasts, so local solar time drops it on the night side.
"""
import math
from datetime import datetime, timezone

LEVELS = ("LOW", "MODERATE", "CRITICAL")

# Score weights (0-100 total, additive, clamped).
W_KP = 10          # per Kp point on the 0-9 scale (max ~90)
# SWPC Kp and the GFZ Kp nowcast are cross-checked: the larger one is scored
# (conservative), and a gap of this size is named in the sentence.
KP_SOURCE_GAP = 1.0
W_FLARE = {"M": 15, "X": 25}  # flare in progress, by GOES X-ray class
# GOES 0.1-0.8 nm flux class floors (W/m^2).
XRAY_CLASS = (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8))
W_CME = 20         # Earth shock arrival predicted in the window below
# A predicted CME arrival counts from 72 h ahead (the 3-day forecast horizon)
# until 24 h after it, while the storm it drives is under way.
CME_AHEAD_H = 72
CME_AFTER_H = 24
# Large-delay level, not a storm detector: vertical TEC of the nearest GloTEC
# cell. 1 TECU is about 0.16 m of L1 delay, so 50 TECU is about 8 m straight
# up and more on low-elevation paths; a single-frequency receiver's broadcast
# model removes only part of it. Low latitudes pass 50 on many afternoons
# near solar maximum; the storm signal is the anomaly term below.
W_TEC_HIGH = 10    # local TEC >= TEC_HIGH_TECU
TEC_HIGH_TECU = 50
# Storm-time disturbance: local TEC far from its 30-day median (GloTEC
# anomaly, observed cells only). 10 TECU is about 1.6 m of L1 delay that a
# receiver's model does not expect.
W_TEC_ANOMALY = 10
TEC_ANOMALY_TECU = 10.0
# GloTEC tiles appear ~1.3 h after their time tag. Older than this, the TEC
# and TEC-deviation terms are skipped rather than scored on a stale sky.
TEC_MAX_AGE_H = 3.0

# Centered-dipole north pole, IGRF-13 approximation (degrees).
# https://www.ngdc.noaa.gov/geomag/geomag.shtml dipole axis, ~2020.
GEOMAG_POLE_LAT = 80.6
GEOMAG_POLE_LON = -72.6

# Share of the planetary Kp term kept in each |geomagnetic latitude| band.
# The high band covers the auroral zone and the polar cap. Low latitudes
# differ mainly by TEC.
MLAT_HIGH = 55.0
MLAT_MID = 30.0
# The auroral zone's equatorward edge moves toward the equator as Kp rises.
# Rough linear fit (about 66 deg at Kp 0, about 50 deg at Kp 9). The high
# band starts at min(MLAT_HIGH, edge), so it only widens in strong storms
# (Kp above ~6.1).
AURORA_EDGE_KP0 = 66.0
AURORA_EDGE_PER_KP = 1.8
# OVATION aurora value (0..100) at or above which a place is under the oval.
OVATION_OVAL_MIN = 10
KP_FACTOR_HIGH = 1.0
KP_FACTOR_MID = 0.8
KP_FACTOR_LOW = 0.6

# Local solar hour is dayside on [06:00, 18:00).
DAYSIDE_START = 6.0
DAYSIDE_END = 18.0


def xray_class(flux):
    """GOES long-band flux (W/m^2) -> class label such as 'M2.3'. None if unknown."""
    if flux is None or flux <= 0:
        return None
    for letter, floor in XRAY_CLASS:
        if flux >= floor:
            return f"{letter}{flux / floor:.1f}"
    return f"A{flux / 1e-8:.1f}"


def _flare_bonus(xray_flux):
    label = xray_class(xray_flux)
    return W_FLARE.get(label[:1], 0) if label else 0


def _parse_utc(text):
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def cme_in_window(arrival, now_iso):
    """True when a predicted Earth arrival is within [-CME_AFTER_H, +CME_AHEAD_H]
    of now. An arrival or clock that cannot be read counts (conservative)."""
    t, now = _parse_utc((arrival or {}).get("arrival")), _parse_utc(now_iso)
    if t is None or now is None:
        return True
    hours = (t - now).total_seconds() / 3600
    return -CME_AFTER_H <= hours <= CME_AHEAD_H


def _cme_bonus(arrivals, now_iso=None):
    return W_CME if any(cme_in_window(a, now_iso) for a in arrivals) else 0


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


def high_band_start(kp=None):
    """|Geomagnetic latitude| where the full Kp term starts, for this Kp."""
    if kp is None:
        return MLAT_HIGH
    return min(MLAT_HIGH, AURORA_EDGE_KP0 - AURORA_EDGE_PER_KP * float(kp))


def under_oval(aurora):
    return aurora is not None and aurora >= OVATION_OVAL_MIN


def latitude_band(lat, lon, kp=None, aurora=None):
    """Return (band name, Kp-term factor, geomagnetic latitude)."""
    mlat = geomagnetic_latitude(lat, lon)
    am = abs(mlat)
    if am >= high_band_start(kp) or under_oval(aurora):
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


def _base_kp(kp, forecast_max_kp, gfz_kp=None):
    return max([v for v in (kp, forecast_max_kp, gfz_kp) if v is not None], default=0) or 0


def gfz_kp_of(snapshot):
    """GFZ Kp nowcast from the snapshot, or None when that feed failed."""
    g = (snapshot or {}).get("kp_gfz") or {}
    return g.get("kp") if g.get("ok", True) and isinstance(g.get("kp"), (int, float)) else None


def score_for(kp=None, forecast_max_kp=None, xray_flux=None,
              cme_arrivals=None, tec_local=None, dayside=True, kp_factor=1.0,
              tec_anomaly=None, now_iso=None, gfz_kp=None):
    base_kp = _base_kp(kp, forecast_max_kp, gfz_kp)
    flare = _flare_bonus(xray_flux) if dayside else 0
    s = base_kp * W_KP * kp_factor + flare + _cme_bonus(cme_arrivals or [], now_iso)
    if tec_local is not None and tec_local >= TEC_HIGH_TECU:
        s += W_TEC_HIGH
    if tec_anomaly is not None and abs(tec_anomaly) >= TEC_ANOMALY_TECU:
        s += W_TEC_ANOMALY
    s = max(0, min(100, round(s)))
    level = "CRITICAL" if s >= 70 else ("MODERATE" if s >= 40 else "LOW")
    return {"score": s, "level": level}


def assess(snapshot, tec_local=None, lat=None, lon=None, dayside=None,
           tec_anomaly=None, aurora=None, tec_time=None, tec_age_h=None):
    now, fc, ev = snapshot.get("now", {}), snapshot.get("forecast_3d", {}), snapshot.get("events", {})
    if dayside is None:
        dayside = is_dayside(snapshot.get("fetched_at"), lon) if lon is not None else True
    gfz = gfz_kp_of(snapshot)
    base_kp = _base_kp(now.get("kp"), fc.get("max_kp"), gfz)
    band, factor, mlat = (None, 1.0, None)
    if lat is not None and lon is not None:
        band, factor, mlat = latitude_band(lat, lon, base_kp, aurora)
    r = score_for(kp=now.get("kp"), forecast_max_kp=fc.get("max_kp"),
                  xray_flux=ev.get("xray_flux"),
                  cme_arrivals=ev.get("cme_earth_arrivals"), tec_local=tec_local,
                  dayside=dayside, kp_factor=factor, tec_anomaly=tec_anomaly,
                  now_iso=snapshot.get("fetched_at"), gfz_kp=gfz)
    r["inputs"] = {
        "kp": now.get("kp"), "kp_1m": now.get("kp_1m"), "kp_gfz": gfz, "kp_scored": base_kp,
        "forecast_max_kp": fc.get("max_kp"),
        "xray_flux": ev.get("xray_flux"), "xray_class": xray_class(ev.get("xray_flux")),
        "worst_flare_7d": ev.get("worst_flare_7d"),
        "sw_speed": now.get("sw_speed"), "bz_gsm": now.get("bz_gsm"),
        "tec_local": tec_local, "tec_anomaly": tec_anomaly, "aurora_local": aurora,
        "tec_time": tec_time, "tec_age_h": tec_age_h,
        "degraded": snapshot.get("degraded"),
        "lat": lat, "lon": lon, "dayside": dayside,
        "kp_factor": factor, "kp_band": band, "geomagnetic_lat": mlat,
        "high_band_start": high_band_start(base_kp),
        "cme_arrival": next((a.get("arrival") for a in ev.get("cme_earth_arrivals") or []
                             if cme_in_window(a, snapshot.get("fetched_at"))), None),
    }
    r["advisory"] = advisory_text(r, snapshot)
    return r


def _tec_age_text(tec_time, age_h):
    if not tec_time and age_h is None:
        return ""
    clock = str(tec_time)[11:16] + " UTC" if tec_time else "time unknown"
    old = f", {age_h:.1f} h old" if age_h is not None else ""
    return f" (GloTEC {clock}{old})"


def advisory_text(r, snapshot):
    parts = [f"GPS risk {r['level']} ({r['score']}/100)."]
    i = r["inputs"]
    if i["kp"] is not None:
        parts.append(f"Planetary Kp {i['kp']}.")
    if i.get("kp_gfz") is not None and (i["kp"] is None or abs(i["kp_gfz"] - i["kp"]) >= KP_SOURCE_GAP):
        parts.append(f"Kp sources differ (GFZ {i['kp_gfz']}, SWPC {i['kp']}); the larger is scored.")
    if i.get("lat") is not None and i.get("lon") is not None:
        parts.append(
            f"Scored at {float(i['lat']):.2f}, {float(i['lon']):.2f} "
            f"({i.get('kp_band')} geomagnetic latitude, Kp term x{i.get('kp_factor')})."
        )
    age = _tec_age_text(i.get("tec_time"), i.get("tec_age_h"))
    if i.get("tec_local") is not None:
        parts.append(f"Local TEC {float(i['tec_local']):.0f} TECU{age}.")
    elif i.get("tec_time") or i.get("tec_age_h") is not None:
        parts.append(f"TEC terms skipped: grid older than {TEC_MAX_AGE_H:g} h{age}.")
    if i.get("tec_anomaly") is not None and abs(i["tec_anomaly"]) >= TEC_ANOMALY_TECU:
        parts.append(f"Local TEC {float(i['tec_anomaly']):+.0f} TECU from its 30-day median.")
    if under_oval(i.get("aurora_local")):
        parts.append(f"Under the auroral oval now (OVATION {i['aurora_local']}).")
    if i.get("xray_class"):
        parts.append(f"X-ray flux now: {i['xray_class']}.")
    if i.get("dayside") is False and _flare_bonus(i.get("xray_flux")):
        parts.append("Night side at this longitude: flare bonus omitted.")
    if i.get("cme_arrival"):
        parts.append(f"CME predicted at Earth {i['cme_arrival']}.")
    if i.get("forecast_max_kp"):
        parts.append(f"3-day forecast max Kp {i['forecast_max_kp']}.")
    if i.get("worst_flare_7d"):
        parts.append(f"Strongest flare in 7d: {i['worst_flare_7d']} (not scored).")
    if snapshot.get("degraded"):
        flags = snapshot.get("flags") or {}
        missing = [name for name, key in (("DONKI", "donki_available"), ("GloTEC", "tec_available"))
                   if not flags.get(key)] or ["a feed"]
        parts.append(f"DEGRADED MODE: {' and '.join(missing)} missing in this snapshot; "
                     "scored with the feeds that answered.")
    if r["level"] == "CRITICAL":
        parts.append("Avoid precision-GPS-dependent routing; prefer inertial/map fallback.")
    elif r["level"] == "MODERATE":
        parts.append("Expect intermittent GPS degradation; keep HD map fallback ready.")
    else:
        parts.append("No significant GPS disruption expected.")
    return " ".join(parts)


def route_segments(snapshot, samples):
    """samples: [{label, lat, lon, tec, tec_anomaly, aurora}] -> per-segment scores."""
    out = []
    for s in samples:
        r = assess(snapshot, tec_local=s.get("tec"), lat=s.get("lat"), lon=s.get("lon"),
                   tec_anomaly=s.get("tec_anomaly"), aurora=s.get("aurora"),
                   tec_time=s.get("tec_time"), tec_age_h=s.get("tec_age_h"))
        out.append({"label": s.get("label"), "lat": s.get("lat"), "lon": s.get("lon"),
                    "tec": s.get("tec"), "tec_anomaly": s.get("tec_anomaly"),
                    "aurora": s.get("aurora"), "score": r["score"], "level": r["level"],
                    "advisory": r["advisory"]})
    return out
