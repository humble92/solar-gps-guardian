"""GOES solar flare event reports: latest + 7-day list + current X-ray flux."""
from .base import frag, http_get_json

ID = "flares"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    return {
        "latest": http_get_json(f"{BASE}/json/goes/primary/xray-flares-latest.json"),
        "week": http_get_json(f"{BASE}/json/goes/primary/xray-flares-7-day.json"),
        "flux": http_get_json(f"{BASE}/json/goes/primary/xrays-6-hour.json"),
        # Primary GOES sometimes reports 0.0 for hours (seen 2026-10-31,
        # GOES-18); the secondary satellite fills that gap.
        "flux_secondary": _optional(f"{BASE}/json/goes/secondary/xrays-6-hour.json"),
    }


def _optional(url):
    try:
        return http_get_json(url)
    except Exception:  # noqa: BLE001 - the primary feed is still usable
        return []


def _cls_key(c):
    order = {"A": 0, "B": 1, "C": 2, "M": 3, "X": 4}
    try:
        return order[str(c)[0].upper()] * 10 + float(str(c)[1:])
    except (ValueError, IndexError, KeyError):
        return -1


def _latest_long_band(rows):
    """Newest 0.1-0.8 nm sample (GOES classes use the long band), or None.

    A flux of 0 is a data gap, not a quiet Sun, so a feed whose newest
    sample is 0 does not count.
    """
    long_band = [r for r in rows if r.get("energy") == "0.1-0.8nm" and r.get("flux") is not None]
    if not long_band or not long_band[-1]["flux"] > 0:
        return None
    return long_band[-1]


def normalize(raw):
    latest, week = raw.get("latest") or [], raw.get("week") or []
    flux = raw.get("flux") or []
    mx = [f for f in week if str(f.get("max_class", "")).upper()[:1] in ("M", "X")]
    worst = max(week, key=lambda f: _cls_key(f.get("max_class", "")), default=None)
    f0 = _latest_long_band(flux) or _latest_long_band(raw.get("flux_secondary") or []) or {}
    return frag(
        latest_flare=(latest[0] if latest else None),
        flares_7d_count=len(week),
        mx_flares_7d=len(mx),
        worst_7d_class=(worst or {}).get("max_class"),
        xray_long=(float(f0["flux"]) if f0 else None),
        xray_time=f0.get("time_tag"),
        xray_satellite=f0.get("satellite"),
    )
