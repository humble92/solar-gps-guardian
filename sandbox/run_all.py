"""Run every sandbox fetcher and print a pass/fail summary."""
import subprocess
import sys

SCRIPTS = [
    ("noaa_kp_index.py", "NOAA Kp-index (doc 1/3)"),
    ("noaa_solar_flare_reports.py", "NOAA Solar Flare reports (doc 2/3)"),
    ("noaa_3day_geomag_forecast.py", "NOAA 3-day geomag forecast (doc 3/3)"),
    ("nasa_donki.py", "DONKI catalogs (CCMC DONKI-API, no key)"),
    ("solar_wind_extra.py", "BONUS solar-wind / GPS-threat feeds"),
    # us_fetch_modal.py is deploy-only (modal deploy), skipped here.
]

if __name__ == "__main__":
    base = __file__.rsplit("/", 1)[0]
    results = []
    for fname, label in SCRIPTS:
        print(f"\n{'#' * 70}\n# {label}: {fname}\n{'#' * 70}")
        p = subprocess.run([sys.executable, f"{base}/{fname}"],
                           capture_output=True, text=True, timeout=300)
        print(p.stdout[-3500:])
        if p.returncode != 0:
            print(f"[stderr] {p.stderr[-800:]}")
        results.append((label, p.returncode))
    print(f"\n{'=' * 70}\nSUMMARY")
    for label, rc in results:
        print(f"  [{'PASS' if rc == 0 else 'FAIL'}] {label}")
    raise SystemExit(0 if all(rc == 0 for _, rc in results) else 1)
