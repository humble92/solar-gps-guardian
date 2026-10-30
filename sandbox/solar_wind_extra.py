"""BONUS: best extra public solar-wind / GPS-relevant feeds (all keyless).

Why these: the doc's 3 sources cover Kp/flares/forecasts, but real-time
L1 solar wind is the earliest CME-arrival signal (~30-60 min lead time)
and TEC/Dst quantify the actual GPS threat. All below are free, no key.

  L1 real-time (SOLAR-1 primary since 2026, ACE backup, IMAP joining):
  - RTSW plasma+mag 1m ........... json/rtsw/rtsw_wind_1m.json, rtsw_mag_1m.json
  - ephemeris ..................... json/rtsw/rtsw_ephemerides_1h.json
  - summary ....................... products/summary/solar-wind-{speed,mag-field}.json
  Off-Sun-Earth-line / backup spacecraft:
  - STEREO-A beacon 1m ............ json/stereo/stereo_a_1m.json
  - ACE MAG/SWEPAM 1h ............. json/ace/{mag,swepam}/ace_{mag,swepam}_1h.json
  Models / propagated:
  - propagated solar wind ......... products/geospace/propagated-solar-wind.json
  - WSA-Enlil time series ......... json/enlil_time_series.json
  GPS-impact quantifiers:
  - GloTEC real-time TEC .......... products/glotec/geojson_2d_urt.json
  - Kyoto quicklook Dst ........... wdc.kugi.kyoto-u.ac.jp/dst_realtime/...
  - GFZ Kp nowcast (CC BY 4.0) .... kp.gfz.de/app/files/Kp_ap_nowcast.txt
  Science-grade archive (delayed; needs US egress, see us_fetch_modal.py):
  - NASA OMNI HRO 1-min ........... omniweb.gsfc.nasa.gov / cdaweb.gsfc.nasa.gov
"""
import datetime as dt
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import FetchError, fetch_json, fetch_text, header  # noqa: E402

SWPC = "https://services.swpc.noaa.gov"


def show(title, url, fn):
    try:
        data = fn(url)
        print(f"  {title}: {data}")
        return True
    except FetchError as e:
        print(f"  {title}: ERROR {e}")
        return False


def main():
    print("BONUS solar-wind / GPS-threat feeds broadcast")
    ok = tot = 0

    header("L1 real-time solar wind (RTSW)", f"{SWPC}/json/rtsw/")
    tot += 1
    try:
        wind = fetch_json(f"{SWPC}/json/rtsw/rtsw_wind_1m.json")
        mag = fetch_json(f"{SWPC}/json/rtsw/rtsw_mag_1m.json")
        w, m = wind[-1], mag[-1]
        srcs = sorted({r.get("source") for r in wind[-60:] if r.get("source")})
        print(f"  plasma latest: {w['time_tag']} src={w.get('source')} "
              f"V={w.get('proton_speed')} km/s N={w.get('proton_density')}/cc "
              f"T={w.get('proton_temperature')}K")
        print(f"  mag latest: {m['time_tag']} src={m.get('source')} "
              f"Bt={m.get('bt')}nT Bz_gsm={m.get('bz_gsm')}nT")
        print(f"  spacecraft seen in last 60 samples: {srcs}")
        ok += 1
    except FetchError as e:
        print(f"  RTSW ERROR: {e}")

    tot += 1
    ok += show("summary speed", f"{SWPC}/products/summary/solar-wind-speed.json",
               lambda u: fetch_json(u))
    tot += 1
    ok += show("STEREO-A beacon latest", f"{SWPC}/json/stereo/stereo_a_1m.json",
               lambda u: {k: fetch_json(u)[-1].get(k) for k in
                            ("timestamp", "speed_KPS", "density_cm3", "Bt_nT")})
    tot += 1
    ok += show("ACE MAG 1h (last)", f"{SWPC}/json/ace/mag/ace_mag_1h.json",
               lambda u: fetch_json(u)[-1])
    tot += 1
    ok += show("propagated SW (last)", f"{SWPC}/products/geospace/propagated-solar-wind.json",
               lambda u: fetch_json(u)[-1])
    tot += 1
    ok += show("Enlil time series (keys/size)", f"{SWPC}/json/enlil_time_series.json",
               lambda u: f"{len(fetch_text(u))} chars")

    header("GPS-threat quantifiers", "SWPC GloTEC / Kyoto WDC / GFZ")
    tot += 1
    try:
        idx_url = f"{SWPC}/products/glotec/geojson_2d_urt.json"
        entries = fetch_json(idx_url)  # index: [{url, time_tag}, ...]
        if not entries:
            print("  GloTEC real-time TEC: index reachable but EMPTY "
                  "(no tiles published right now)")
        else:
            last = entries[-1]
            tile = fetch_json(SWPC + last["url"])
            feats = tile.get("features", []) if isinstance(tile, dict) else tile
            print(f"  GloTEC real-time TEC: index={len(entries)} tiles "
                  f"latest={last['time_tag']} features={len(feats)}")
            ok += 1
    except FetchError as e:
        print(f"  GloTEC real-time TEC: ERROR {e}")
    yymm = dt.datetime.now(dt.timezone.utc).strftime("%Y%m")
    tot += 1
    ok += show("Kyoto quicklook Dst (month tail)",
               f"https://wdc.kugi.kyoto-u.ac.jp/dst_realtime/{yymm}/dst{yymm[2:]}.for.request",
               lambda u: [ln for ln in fetch_text(u).splitlines()
                          if ln.startswith("DST")][-1][:120])
    tot += 1
    ok += show("GFZ Kp nowcast (tail)",
               "https://kp.gfz.de/app/files/Kp_ap_nowcast.txt",
               lambda u: [ln for ln in fetch_text(u).splitlines()
                          if ln and not ln.startswith("#")][-1][:160])

    print(f"\n{ok}/{tot} bonus feeds reachable. (OMNI/CDAWeb science archive needs "
          "US egress -> us_fetch_modal.py)")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    raise SystemExit(main())
