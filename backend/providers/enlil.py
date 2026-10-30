"""Propagated solar wind + WSA-Enlil summary (CME arrival estimates)."""
from .base import frag, http_get_json, http_get_text

ID = "enlil"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    return {
        "propagated": http_get_json(f"{BASE}/products/geospace/propagated-solar-wind.json"),
        "enlil_chars": len(http_get_text(f"{BASE}/json/enlil_time_series.json", timeout=60)),
    }


def normalize(raw):
    rows = raw.get("propagated") or []
    last = rows[-1] if rows else []
    # [time_tag, speed, density, temp, bx, by, bz, bt, vx, vy, vz, propagated_time_tag]
    return frag(propagated_time=(last[11] if len(last) > 11 else None),
                speed_km_s=(last[1] if len(last) > 1 else None),
                bz_nt=(last[6] if len(last) > 6 else None),
                enlil_series_chars=raw.get("enlil_chars"))
