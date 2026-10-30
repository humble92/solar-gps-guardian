# Technical stack

Solar-GPS-Guardian is a small serverless system. The page is a Next.js app.
The Python service runs on Modal. Open-data fetches, the risk score, and
mail are ordinary Python modules. Modal is only the scheduler and the HTTP
host.

## Runtime

| Piece | Role |
|---|---|
| Next.js 15, React 19, TypeScript | Single page on Vercel, or `npm run dev` locally. |
| Leaflet and OpenStreetMap | Map tiles and the position marker. |
| Nominatim and the public OSRM server | Place lookup and driving geometry. Called by the browser. |
| Modal | 15-minute ingest, hourly storm check, daily digest, and the HTTP API. |
| SQLite on a Modal Volume | One subscriptions table, one snapshot row, one send log. Locally the file is `data/guardian.db`. |
| Baseten, then Fireworks | Optional prose. If both are absent or the echoed score does not match, the template sentence from `risk.py` is used. |
| SMTP | Real mail only from the deployed batch. Local `--batch` writes `data/outbox/*.eml`. |

`backend/app.py` is the only module that imports Modal. Providers, the risk
engine, and the mailer do not.

There is no long-running Python server in this repository. `python
backend/app.py` does not listen. `modal serve backend/app.py` runs the
functions in Modal's cloud while the command stays open on your machine.
`modal deploy backend/app.py` is what leaves the schedules in place.

Containers scale to zero. A 15-minute ingest often pays a cold start of a
few seconds. The web function is FastAPI behind `@modal.asgi_app`. Modal
also runs plain functions and can host Flask or Django through WSGI. This
project does not use Django.

## Pipeline

`backend/pipeline.json` is the provider order and the enable flags. It does
not store measurements. `run_pipeline()` calls each provider, isolates
failures, and `build_snapshot()` builds one JSON document:

- `snapshot_version` is the schema number. It stays 1 until the shape of the
  document changes.
- `fetched_at`, `now`, `forecast_3d`, `events`, `tec`, `flags`, and
  `degraded` are the readings from that run.
- The database keeps one row, `telemetry_cache.id = 1`. The next ingest
  replaces it.

Provider order: rtsw, kp, flares, forecast_3d, donki, tec, dst, kp_gfz,
stereo, enlil.

DONKI is the only live provider called from `region="us"`, because
`ccmc.gsfc.nasa.gov` timed out from Ontario on 2026-10-29. The other
providers run in Modal's default region. CDAWeb and OMNI are not on this
live list. They are probed by `sandbox/us_fetch_modal.py`.

`NASA_API_KEY` is kept in `.env` and in the Modal secret `nasa-api`. The
CCMC DONKI host does not receive it.

An empty `/snapshot` cache runs the pipeline inside that request and returns
the JSON. That path does not save the row. The 15-minute cron does.

## Risk numbers

`risk.py` owns the score. The weights are constants in that file:

| Input | Points |
|---|---|
| Each Kp point, using the larger of current Kp and the 3-day maximum | 10 |
| Strongest flare in 7 days starts with M | 15 |
| Strongest flare in 7 days starts with X | 25 |
| Any listed Earth-arrival CME | 20 |
| Local TEC at or above 50 TECU, when the caller passes it | 10 |

The total is clamped to 0..100. Under 40 is LOW, under 70 is MODERATE, 70
and above is CRITICAL. Missing inputs score 0, LOW. Solar-wind speed and Bz
are stored for the sentence and are not part of the sum.

The browser repeats the same Kp, flare, and CME terms in
`frontend/lib/api.ts`. It does not call `GET /risk`. The email body uses the
Python template, not the LLM paragraph.

When an LLM is configured, it receives the finished score and must end with
`SCORE: <that number>`. Any other number is discarded and the template
remains. The order is Baseten, then Fireworks, then the template.

## Why this pipeline

Six candidates were scored on 2026-10-26. Weights: GPS fidelity 25%, lead
time 20%, location and route specificity 15%, behavior when a feed is down
15%, implementation simplicity 10%, cost and keys 10%, explainability 5%.

| ID | Idea | Weighted score |
|---|---|---|
| P1 | SWPC indices only | 3.50 |
| P2 | P1 plus TEC | 3.65 |
| P3 | P1 plus DONKI | 3.10 |
| P4 | SWPC, DONKI, TEC, and the Dst/GFZ cross-check | 4.60 |
| P5 | The model assigns the number | 2.35 |
| P6 | OMNI science archive | 2.65 |

P4 is the live path. P2 is the fallback if DONKI stays unreachable. P1 is
the floor when several feeds are down. P5 was rejected because a model must
not invent the score. P6 stays off the live path because the archive is
delayed and the GSFC download is blocked from some networks. The full grid
is [pipeline-study-scorecard.csv](../pipeline-study-scorecard.csv).
