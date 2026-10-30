"""Deterministic risk engine: snapshot -> numeric GPS risk (numbers owner).

The LLM never computes numbers; it only renders the fixed values produced
here into prose (backend/llm.py). Thresholds live in this one file.
"""
LEVELS = ("LOW", "MODERATE", "CRITICAL")

# Score weights (0-100 total, additive, clamped).
W_KP = 10          # per Kp point on the 0-9 scale (max ~90)
W_FLARE = {"M": 15, "X": 25}
W_CME_24H = 20     # Earth arrival within 24h
W_TEC_HIGH = 10    # local TEC >= TEC_HIGH_TECU
TEC_HIGH_TECU = 50


def _flare_bonus(flares_worst):
    if not flares_worst:
        return 0
    return W_FLARE.get(str(flares_worst)[:1].upper(), 0)


def _cme_bonus(arrivals, now_iso=None):
    # Simplified: any predicted Earth arrival listed counts (conservative).
    return W_CME_24H if arrivals else 0


def score_for(kp=None, forecast_max_kp=None, worst_flare=None,
              cme_arrivals=None, tec_local=None):
    base_kp = max([v for v in (kp, forecast_max_kp) if v is not None], default=0) or 0
    s = base_kp * W_KP + _flare_bonus(worst_flare) + _cme_bonus(cme_arrivals or [])
    if tec_local is not None and tec_local >= TEC_HIGH_TECU:
        s += W_TEC_HIGH
    s = max(0, min(100, round(s)))
    level = "CRITICAL" if s >= 70 else ("MODERATE" if s >= 40 else "LOW")
    return {"score": s, "level": level}


def assess(snapshot, tec_local=None):
    now, fc, ev = snapshot.get("now", {}), snapshot.get("forecast_3d", {}), snapshot.get("events", {})
    r = score_for(kp=now.get("kp"), forecast_max_kp=fc.get("max_kp"),
                  worst_flare=ev.get("worst_flare_7d"),
                  cme_arrivals=ev.get("cme_earth_arrivals"), tec_local=tec_local)
    r["inputs"] = {
        "kp": now.get("kp"), "kp_1m": now.get("kp_1m"),
        "forecast_max_kp": fc.get("max_kp"),
        "worst_flare_7d": ev.get("worst_flare_7d"),
        "sw_speed": now.get("sw_speed"), "bz_gsm": now.get("bz_gsm"),
        "tec_local": tec_local,
        "degraded": snapshot.get("degraded"),
    }
    r["advisory"] = advisory_text(r, snapshot)
    return r


def advisory_text(r, snapshot):
    parts = [f"GPS risk {r['level']} ({r['score']}/100)."]
    i = r["inputs"]
    if i["kp"] is not None:
        parts.append(f"Current Kp {i['kp']}.")
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
    """samples: [{label, lat, lon, tec}] -> per-segment scores (same rules)."""
    out = []
    for s in samples:
        r = score_for(kp=snapshot.get("now", {}).get("kp"),
                      forecast_max_kp=snapshot.get("forecast_3d", {}).get("max_kp"),
                      worst_flare=snapshot.get("events", {}).get("worst_flare_7d"),
                      cme_arrivals=snapshot.get("events", {}).get("cme_earth_arrivals"),
                      tec_local=s.get("tec"))
        out.append({"label": s.get("label"), "lat": s.get("lat"), "lon": s.get("lon"),
                    "tec": s.get("tec"), "score": r["score"], "level": r["level"]})
    return out
