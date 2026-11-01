"""Kyoto WDC quicklook Dst (hourly storm-phase index, plain text).

Values are provisional and replaced later by definitive series; the UI
labels them as such (docs/implementation.md section 3.1).
"""
import datetime as dt

from .base import ProviderError, frag, http_get_text

ID = "dst"
WDC = "https://wdc.kugi.kyoto-u.ac.jp/dst_realtime"


def _month_url(day):
    yymm = day.strftime("%Y%m")
    return f"{WDC}/{yymm}/dst{yymm[2:]}.for.request"


def fetch(env=None, now=None):
    """This month's file; last month's when this month's is not there yet.

    Kyoto creates the new month's file some hours into the 1st, so the
    first ingests of a month got a 404 (seen 2026-11-01 00:0x UTC).
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    last_month = now.replace(day=1) - dt.timedelta(days=1)
    try:
        text = http_get_text(_month_url(now))
        if any(r["valid"] for r in _rows_with_values(text)):
            return {"text": text}
    except ProviderError:
        pass
    return {"text": http_get_text(_month_url(last_month))}


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


def _rows_with_values(text):
    return [{**r, "valid": [v for v in r["hourly"] if v != 9999]} for r in parse_dst(text)]


def normalize(raw):
    rows = _rows_with_values(raw.get("text", ""))
    if not rows:
        raise ProviderError("dst: no DST rows parsed")
    # The newest day can be all 9999 just after midnight; use the newest
    # day that has an hourly value.
    last = next((r for r in reversed(rows) if r["valid"]), rows[-1])
    vals = last["valid"]
    return frag(day=last["day"], latest_hour_dst=vals[-1] if vals else None,
                min_dst=min(vals) if vals else None, provisional=True)
