"""US-region fetcher (DEPLOY-ONLY): pull NASA feeds via Modal (US cloud).

Problem: DONKI / CDAWeb / OMNI backends (GSFC/CCMC netblocks) time out
from some Canadian networks (measured 2026-10-26 from Toronto egress:
TCP CONNECT to *.gsfc.nasa.gov hangs; same links work over a US VPN).
NOAA SWPC, Kyoto WDC and GFZ work fine from anywhere.

Fix: run NASA pulls on Modal -- its workers egress from US regions.
This matches the project plan (Modal = ingestion pipeline host).

Deploy (needs working `modal` auth, workspace humble92):
    modal deploy sandbox/us_fetch_modal.py        # schedule: every 10 min
    modal run sandbox/us_fetch_modal.py::fetch_once

What it does: fetches DONKI event catalogs + OMNI HRO daily file head +
CDAWeb availability probe from US egress, prints a compact JSON report.
Wire the returned dict into Modal Dict/Bucket for the real pipeline.
"""
import modal

app = modal.App("solar-gps-guardian-us-ingest")
IMAGE = modal.Image.debian_slim(python_version="3.12")

# CCMC host since 2026-09-30. No API key. The nasa-api secret stays mounted
# so NASA_API_KEY remains available, but it is not sent.
DONKI_BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
DONKI_EPS = ["CME", "GST", "IPS", "FLR", "SEP", "MPC", "RBE", "HSS",
             "WSAEnlilSimulations", "notifications"]
# Monthly 1-min OMNI file. The old hro2 daily path 404s; this directory is current.
OMNI_DIR = "https://spdf.gsfc.nasa.gov/pub/data/omni/high_res_omni/monthly_1min"
CDAWEB_PROBE = "https://cdaweb.gsfc.nasa.gov/index.html"
US_REGION = "us"


def _omni_url(day):
    return f"{OMNI_DIR}/omni_min{day:%Y%m}.asc"


@app.function(image=IMAGE, timeout=180, region=US_REGION,
              secrets=[modal.Secret.from_name("nasa-api")])  # NASA_API_KEY
def fetch_once(days: int = 7) -> dict:
    import datetime as dt
    import json
    import os
    import urllib.parse, urllib.request

    key = os.environ.get("NASA_API_KEY", "")
    end = dt.date.today()
    start = (end - dt.timedelta(days=days)).isoformat()

    def get(url, params=None, nbytes=400):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url, headers={"User-Agent": "SolarGPSGuardian-modal/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read(nbytes)

    report = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "nasa_key": "retained" if key and key != "DEMO_KEY" else "absent",
              "donki": {}, "us_probes": {}}
    for ep in DONKI_EPS:
        p = {"startDate": start, "endDate": end.isoformat()}
        if ep == "notifications":
            p["type"] = "all"
        try:
            st, raw = get(f"{DONKI_BASE}/{ep}", p, 200000)
            data = json.loads(raw.decode("utf-8", "replace"))
            report["donki"][ep] = {"status": st,
                                   "events": len(data) if isinstance(data, list) else 1}
        except Exception as e:  # noqa: BLE001
            report["donki"][ep] = {"error": f"{type(e).__name__}: {e}"}
    probes = {"omni_hro": _omni_url(end), "cdaweb": CDAWEB_PROBE}
    for name, url in probes.items():
        try:
            st, raw = get(url)
            report["us_probes"][name] = {"status": st, "head": raw[:80].decode(
                "utf-8", "replace")}
        except Exception as e:  # noqa: BLE001
            report["us_probes"][name] = {"error": f"{type(e).__name__}: {e}"}
    try:
        _, raw = get("https://ipinfo.io/json")
        geo = json.loads(raw.decode("utf-8"))
        report["egress"] = {k: geo.get(k) for k in ("ip", "city", "region", "country")}
    except Exception as e:  # noqa: BLE001
        report["egress"] = {"error": str(e)}
    print(json.dumps(report, indent=1)[:3000])
    return report


@app.function(image=IMAGE, schedule=modal.Cron("*/10 * * * *"),
              secrets=[modal.Secret.from_name("nasa-api")])
def ingest_cron():
    """Every 10 min: same pull as fetch_once (persist to Modal Dict next)."""
    fetch_once.remote()
