"""Doc source 1/3: NOAA SWPC Kp-index (real-time / daily baseline hazard).

Endpoints (all public, no key):
  - 3-hourly planetary K index ........ products/noaa-planetary-k-index.json
  - 1-min estimated planetary K ....... json/planetary_k_index_1m.json
  - 1-min Boulder K ................... json/boulder_k_index_1m.json
  - G-scale status .................... products/noaa-scales.json
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import FetchError, fetch_json, header  # noqa: E402

BASE = "https://services.swpc.noaa.gov"
URLS = {
    "kp_3hourly": f"{BASE}/products/noaa-planetary-k-index.json",
    "kp_forecast": f"{BASE}/products/noaa-planetary-k-index-forecast.json",
    "kp_1m": f"{BASE}/json/planetary_k_index_1m.json",
    "boulder_1m": f"{BASE}/json/boulder_k_index_1m.json",
    "scales": f"{BASE}/products/noaa-scales.json",
}


def g_scale(kp):
    if kp >= 9:
        return "G5 Extreme"
    if kp >= 8:
        return "G4 Severe"
    if kp >= 7:
        return "G3 Strong"
    if kp >= 6:
        return "G2 Moderate"
    if kp >= 5:
        return "G1 Minor"
    return "No storm (Kp<5)"


def main():
    print("NOAA SWPC Kp-index broadcast (baseline geomagnetic hazard)")
    try:
        header("3-hourly planetary Kp", URLS["kp_3hourly"])
        rows = fetch_json(URLS["kp_3hourly"])
        for r in rows[-4:]:
            kp = float(r.get("Kp", 0))
            print(f"  {r.get('time_tag')}  Kp={kp:.2f}  a_running={r.get('a_running')} "
                  f"stations={r.get('station_count')}  -> {g_scale(kp)}")
        latest = float(rows[-1].get("Kp", 0))
        print(f"  LATEST: {rows[-1].get('time_tag')} Kp={latest:.2f} ({g_scale(latest)})")

        header("1-min estimated planetary Kp (latest)", URLS["kp_1m"])
        m1m = fetch_json(URLS["kp_1m"])
        m = m1m[-1] if isinstance(m1m, list) else m1m
        print(f"  {m.get('time_tag')}  estimated_kp={m.get('estimated_kp')} kp={m.get('kp')}")

        header("NOAA scales (current G/R/S)", URLS["scales"])
        s = fetch_json(URLS["scales"])
        cur = s.get("0", {})
        for k in ("G", "R", "S"):
            print(f"  {k}-scale: {cur.get(k)}")

        header("Kp forecast JSON (tail)", URLS["kp_forecast"])
        f = fetch_json(URLS["kp_forecast"])
        for r in f[-4:]:
            print(f"  {r.get('time_tag')} kp={r.get('kp')} {r.get('observed')} "
                  f"noaa_scale={r.get('noaa_scale')}")
        print("\nOK: Kp-index pipeline works (no key needed).")
        return 0
    except FetchError as e:
        print(f"\nFAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
