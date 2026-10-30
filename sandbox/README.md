# sandbox/ — Public Data Sources fetch & broadcast tests

Maps 1:1 to the **Public Data Sources & Ingestion** table in the project plan
(`Solar-GPS-Guardian` Google Doc), plus bonus solar-wind research.

| Script | Doc source | Key? | 2026-10-26 result (Toronto egress) |
|---|---|---|---|
| `noaa_kp_index.py` | NOAA SWPC Kp-index (real-time/daily) | no | PASS |
| `noaa_solar_flare_reports.py` | NOAA SWPC Solar Flare event reports | no | PASS |
| `noaa_3day_geomag_forecast.py` | NOAA SWPC 3-Day Geomagnetic Forecasts | no | PASS |
| `nasa_donki.py` | DONKI catalogs via `ccmc.gsfc.nasa.gov/DONKI-API/get/` | no (key kept, unused) | re-check after the 2026-09-30 host move |
| `solar_wind_extra.py` | BONUS: L1 wind, TEC, Dst, Kp nowcast | no | PASS 9/9 |
| `us_fetch_modal.py` | Deploy-only Modal (US) NASA fetcher | NASA key as Modal secret | not run here (auth) |
| `run_all.py` | runs all of the above except Modal | — | see summary |
| `test_parsing.py` | offline regression tests (stdlib unittest) | — | 8/8 PASS |

All fetchers are **stdlib-only** (`urllib`) — no pip install needed.
`us_fetch_modal.py` needs `pip install modal` + `modal token new`.

## Run

```bash
python3 sandbox/run_all.py            # everything (live network)
python3 sandbox/test_parsing.py       # offline regression tests
python3 sandbox/noaa_kp_index.py      # one feed
python3 sandbox/nasa_donki.py         # DONKI via CCMC, no key
```

## NASA API key: kept, not sent

DONKI no longer uses an API key. The live host since 2026-09-30 is
`https://ccmc.gsfc.nasa.gov/DONKI-API/get/`. `api.nasa.gov/DONKI` returns 503,
and `kauai.ccmc.gsfc.nasa.gov` was retired. `NASA_API_KEY` stays in `.env` and
in the Modal secret `nasa-api` for a later client. `nasa_donki.py` does not
read it.

## Network finding: NASA backends vs Canadian egress (important)

Measured 2026-10-26 from Toronto egress (this sandbox + your report):

- **Works from Canada**: NOAA SWPC (all), Kyoto WDC Dst, GFZ Kp nowcast,
  `www.nasa.gov`, `sdo.gsfc.nasa.gov`, `api.nasa.gov` gateway itself
  (NeoWs with DEMO_KEY returned 200).
- **Fails from Canada**: `cdaweb/spdf/omniweb/kauai.ccmc.gsfc.nasa.gov`
  (TCP CONNECT hangs), DONKI via api.nasa.gov (HTTP 503 "upstream connect
  error"), APOD backend (503). Your US-VPN test says these work from the US.

2026-10-29, VPN off, egress Ontario: `ccmc.gsfc.nasa.gov/DONKI-API/get/FLR` timed out
after 25s. The new host still needs a US pull. Conclusion: run **DONKI + CDAWeb/OMNI pulls on a US host**. That is exactly
`us_fetch_modal.py` (Modal workers egress from US regions; also matches the
plan's "Modal ingestion pipeline"). Keep SWPC/Kyoto/GFZ as direct feeds —
they work globally. Local `modal run` from this sandbox is currently blocked
(profile handshake fails), so deploy from your machine once, then it runs
on schedule in the US.

## Bonus research: better/other public solar-wind data

Live in `solar_wind_extra.py` (all verified 2026-10-26 unless noted):

- **L1 real-time RTSW** (`json/rtsw/rtsw_{wind,mag}_1m.json`, 1-min):
  the single best real-time feed. Spacecraft mix seen live:
  `SOLAR1` (primary since Jun 2026), `ACE` (backup), `IMAP` (new, live).
  DSCOVR-era `/products/solar-wind/*.json` URLs are **dead (404)** — do not
  use old blog snippets.
- **Propagated solar wind** (`products/geospace/propagated-solar-wind.json`):
  L1 shifted to bow shock + ~1h propagation stamp — free "arrival" estimate.
- **WSA-Enlil time series** (`json/enlil_time_series.json`, ~1.6 MB):
  CME-arrival model output, same model DONKI's WSAEnlilSimulations wraps.
- **STEREO-A beacon** (`json/stereo/stereo_a_1m.json`): off-line
  early warning, but beacon quality is rough (plasma often null, mag spikes
  like Bt=834 nT seen — flag/filter before use).
- **ACE direct** (`json/ace/{mag,swepam}/..._1h.json`): backup when RTSW
  has gaps (note: 1h files lagged ~1 month in this test — prefer RTSW).
- **GloTEC real-time TEC** (`products/glotec/geojson_2d_urt.json` index +
  per-tile geojson, 5184 features/tile): the most **GPS-direct** feed —
  ionospheric TEC maps. Index was transiently empty once during testing;
  the script tolerates that.
- **Kyoto quicklook Dst** (`dst_realtime/.../dstYYMM.for.request`):
  hourly storm-time index, plain text, works from CA. Provisional/final
  series replace it later for science use.
- **GFZ Kp nowcast** (`kp.gfz.de/app/files/Kp_ap_nowcast.txt`, CC BY 4.0):
  definitive-Kp source institute, 3-hourly + nowcast, works from CA.
- **NASA OMNI HRO 1-min / CDAWeb** (science-grade, multi-spacecraft,
  bow-shock-shifted): best archive for training/backtesting, but needs US
  egress (blocked from CA) — pull via `us_fetch_modal.py`.
