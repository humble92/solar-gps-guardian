"""STEREO-A beacon 1-min (off-Sun-Earth-line early warning, experimental).

Beacon quality is rough (plasma often null, mag spikes observed): flagged
experimental and excluded from the risk score (docs/implementation.md 3.1).
"""
from .base import frag, http_get_json

ID = "stereo"
URL = "https://services.swpc.noaa.gov/json/stereo/stereo_a_1m.json"


def fetch(env=None):
    return {"rows": http_get_json(URL)}


def normalize(raw):
    rows = raw.get("rows") or []
    last = rows[-1] if rows else {}
    bt = last.get("Bt_nT")
    sane = isinstance(bt, (int, float)) and bt < 100  # spike filter
    return frag(experimental=True, time_tag=last.get("timestamp"),
                speed_km_s=last.get("speed_KPS") if sane else None,
                density_cc=last.get("density_cm3") if sane else None,
                bt_nt=bt if sane else None, spike_filtered=not sane)
