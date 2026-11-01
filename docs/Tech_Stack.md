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
| Nominatim and the public OSRM server | Place lookup and driving geometry. Called by the browser. The score of that path is `POST /route-score` on the Python API. |
| Modal | 5-minute ingest, 6-hour critical check, daily digest, and the HTTP API. |
| SQLite on a Modal Volume | Subscriptions, one snapshot row, one TEC grid row, one OVATION grid row, one send log, newsletters. Locally the file is `data/guardian.db`. |
| Baseten, then Fireworks | Optional prose + monthly newsletter writing. If both are absent or the echoed score does not match, the template sentence from `risk.py` is used. |
| SMTP | Real mail only from the deployed batch. Local `--batch` writes `data/outbox/*.eml`. |

`backend/app.py` is the only module that imports Modal. Providers, the risk
engine, and the mailer do not.

There is no long-running Python server in this repository. `python
backend/app.py` does not listen. `modal serve backend/app.py` runs the
functions in Modal's cloud while the command stays open on your machine.
`modal deploy backend/app.py` is what leaves the schedules in place.

Containers scale to zero. A 5-minute ingest often pays a cold start of a
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

Provider order: rtsw, kp, flares, forecast_3d, donki, tec, ovation, dst,
kp_gfz, stereo, enlil.

DONKI is the only live provider called from `region="us"`, because
`ccmc.gsfc.nasa.gov` timed out from Ontario on 2026-10-29. The other
providers run in Modal's default region. CDAWeb and OMNI are not on this
live list. They are probed by `sandbox/us_fetch_modal.py`. The monthly
newsletter plan (`implementation.md` §3.5) adopts OMNI aggregates for the
retrospective; CDAWeb stays out (OMNI is already its curated composite).

`NASA_API_KEY` is kept in `.env` and in the Modal secret `nasa-api`. The
CCMC DONKI host does not receive it.

An empty `/snapshot` cache runs the pipeline inside that request and returns
the JSON. That path does not save the row. The 5-minute cron does. Its timeout is
240 seconds, under the period, so two ingests never write the SQLite file on
the volume at the same time. A warm API container reloads the volume at
most once a minute (`_fresh_volume` in `backend/app.py`), so it serves the
newest committed snapshot without a restart.

## Feed fallbacks

Each provider fails on its own; a failed or empty feed never stops the
snapshot. Some feeds also have a fallback inside the provider:

- GOES X-ray (`flares`): when the primary satellite's newest long-band
  sample is 0 (a data gap; seen for 1.5 hours on 2026-10-31), the secondary
  satellite's file is used.
- GloTEC (`tec`): the index JSON is sometimes published as an empty list
  while tiles keep arriving, so an empty index falls back to the newest
  tile in the directory listing. The grid is stored with its tile time.
- Kyoto Dst (`dst`): during the first hours of a month the new month's file
  does not exist yet (404), so last month's file is read.
- DONKI: only this fetch runs in `region="us"` (see above).

`degraded` is true when DONKI or GloTEC is missing from a run. The page
shows DEGRADED MODE, and the sentence names the missing feed.

## Scoring service

`backend/risk.py` computes the score. What the inputs mean, the weights,
and their limits are in [Pipeline_Study.md](Pipeline_Study.md).

The page does not recompute the score. The banner calls
`GET /local-score`. A route calls `POST /route-score` with up to 8 samples
of the OSRM line, including the start and the end, spaced through the
vertex list. The corridor score is the highest sample. See `Manual.md` for
what the sentence and the line color show. Demo mode and the superstorm
step use fixed labels because those cards are not on the server. The
route-risk step of the same button sends `scenario=storm`, so those
samples use the superstorm numbers with the live clock and TEC grid. The
banner stays the live position score.

Each request reads the snapshot plus two lookup grids from the volume: the
GloTEC grid (`tec_grid`, with its tile time) and the OVATION grid
(`aurora_grid`). The daily digest and the 6-hour storm check score every
subscriber's stored coordinates with the same function, and the mail body
carries the same sentence as the page, not the LLM paragraph.

When an LLM is configured, it receives the finished score and must end with
`SCORE: <that number>`. Any other number is discarded and the template
remains. The order is Baseten, then Fireworks, then the template.

The same LLM writes the monthly newsletter from a fixed-number archive
package (DONKI events, Kyoto Dst, GFZ Kp, OMNI solar-wind aggregates):
numbers only from the package, plus a one-line commentary per section.
The package is collected on demand at publish time; no snapshot history
is kept. See `implementation.md` Phase 7 for the contract and validation.

The pipeline was chosen by a scored study of six designs; the study and
the changes made after it are in [Pipeline_Study.md](Pipeline_Study.md).
