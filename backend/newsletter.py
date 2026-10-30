"""Monthly newsletter: publish-time archive collect -> package -> LLM -> store.

No snapshot history is kept; every input is re-queried for the target month
at publish time (implementation.md section 3.5). Partial failures degrade
per-source; the letter always publishes with an "aggregated at" note.
"""
import calendar
import datetime as dt
import json
import os
import re
import urllib.request

from .providers.base import http_get_json, http_get_text, utcnow_iso
from .providers import dst as dst_mod

DONKI = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
EPS = ("CME", "GST", "FLR", "SEP", "IPS", "HSS")
GFZ_SINCE_1932 = "https://kp.gfz.de/app/files/Kp_ap_since_1932.txt"
OMNI_YEARLY = ("https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/"
               "omni2_{year}.asc")


def last_complete_month(today=None):
    t = today or dt.date.today()
    first_this = t.replace(day=1)
    last_prev = first_this - dt.timedelta(days=1)
    y, m = last_prev.year, last_prev.month
    start = dt.date(y, m, 1)
    end = dt.date(y, m, calendar.monthrange(y, m)[1])
    return {"period": f"{y:04d}-{m:02d}", "year": y, "month": m,
            "start": start.isoformat(), "end": end.isoformat()}


def _donki(period, w):
    out, top = {}, []
    for ep in EPS:
        try:
            data = http_get_json(f"{DONKI}/{ep}", {"startDate": w["start"],
                                 "endDate": w["end"]}, timeout=60)
            out[ep] = len(data) if isinstance(data, list) else 1
            if ep == "FLR":
                for f in data if isinstance(data, list) else []:
                    top.append({"date": (f.get("beginTime") or "")[:10],
                                "type": "Flare", "detail": f.get("classType", "")})
            if ep == "CME":
                for c in data if isinstance(data, list) else []:
                    top.append({"date": (c.get("startTime") or "")[:10],
                                "type": "CME", "detail": c.get("activityID", "")})
        except Exception:  # noqa: BLE001 - tolerate per-endpoint failure
            out[ep] = None
    return out, top


def _kyoto_month(w):
    yymm = f"{w['year']:04d}{w['month']:02d}"
    url = f"https://wdc.kugi.kyoto-u.ac.jp/dst_provisional/{yymm}/dst{yymm[2:]}.for.request"
    rows = dst_mod.parse_dst(http_get_text(url, timeout=60))
    mins = [min(v for v in r["hourly"] if v != 9999) for r in rows if r["hourly"]]
    return {"days": len(rows), "min_dst": min(mins) if mins else None,
            "storm_days_dst_le_-50": sum(1 for v in mins if v <= -50)}


def _gfz_month(w):
    daily = {}
    for ln in http_get_text(GFZ_SINCE_1932, timeout=90).splitlines():
        if ln.startswith("#") or not ln.strip():
            continue
        p = ln.split()
        try:
            if int(p[0]) == w["year"] and int(p[1]) == w["month"]:
                daily[int(p[2])] = max(daily.get(int(p[2]), 0), float(p[7]))
        except (ValueError, IndexError):
            continue
    vals = sorted(daily.values())
    return {"days": len(vals), "max_kp": max(vals) if vals else None,
            "daily_max_kp": [daily[d] for d in sorted(daily)]}


def _omni_month(w):
    """OMNI2 hourly (US-only reachability); graceful None when unreachable."""
    text = http_get_text(OMNI_YEARLY.format(year=w["year"]), timeout=90)
    speeds, bzs = [], []
    for ln in text.splitlines():
        p = ln.split()
        if len(p) < 42:
            continue
        try:
            if int(p[1]) != w["month"]:  # year doy month day hour ...
                continue
            v, bz = float(p[24]), float(p[15])  # bulk speed, Bz GSM (OMNI2 layout)
            if v < 9000:
                speeds.append(v)
            if abs(bz) < 900:
                bzs.append(bz)
        except (ValueError, IndexError):
            continue
    if not speeds:
        return None
    return {"mean_speed_km_s": round(sum(speeds) / len(speeds), 1),
            "max_speed_km_s": max(speeds),
            "min_bz_nt": min(bzs) if bzs else None, "samples": len(speeds)}


def collect(w):
    pkg = {"period": w["period"], "window": [w["start"], w["end"]],
           "aggregated_at": utcnow_iso(), "sources": {}}
    try:
        counts, top = _donki(pkg["period"], w)
        pkg["donki_counts"] = counts
        pkg["top_events"] = sorted(top, key=lambda e: e["date"])[:12]
        pkg["sources"]["donki"] = "ok" if any(v is not None for v in counts.values()) else "failed"
    except Exception as e:  # noqa: BLE001
        pkg["sources"]["donki"] = f"failed: {type(e).__name__}"
    for name, fn in (("kyoto_dst", _kyoto_month), ("gfz_kp", _gfz_month),
                     ("omni", _omni_month)):
        try:
            pkg[name] = fn(w)
            pkg["sources"][name] = "ok"
        except Exception as e:  # noqa: BLE001
            pkg[name] = None
            pkg["sources"][name] = f"failed: {type(e).__name__}"
    pkg["notes"] = [
        "Kyoto Dst values are provisional and may be revised.",
        "RTSW/GloTEC have no public monthly archive; excluded from this letter.",
    ]
    return pkg


def render_chart_svg(pkg, width=720, height=240):
    kp = (pkg.get("gfz_kp") or {}).get("daily_max_kp") or []
    if not kp:
        return None
    mx = max(kp) or 1
    bw = width / max(len(kp), 1)
    bars = "".join(
        f'<rect x="{i * bw + 1:.1f}" y="{height - 30 - (v / mx) * (height - 60):.1f}" '
        f'width="{bw - 2:.1f}" height="{(v / mx) * (height - 60):.1f}" fill="#f5a623"/>'
        for i, v in enumerate(kp))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'style="background:#0e141b"><text x="10" y="18" fill="#e8eef4" '
            f'font-size="13">Daily max Kp - {pkg["period"]} (max {mx})</text>'
            f"{bars}"
            f'<text x="10" y="{height - 8}" fill="#93a5b5" font-size="11">'
            f"Source: GFZ Kp (CC BY 4.0)</text></svg>")


_NUM = re.compile(r"\d+(?:\.\d+)?")


def package_numbers(pkg):
    nums = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            nums.add(round(float(x), 2))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(pkg)
    y, m = pkg["period"].split("-")
    nums.update({float(y), float(m)})
    return nums


_BARE_NUM = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z])")
_DATE_RX = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}(?::\d{2})?")


def validate_draft(md, pkg):
    allowed = package_numbers(pkg)
    allowed |= {abs(v) for v in list(allowed)}  # "-82 nT" reads back as 82
    text = _DATE_RX.sub(" ", md)  # dates/times are not claimed numbers
    bad = sorted({float(t) for t in _BARE_NUM.findall(text)} - allowed)
    return bad  # empty list == valid


def _template_draft(pkg):
    c = pkg.get("donki_counts") or {}
    g = pkg.get("gfz_kp") or {}
    k = pkg.get("kyoto_dst") or {}
    lines = [
        f"# Solar wind month in review: {pkg['period']}",
        "",
        f"## Month summary",
        f"Max Kp {g.get('max_kp')}; min Dst {k.get('min_dst')} nT; "
        f"CMEs {c.get('CME') if c.get('CME') is not None else 'n/a'}, "
        f"flares {c.get('FLR') if c.get('FLR') is not None else 'n/a'}, "
        f"storms {c.get('GST') if c.get('GST') is not None else 'n/a'}. "
        f"One-line take: the month is summarized by the numbers above; "
        f"details follow in the table.",
        "",
        "## Top events",
        "| Date | Type | Detail |",
        "|---|---|---|",
    ]
    for e in pkg.get("top_events", [])[:8]:
        lines.append(f"| {e.get('date')} | {e.get('type')} | {e.get('detail')} |")
    lines += ["", "## Next-month watch points",
              "Follow the daily SWPC 3-day forecast; storm risk rises when "
              "the forecast reaches G-scale storm levels.", "",
              f"_Aggregated at {pkg['aggregated_at']}. "
              f"Sources: DONKI, Kyoto WDC, GFZ (CC BY)"
              + (", OMNI/SPDF." if pkg.get("omni") else ". OMNI unavailable this run.") + "_"]
    return "\n".join(lines)


def write_draft(pkg):
    providers = [
        ("baseten", os.environ.get("BASETEN_API_BASE", "https://inference.baseten.co/v1"),
         os.environ.get("BASETEN_API_KEY"), os.environ.get("BASETEN_MODEL")),
        ("fireworks", os.environ.get("FIREWORKS_API_BASE", "https://api.fireworks.ai/inference/v1"),
         os.environ.get("FIREWORKS_API_KEY"), os.environ.get("FIREWORKS_MODEL")),
    ]
    for name, base, key, model in providers:
        if not (key and model):
            continue
        try:
            body = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content":
                     "Write a SHORT monthly space-weather newsletter in markdown. "
                     "Use ONLY the numbers in the JSON package. Add at most a "
                     "one-line commentary per section (interpretation only, no "
                     "new numbers/events). Structure: headline, month summary, "
                     "top-events table, next-month watch points."},
                    {"role": "user", "content": json.dumps(pkg)},
                ],
                "max_tokens": 700}).encode()
            req = urllib.request.Request(base.rstrip("/") + "/chat/completions",
                                         data=body, headers={
                                             "Authorization": f"Bearer {key}",
                                             "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                md = json.loads(r.read())["choices"][0]["message"]["content"]
            if not validate_draft(md, pkg):
                return md, name
        except Exception:  # noqa: BLE001
            continue
    return _template_draft(pkg), "template"


def generate(store, period=None, today=None):
    if period:
        y, m = (int(x) for x in period.split("-"))
        w = {"period": period, "year": y, "month": m,
             "start": f"{y:04d}-{m:02d}-01",
             "end": f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"}
    else:
        w = last_complete_month(today)
    pkg = collect(w)
    md, source = write_draft(pkg)
    chart = render_chart_svg(pkg)
    title = f"Solar wind month in review: {w['period']} ({source})"
    nid = store.save_newsletter(w["period"], title, md, chart, pkg)
    return {"id": nid, "period": w["period"], "title": title,
            "source": source, "sources_ok": pkg["sources"]}
