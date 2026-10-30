"""Kyoto WDC quicklook Dst (hourly storm-phase index, plain text).

Values are provisional and replaced later by definitive series; the UI
labels them as such (docs/implementation.md section 3.1).
"""
import datetime as dt

from .base import ProviderError, frag, http_get_text

ID = "dst"
WDC = "https://wdc.kugi.kyoto-u.ac.jp/dst_realtime"


def fetch(env=None):
    yymm = dt.datetime.now(dt.timezone.utc).strftime("%Y%m")
    return {"text": http_get_text(f"{WDC}/{yymm}/dst{yymm[2:]}.for.request")}


def parse_dst(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("DST") and len(line) > 20:
            parts = line.split()
            # Pure-integer tokens after the header token are the 24 hourly
            # values (then daily mean); header extras like RRX-codes drop out.
            nums = [p for p in parts[1:] if p.lstrip("-").isdigit()]
            if len(nums) >= 24:
                rows.append({"day": parts[0], "hourly": [int(x) for x in nums[:24]]})
    return rows


def normalize(raw):
    rows = parse_dst(raw.get("text", ""))
    if not rows:
        raise ProviderError("dst: no DST rows parsed")
    last = rows[-1]
    vals = [v for v in last["hourly"] if v != 9999]
    return frag(day=last["day"], latest_hour_dst=vals[-1] if vals else None,
                min_dst=min(vals) if vals else None, provisional=True)
