"""GloTEC real-time TEC: index of tiles + latest tile (GPS-direct).

The tile is heavy (5k+ features). normalize() keeps a compact
(lon, lat, tec, anomaly) grid for the volume, plus tec_max for the public
snapshot. anomaly is the deviation from the 30-day median in TECU (SWPC). It
is kept only where quality_flag > 0: 0 means no GNSS observations went into
that cell (oceans, deserts), so its anomaly is model output. Lookup is
tec_value_at() / nearest_value() / nearest_cell(). Empty index observed live
is tolerated (available=False, no crash).

Tiles are written every 10 minutes and appear about 1.3 hours after their
time tag (measured 2026-10-31). The index JSON is sometimes published as an
empty list while tiles keep arriving, so an empty index falls back to the
newest file in the directory listing.
"""
import re

from .base import ProviderError, frag, http_get_json, http_get_text

ID = "tec"
BASE = "https://services.swpc.noaa.gov"


TILE_DIR = "/products/glotec/geojson_2d_urt/"
TILE_NAME = re.compile(r"glotec_icao_(\d{8}T\d{6})Z\.geojson")


def _index_from_listing(html):
    """Directory listing -> index rows [{time_tag, url}], oldest first."""
    stamps = sorted(set(TILE_NAME.findall(html or "")))
    return [{"time_tag": f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}Z",
             "url": f"{TILE_DIR}glotec_icao_{s}Z.geojson"} for s in stamps]


def fetch(env=None):
    idx = http_get_json(f"{BASE}/products/glotec/geojson_2d_urt.json")
    if not idx:
        idx = _index_from_listing(http_get_text(BASE + TILE_DIR))[-1:]
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
        anomaly = props.get("anomaly")
        if not isinstance(anomaly, (int, float)) or not props.get("quality_flag"):
            anomaly = None
        if lon is not None and isinstance(val, (int, float)):
            cells.append((float(lon), float(lat), float(val),
                          None if anomaly is None else float(anomaly)))
    return cells


def nearest_cell(cells, lon, lat):
    """Nearest (lon, lat, tec[, anomaly]) cell. None when the grid is missing."""
    if not cells:
        return None
    return min(cells, key=lambda c: (float(c[0]) - lon) ** 2 + (float(c[1]) - lat) ** 2)


def nearest_value(cells, lon, lat):
    """TEC of the nearest cell. None when the grid is missing."""
    best = nearest_cell(cells, lon, lat)
    return None if best is None else float(best[2])


def nearest_anomaly(cells, lon, lat):
    """30-day-median deviation (TECU) of the nearest cell; None if unobserved or absent."""
    best = nearest_cell(cells, lon, lat)
    if best is None or len(best) < 4 or best[3] is None:
        return None
    return float(best[3])


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
                grid=[list(c) for c in cells])
