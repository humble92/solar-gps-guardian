"""Doc source 4/4: DONKI solar-event catalogs.

Host since 2026-09-30: https://ccmc.gsfc.nasa.gov/DONKI-API/get/
No API key is sent. NASA_API_KEY may still be set in the environment for a
later client; this script does not read it.

Endpoints: CME, CMEAnalysis, GST, IPS, FLR, SEP, MPC, RBE, HSS,
  WSAEnlilSimulations, notifications
"""
import datetime as dt
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import FetchError, fetch_json, header, utcnow  # noqa: E402

BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
ENDPOINTS = ["CME", "CMEAnalysis", "GST", "IPS", "FLR", "SEP", "MPC", "RBE",
             "HSS", "WSAEnlilSimulations", "notifications"]


def window(days=7):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    return start.isoformat(), end.isoformat()


def fetch_donki(ep, start, end):
    params = {"startDate": start, "endDate": end}
    if ep == "notifications":
        params["type"] = "all"
    return fetch_json(f"{BASE}/{ep}", params, timeout=45)


def summarize(ep, data):
    n = len(data) if isinstance(data, list) else 1
    line = f"  {ep}: {n} event(s)"
    if isinstance(data, list) and data:
        first, last = data[0], data[-1]
        g = lambda d: (d.get("activityID") or d.get("messageID") or
                       d.get("startTime") or d.get("issueTime") or "?")
        line += f" | first={g(first)} last={g(last)}"
        if ep == "FLR":
            line += f" | max class={max(str(d.get('classType', '')) for d in data)}"
        if ep == "GST":
            line += f" | min Kp={min(d.get('allKpIndex', [{'kpIndex': 0}])[0].get('kpIndex', 0) if d.get('allKpIndex') else 0 for d in data)}"
    return line


def main():
    start, end = window()
    print(f"DONKI broadcast {start}..{end} ({BASE})")
    header("DONKI event catalogs", BASE)
    ok, failed = 0, []
    for ep in ENDPOINTS:
        try:
            print(summarize(ep, fetch_donki(ep, start, end)))
            ok += 1
        except FetchError as e:
            print(f"  {ep}: ERROR {e}")
            failed.append(ep)
    print(f"\n{ok}/{len(ENDPOINTS)} DONKI endpoints reachable at {utcnow()}.")
    if failed:
        print("HINT: GSFC hosts can fail from some networks. Re-run via "
              "modal run sandbox/us_fetch_modal.py::fetch_once.")
        return 1
    print("OK: DONKI pipeline works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
