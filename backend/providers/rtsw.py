"""L1 real-time solar wind: SWPC RTSW 1-min plasma + mag (+ephemeris).

Spacecraft mix observed live: SOLAR1 (primary), ACE (backup), IMAP (new).
Fastest signal (~30-60 min lead time) but gappy -> stale_after is short.
"""
from .base import ProviderError, frag, http_get_json

ID = "rtsw"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    return {
        "wind": http_get_json(f"{BASE}/json/rtsw/rtsw_wind_1m.json"),
        "mag": http_get_json(f"{BASE}/json/rtsw/rtsw_mag_1m.json"),
    }


def normalize(raw):
    wind, mag = raw.get("wind") or [], raw.get("mag") or []
    if not wind and not mag:
        raise ProviderError("rtsw: empty payload")
    w = wind[-1] if wind else {}
    m = mag[-1] if mag else {}
    srcs = sorted({r.get("source") for r in wind[-60:] + mag[-60:] if r.get("source")})
    return frag(
        time_tag=w.get("time_tag") or m.get("time_tag"),
        speed_km_s=w.get("proton_speed"),
        density_cc=w.get("proton_density"),
        temp_k=w.get("proton_temperature"),
        bt_nt=m.get("bt"),
        bz_gsm_nt=m.get("bz_gsm"),
        spacecraft=w.get("source") or m.get("source"),
        spacecraft_seen=srcs,
    )
