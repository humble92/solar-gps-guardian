"""GloTEC real-time TEC: index of tiles + latest tile (GPS-direct).

The tile is heavy (5k+ features). normalize() keeps a compact (lon, lat, tec)
grid for the volume, plus tec_max for the public snapshot. Lookup is
tec_value_at() / nearest_value(). Empty index observed live is tolerated
(available=False, no crash).
"""
from .base import ProviderError, frag, http_get_json

ID = "tec"
BASE = "https://services.swpc.noaa.gov"


def fetch(env=None):
    idx = http_get_json(f"{BASE}/products/glotec/geojson_2d_urt.json")
    tile = None
    if idx:
        tile = http_get_json(BASE + idx[-1]["url"], timeout=60)
    return {"index": idx, "tile": tile}


def _cells(tile):
    feats = tile.get("features", []) if isinstance(tile, dict) else tile or []
    cells = []
    for f in feats:
        props = f.get("properties", {}) or {}
        geom = f.get("geometry", {}) or {}
        coords = geom.get("coordinates")
        lon = lat = None
        if geom.get("type") == "Point" and coords:
            lon, lat = coords[0], coords[1]
        elif coords:
            try:
                ring = coords[0]
                lon = sum(p[0] for p in ring) / len(ring)
                lat = sum(p[1] for p in ring) / len(ring)
            except (TypeError, IndexError):
                pass
        val = props.get("tec") or props.get("TEC") or props.get("value")
        if lon is not None and isinstance(val, (int, float)):
            cells.append((float(lon), float(lat), float(val)))
    return cells


def nearest_value(cells, lon, lat):
    """Nearest cell in a list of (lon, lat, tec). None when the grid is missing."""
    if not cells:
        return None
    best = min(cells, key=lambda c: (float(c[0]) - lon) ** 2 + (float(c[1]) - lat) ** 2)
    return float(best[2])


def tec_value_at(tile, lon, lat):
    return nearest_value(_cells(tile), lon, lat)


def normalize(raw):
    idx = raw.get("index") or []
    if not idx:
        return frag(ok=False, available=False, tiles=0, note="empty index (tolerated)")
    tile = raw.get("tile")
    cells = _cells(tile) if tile else []
    return frag(available=True, tiles=len(idx),
                latest_time=idx[-1].get("time_tag"),
                cells=len(cells),
                tec_max=max((c[2] for c in cells), default=None),
                grid=[[c[0], c[1], c[2]] for c in cells])
