"""Doc source 2/3: NOAA SWPC Solar Flare event reports (real-time / daily).

Endpoints (all public, no key):
  - Latest flare ................ json/goes/primary/xray-flares-latest.json
  - 7-day flare list ............ json/goes/primary/xray-flares-7-day.json
  - 6-hour X-ray flux ........... json/goes/primary/xrays-6-hour.json
  - SUVI flare detections ....... json/goes/primary/suvi-flares-latest.json
  - Daily event reports (SGAS) .. text/solar-geophysical-event-reports.txt
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import FetchError, fetch_json, fetch_text, header  # noqa: E402

BASE = "https://services.swpc.noaa.gov"
URLS = {
    "flares_latest": f"{BASE}/json/goes/primary/xray-flares-latest.json",
    "flares_7d": f"{BASE}/json/goes/primary/xray-flares-7-day.json",
    "xrays_6h": f"{BASE}/json/goes/primary/xrays-6-hour.json",
    "suvi_latest": f"{BASE}/json/goes/primary/suvi-flares-latest.json",
    "event_reports": f"{BASE}/text/solar-geophysical-event-reports.txt",
}


def r_scale(cls):
    """NOAA R-scale from GOES flare class string like 'M2.3'/'X1.0'."""
    try:
        letter, mag = cls[0].upper(), float(cls[1:])
    except (ValueError, IndexError):
        return "unknown"
    power = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}.get(letter)
    if power is None:
        return "unknown"
    flux = mag * power
    if flux >= 2e-3:
        return "R5 Extreme"
    if flux >= 1e-3:
        return "R4 Severe"
    if flux >= 1e-4:
        return "R3 Strong"
    if flux >= 5e-5:
        return "R2 Moderate"
    if flux >= 1e-5:
        return "R1 Minor"
    return "below R-scale"


def main():
    print("NOAA SWPC Solar Flare reports broadcast")
    try:
        header("Latest GOES X-ray flare", URLS["flares_latest"])
        for f in fetch_json(URLS["flares_latest"]):
            print(f"  begin={f.get('begin_time')} max={f.get('max_time')} "
                  f"max_class={f.get('max_class')} ({r_scale(f.get('max_class', ''))}) "
                  f"end={f.get('end_time')} sat=GOES-{f.get('satellite')}")

        header("7-day flare list (tail)", URLS["flares_7d"])
        week = fetch_json(URLS["flares_7d"])
        print(f"  total flares in 7d: {len(week)}")
        big = [f for f in week if str(f.get("max_class", "")).upper().startswith(("M", "X"))]
        print(f"  M/X-class in 7d: {len(big)}")
        for f in week[-3:]:
            print(f"    {f.get('max_time')} {f.get('max_class')} ({r_scale(f.get('max_class', ''))})")

        header("Current X-ray flux (6h tail)", URLS["xrays_6h"])
        for row in fetch_json(URLS["xrays_6h"])[-3:]:
            print(f"  {row.get('time_tag')} long={float(row.get('xrlong', 0) or 0):.2e} "
                  f"short={float(row.get('xrshort', 0) or 0):.2e} sat=GOES-{row.get('satellite')}")

        header("SUVI flare detections (latest)", URLS["suvi_latest"])
        print(f"  {str(fetch_json(URLS['suvi_latest']))[:400]}")

        header("Daily solar-geophysical event reports (head)", URLS["event_reports"])
        txt = fetch_text(URLS["event_reports"])
        for line in txt.splitlines()[:18]:
            print(f"  {line}")
        print("\nOK: Solar Flare report pipeline works (no key needed).")
        return 0
    except FetchError as e:
        print(f"\nFAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
