"""SWPC OVATION aurora nowcast: where the auroral oval is, 30-90 min ahead.

The oval moves with substorms, including the night-side bulge that a
planetary Kp cannot place. normalize() keeps only non-zero 1-degree cells
(lon 0..359 east, lat -90..90, value 0..100) for the volume. Lookup is
aurora_at().
"""
from .base import frag, http_get_json

ID = "ovation"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    return http_get_json(f"{BASE}/json/ovation_aurora_latest.json", timeout=60)


def normalize(raw):
    coords = (raw or {}).get("coordinates") or []
    cells = [[int(c[0]), int(c[1]), int(c[2])] for c in coords
             if len(c) >= 3 and isinstance(c[2], (int, float)) and c[2] > 0]
    if not coords:
        return frag(ok=False, available=False, note="no OVATION grid")
    return frag(available=True,
                observation_time=raw.get("Observation Time"),
                forecast_time=raw.get("Forecast Time"),
                aurora_max=max((c[2] for c in cells), default=0),
                cells=len(cells), grid=cells)


def aurora_at(cells, lat, lon):
    """Aurora value (0..100) in the 1-degree cell at lat/lon. None without a grid."""
    if not cells:
        return None
    key = (round(float(lon)) % 360, max(-90, min(90, round(float(lat)))))
    for c in cells:
        if c[0] == key[0] and c[1] == key[1]:
            return int(c[2])
    return 0
