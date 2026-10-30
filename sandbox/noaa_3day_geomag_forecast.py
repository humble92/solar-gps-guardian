"""Doc source 3/3: NOAA SWPC 3-Day Geomagnetic Forecasts (00:30 & 12:30 UT).

Endpoints (all public, no key):
  - Geomag forecast text .... text/3-day-geomag-forecast.txt (Kp table + Ap + probs)
  - Full 3-day forecast ..... text/3-day-forecast.txt (R/S/G + Kp detail)
  - Kp forecast JSON ........ products/noaa-planetary-k-index-forecast.json
  - 27-day outlook .......... text/27-day-outlook.txt (recurrence baseline)
  - Forecaster discussion ... text/discussion.txt
"""
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import FetchError, fetch_json, fetch_text, header  # noqa: E402

BASE = "https://services.swpc.noaa.gov"
URLS = {
    "geomag_txt": f"{BASE}/text/3-day-geomag-forecast.txt",
    "full_txt": f"{BASE}/text/3-day-forecast.txt",
    "kp_json": f"{BASE}/products/noaa-planetary-k-index-forecast.json",
    "outlook_27d": f"{BASE}/text/27-day-outlook.txt",
    "discussion": f"{BASE}/text/discussion.txt",
}


def parse_kp_table(txt):
    """Extract the 'NOAA Kp index forecast' block rows -> list of dicts."""
    rows = []
    in_table = False
    for line in txt.splitlines():
        if "NOAA Kp index forecast" in line:
            in_table = True
            continue
        if in_table:
            m = re.match(r"\s*(\d{2}-\d{2}UT)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", line)
            if m:
                rows.append({"ut": m.group(1), "day1": float(m.group(2)),
                             "day2": float(m.group(3)), "day3": float(m.group(4))})
            elif rows and not line.strip():
                break
    return rows


def main():
    print("NOAA SWPC 3-Day Geomagnetic Forecast broadcast (predictive routing input)")
    try:
        header("Geomagnetic forecast text", URLS["geomag_txt"])
        txt = fetch_text(URLS["geomag_txt"])
        print("  " + "\n  ".join(txt.splitlines()[:14]))
        rows = parse_kp_table(txt)
        if rows:
            mx = max(max(r["day1"], r["day2"], r["day3"]) for r in rows)
            print(f"  parsed Kp rows={len(rows)} max_forecast_Kp={mx:.2f} "
                  f"storm_expected={'YES' if mx >= 5 else 'no'}")

        header("Full 3-day forecast (head)", URLS["full_txt"])
        full = fetch_text(URLS["full_txt"])
        print("  " + "\n  ".join(full.splitlines()[:12]))

        header("Kp forecast JSON", URLS["kp_json"])
        print(f"  {str(fetch_json(URLS['kp_json']))[:500]}")

        header("27-day outlook (head)", URLS["outlook_27d"])
        out = fetch_text(URLS["outlook_27d"])
        print("  " + "\n  ".join(out.splitlines()[:12]))

        header("Forecaster discussion (head)", URLS["discussion"])
        disc = fetch_text(URLS["discussion"])
        print("  " + "\n  ".join(disc.splitlines()[:10]))
        print("\nOK: 3-day forecast pipeline works (no key needed).")
        return 0
    except FetchError as e:
        print(f"\nFAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
