"""3-day geomagnetic forecast (twice daily) + 27-day outlook + discussion text."""
import re

from .base import frag, http_get_text

ID = "forecast_3d"
BASE = "https://services.swpc.noaa.gov"
ROW = re.compile(r"\s*(\d{2}-\d{2}UT)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")


def fetch(env=None):
    return {
        "geomag": http_get_text(f"{BASE}/text/3-day-geomag-forecast.txt"),
        "full": http_get_text(f"{BASE}/text/3-day-forecast.txt"),
    }


def parse_kp_table(txt):
    rows, in_table = [], False
    for line in txt.splitlines():
        if "NOAA Kp index forecast" in line:
            in_table = True
            continue
        if in_table:
            m = ROW.match(line)
            if m:
                rows.append({"ut": m.group(1), "day1": float(m.group(2)),
                             "day2": float(m.group(3)), "day3": float(m.group(4))})
            elif rows and not line.strip():
                break
    return rows


def normalize(raw):
    rows = parse_kp_table(raw.get("geomag", ""))
    mx = max((max(r["day1"], r["day2"], r["day3"]) for r in rows), default=None)
    return frag(rows=rows, max_kp=mx, storm_expected=(mx is not None and mx >= 5),
                issued=(raw.get("geomag", "").splitlines()[1:2] or [""])[0][:80])
