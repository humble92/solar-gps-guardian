"""DONKI event catalogs from CCMC.

Live host since 2026-09-30:
https://ccmc.gsfc.nasa.gov/DONKI-API/get/
The api.nasa.gov gateway returns 503, and kauai.ccmc.gsfc.nasa.gov was retired.
This host does not take an API key. NASA_API_KEY is still read and reported
as key_tier so the credential stays available for a later client.
"""
import datetime as dt
import os

from .base import ProviderError, frag, http_get_json

ID = "donki"
BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
ENDPOINTS = ["CME", "CMEAnalysis", "GST", "IPS", "FLR", "SEP", "MPC", "RBE",
             "HSS", "WSAEnlilSimulations", "notifications"]


def fetch(env=None):
    key = (env or {}).get("NASA_API_KEY") or os.environ.get("NASA_API_KEY", "")
    end = dt.date.today()
    start = (end - dt.timedelta(days=7)).isoformat()
    end_s = end.isoformat()
    out, errors = {}, {}
    for ep in ENDPOINTS:
        params = {"startDate": start, "endDate": end_s}
        if ep == "notifications":
            params["type"] = "all"
        try:
            out[ep] = http_get_json(f"{BASE}/{ep}", params, timeout=45)
        except ProviderError as e:
            errors[ep] = str(e)[:240]
    tier = "retained" if key and key != "DEMO_KEY" else "absent"
    return {"data": out, "errors": errors, "key_tier": tier}


def normalize(raw):
    data, errors = raw.get("data", {}), raw.get("errors", {})
    if not data:
        raise ProviderError(f"donki: all endpoints failed: {list(errors)[:2]}")
    cme = data.get("CME") or []
    enlil = data.get("WSAEnlilSimulations") or []
    # WSA-Enlil puts the predicted Earth shock arrival in
    # estimatedShockArrivalTime. impactList holds other targets (spacecraft,
    # planets), and cmeInputs has no impact list (checked 2026-10-31).
    arrivals, seen = [], set()
    for sim in enlil:
        when = sim.get("estimatedShockArrivalTime")
        if not when or when in seen:
            continue
        seen.add(when)
        arrivals.append({"arrival": when, "glancing": bool(sim.get("isEarthGB")),
                         "minor": bool(sim.get("isEarthMinorImpact")),
                         "kp_90": sim.get("kp_90"), "kp_180": sim.get("kp_180")})
    arrivals.sort(key=lambda a: a["arrival"], reverse=True)
    counts = {ep: (len(v) if isinstance(v, list) else 1) for ep, v in data.items()}
    return frag(available=len(data), failed=sorted(errors), key_tier=raw.get("key_tier"),
                counts=counts, cme_count=len(cme), earth_arrivals=arrivals[:5])
