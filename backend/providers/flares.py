"""GOES solar flare event reports: latest + 7-day list + current X-ray flux."""
from .base import frag, http_get_json

ID = "flares"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    return {
        "latest": http_get_json(f"{BASE}/json/goes/primary/xray-flares-latest.json"),
        "week": http_get_json(f"{BASE}/json/goes/primary/xray-flares-7-day.json"),
        "flux": http_get_json(f"{BASE}/json/goes/primary/xrays-6-hour.json"),
    }


def _cls_key(c):
    order = {"A": 0, "B": 1, "C": 2, "M": 3, "X": 4}
    try:
        return order[str(c)[0].upper()] * 10 + float(str(c)[1:])
    except (ValueError, IndexError, KeyError):
        return -1


def normalize(raw):
    latest, week = raw.get("latest") or [], raw.get("week") or []
    flux = raw.get("flux") or []
    mx = [f for f in week if str(f.get("max_class", "")).upper()[:1] in ("M", "X")]
    worst = max(week, key=lambda f: _cls_key(f.get("max_class", "")), default=None)
    f0 = flux[-1] if flux else {}
    return frag(
        latest_flare=(latest[0] if latest else None),
        flares_7d_count=len(week),
        mx_flares_7d=len(mx),
        worst_7d_class=(worst or {}).get("max_class"),
        xray_long=float(f0.get("xrlong", 0) or 0),
        xray_time=f0.get("time_tag"),
    )
