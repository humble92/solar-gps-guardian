"""Request-time local score shared by the banner, the route, and mail.

The planetary snapshot stays one row. This module looks up TEC (skipped when
the grid is older than risk.TEC_MAX_AGE_H) and the OVATION aurora value at
the caller's coordinates and calls risk.assess. It does not invent a local Kp.
"""
from datetime import datetime, timezone

from .providers.ovation import aurora_at
from .providers.tec import nearest_anomaly, nearest_value
from .risk import TEC_MAX_AGE_H, assess, route_segments

# Same fixed card as the superstorm view. Kp is still the planetary index.
STORM_NOW = {"kp": 8.3, "kp_1m": 8.0, "sw_speed": 920, "bz_gsm": -28, "bt": 34,
             "spacecraft": "SOLAR1 (simulated)"}
STORM_FORECAST = {"max_kp": 9.0, "storm_expected": True}
STORM_EVENTS = {"xray_flux": 4.2e-4, "worst_flare_7d": "X4.2",
                "cme_earth_arrivals": [{"arrival": "+18h"}]}  # X4.2 flare in progress


def storm_snapshot(snapshot):
    """Hypothetical superstorm on top of the live clock. TEC lookup stays outside."""
    base = dict(snapshot or {})
    base["now"] = dict(STORM_NOW)
    base["forecast_3d"] = dict(STORM_FORECAST)
    base["events"] = dict(STORM_EVENTS)
    base["degraded"] = False
    return base


def _when(text):
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def tec_grid_age(grid, now_iso):
    """(cells, tile time, age in hours). A bare cell list (stored before tile
    times were kept) has no time and no age."""
    if isinstance(grid, dict):
        cells, tag = grid.get("cells") or [], grid.get("time_tag")
    else:
        cells, tag = grid or [], None
    t, now = _when(tag), _when(now_iso)
    age = round((now - t).total_seconds() / 3600, 1) if t and now else None
    return cells, tag, age


def _local(grid, aurora, lat, lon, now_iso=None):
    cells, tag, age = tec_grid_age(grid, now_iso)
    fresh = bool(cells) and age is not None and age <= TEC_MAX_AGE_H
    return {"tec": nearest_value(cells, lon, lat) if fresh else None,
            "tec_anomaly": nearest_anomaly(cells, lon, lat) if fresh else None,
            "tec_time": tag if cells else None, "tec_age_h": age if cells else None,
            "aurora": aurora_at(aurora, lat, lon) if aurora else None}


def score_point(snapshot, lat, lon, grid=None, aurora=None):
    loc = _local(grid, aurora, lat, lon, (snapshot or {}).get("fetched_at"))
    return assess(snapshot, tec_local=loc["tec"], lat=lat, lon=lon,
                  tec_anomaly=loc["tec_anomaly"], aurora=loc["aurora"],
                  tec_time=loc["tec_time"], tec_age_h=loc["tec_age_h"])


def score_route(snapshot, points, grid=None, limit=16, scenario=None, aurora=None):
    scored = storm_snapshot(snapshot) if scenario == "storm" else snapshot
    samples = []
    for p in list(points)[:limit]:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        samples.append({"label": p.get("label"), "lat": lat, "lon": lon,
                        **_local(grid, aurora, lat, lon, scored.get("fetched_at"))})
    segs = route_segments(scored, samples)
    worst = max(segs, key=lambda s: s["score"]) if segs else None
    return {"scenario": "storm" if scenario == "storm" else "live",
            "segments": segs, "worst": worst}
