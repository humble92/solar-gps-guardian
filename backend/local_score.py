"""Request-time local score shared by the banner, the route, and mail.

The planetary snapshot stays one row. This module looks up TEC at the
caller's coordinates and calls risk.assess. It does not invent a local Kp.
"""
from .providers.tec import nearest_value
from .risk import assess, route_segments

# Same fixed card as the superstorm view. Kp is still the planetary index.
STORM_NOW = {"kp": 8.3, "kp_1m": 8.0, "sw_speed": 920, "bz_gsm": -28, "bt": 34,
             "spacecraft": "SOLAR1 (simulated)"}
STORM_FORECAST = {"max_kp": 9.0, "storm_expected": True}
STORM_EVENTS = {"worst_flare_7d": "X4.2", "cme_earth_arrivals": [{"arrival": "+18h"}]}


def storm_snapshot(snapshot):
    """Hypothetical superstorm on top of the live clock. TEC lookup stays outside."""
    base = dict(snapshot or {})
    base["now"] = dict(STORM_NOW)
    base["forecast_3d"] = dict(STORM_FORECAST)
    base["events"] = dict(STORM_EVENTS)
    base["degraded"] = False
    return base


def score_point(snapshot, lat, lon, grid=None):
    tec = nearest_value(grid, lon, lat) if grid else None
    return assess(snapshot, tec_local=tec, lat=lat, lon=lon)


def score_route(snapshot, points, grid=None, limit=16, scenario=None):
    scored = storm_snapshot(snapshot) if scenario == "storm" else snapshot
    samples = []
    for p in list(points)[:limit]:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        tec = nearest_value(grid, lon, lat) if grid else None
        samples.append({"label": p.get("label"), "lat": lat, "lon": lon, "tec": tec})
    segs = route_segments(scored, samples)
    worst = max(segs, key=lambda s: s["score"]) if segs else None
    return {"scenario": "storm" if scenario == "storm" else "live",
            "segments": segs, "worst": worst}
