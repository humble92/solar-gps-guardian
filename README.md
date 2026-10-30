# Solar-GPS-Guardian

Live site: https://solar-gps-guardian.ninefruits.work/

A public space-weather dashboard and email alert for GPS risk. The score is
a fixed formula over open data. A language model may rewrite the sentence
only when it repeats that score.

No login. A subscription is an email address and a region.

## Guides

- [Operation.md](docs/Operation.md): local commands, Modal serve and deploy, secrets, and what does not start a cron.
- [Manual.md](docs/Manual.md): the single page, badges, map, route, simulated storm, and subscribe. Includes screenshots.
- [Tech_Stack.md](docs/Tech_Stack.md): serverless layout, the snapshot, the risk weights, and the pipeline study.

Recorded live checks from 2026-10-29 are in [sandbox/results](sandbox/results/README.md).

## What it does

Every 15 minutes the deployed service reads ten open-data providers and
stores one snapshot. The page shows Kp, the 3-day forecast, the strongest
recent flare, a map, and a driving-route check. Subscribers get one daily
digest and an extra message when the storm rule trips.

The score is 10 points per Kp (current or forecast maximum, whichever is
larger), plus 15 for an M-class flare, 25 for an X-class flare, 20 if an
Earth-arrival CME is listed, and 10 if a supplied local TEC value is at
least 50 TECU. Under 40 is LOW, under 70 is MODERATE, and 70 or more is
CRITICAL. The model does not calculate these numbers.

If DONKI or the TEC feed is missing, the snapshot is marked degraded and the
SWPC readings still drive the score and the mail batch.

## Pipeline choice

Six designs were scored on 2026-10-26. The weights were GPS fidelity 25%,
lead time 20%, location and route specificity 15%, missing-feed behavior
15%, simplicity 10%, cost and keys 10%, and explainability 5%.

The adopted design is the layered hybrid (P4, weighted 4.60): SWPC indices,
DONKI events, TEC, and the Dst/GFZ cross-check. TEC without DONKI (P2, 3.65)
is the fallback. SWPC alone (P1, 3.50) is the floor. Letting the model pick
the number (P5, 2.35) was rejected. The OMNI science archive (P6, 2.65)
stays off the live path. Details and the grid are in
[Tech_Stack.md](docs/Tech_Stack.md) and `pipeline-study-scorecard.csv`.

DONKI is read from `https://ccmc.gsfc.nasa.gov/DONKI-API/get/` with no API
key. `NASA_API_KEY` is still kept for a later client. That host timed out
from Ontario and answered from a Virginia container, so only the DONKI fetch
is pinned to a US Modal region.

## Run

```bash
uv run python -m unittest discover -s backend/tests
uv run python -m backend.run_local
cd frontend && npm install && npm run dev
```

Deploy and the Modal URL are in [Operation.md](docs/Operation.md). The design
record is [implementation.md](docs/implementation.md).

## Acknowledgements

Thanks to Meta, Baseten, and Modal for the credits that made this project possible.
