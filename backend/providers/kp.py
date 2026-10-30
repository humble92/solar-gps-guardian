"""Planetary K index family: 3-hourly, 1-min estimated, forecast, G/R/S scales.

Kp is the stable baseline of the risk score; numbers come from here and the
3-day forecast, never from the LLM.
"""
from .base import ProviderError, frag, http_get_json

ID = "kp"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    return {
        "kp3": http_get_json(f"{BASE}/products/noaa-planetary-k-index.json"),
        "kp1m": http_get_json(f"{BASE}/json/planetary_k_index_1m.json"),
        "forecast": http_get_json(f"{BASE}/products/noaa-planetary-k-index-forecast.json"),
        "scales": http_get_json(f"{BASE}/products/noaa-scales.json"),
    }


def normalize(raw):
    kp3, kp1m, fc = raw.get("kp3") or [], raw.get("kp1m") or [], raw.get("forecast") or []
    if not kp3:
        raise ProviderError("kp: empty 3-hourly payload")
    latest = kp3[-1]
    m1 = kp1m[-1] if kp1m else {}
    scales = (raw.get("scales") or {}).get("0", {})
    predicted = [r for r in fc if r.get("observed") == "predicted"]
    return frag(
        time_tag=latest.get("time_tag"),
        kp=float(latest.get("Kp", 0)),
        kp_1m_estimated=m1.get("estimated_kp"),
        g_scale=scales.get("G", {}),
        r_scale=scales.get("R", {}),
        s_scale=scales.get("S", {}),
        forecast_max_kp=max((float(r.get("kp", 0)) for r in predicted), default=None),
    )
