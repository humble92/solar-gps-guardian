# Operation guide

How to run and check this repository on your own machine. Nothing here
registers a cron. Scheduled jobs exist only after `modal deploy`.

## What you can run without Modal

From the repository root:

```bash
uv run python -m unittest discover -s backend/tests
```

This uses the Python standard library only. It checks parsing, the risk
formula, SQLite subscribe and mail batch behavior, and that DONKI calls the
CCMC host without an API key. There is no `pyproject.toml`. `uv run` does not
require you to activate a virtual environment first. `python3 -m unittest
discover -s backend/tests` also works.

```bash
uv run python -m backend.pipeline
```

Fetches the live providers once and prints a snapshot JSON. It does not write
the database.

```bash
uv run python -m backend.run_local
uv run python -m backend.run_local --subscribe you@example.com:43.65:-79.38:Toronto
uv run python -m backend.run_local --batch daily
```

Each command is a separate process. The default database is
`data/guardian.db`, created on first use. `--subscribe` stores one email and
region. `--batch daily` reads every active subscriber in that same database
and writes one `.eml` file per new send under `data/outbox/`. It does not
open an SMTP session, because the local command always passes a dry-run
directory. A second daily batch on the same UTC date is skipped for addresses
already recorded in `send_log`.

`run_local` does not load `.env` by itself. Export variables in the shell if
you want the process to see them.

```bash
uv run python sandbox/test_parsing.py
uv run python sandbox/run_all.py
uv run python sandbox/nasa_donki.py
```

`test_parsing.py` stays offline. `run_all.py` calls the public feeds from
this machine and prints a PASS/FAIL summary. `nasa_donki.py` is the DONKI
catalog check alone. Saved examples from 2026-10-29 are in
[sandbox/results](../sandbox/results/README.md).

The frontend does not talk to `run_local`. It only calls an HTTP base URL.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Next.js reads `frontend/.env.local`, not the
repository root `.env`. If `NEXT_PUBLIC_API_BASE` is empty, the page shows
demo numbers and does not store a subscription. See [Manual.md](Manual.md).

## DONKI and the US path

The live DONKI host is `https://ccmc.gsfc.nasa.gov/DONKI-API/get/`. It does
not take an API key. `NASA_API_KEY` remains in `.env.example` and in the
Modal secret `nasa-api` for a later client. The current fetch does not send
it. A configured key is reported as `key_tier=retained`.

From Ontario on 2026-10-29 that host timed out. A later local retry returned
11/11. A Modal run from Virginia returned 200 for every DONKI catalog, the
monthly OMNI file, and the CDAWeb home page. Because the direct path is
unreliable from this network, the deployed pipeline still fetches DONKI from
a container pinned to `region="us"`. SWPC, Kyoto, GFZ, TEC, STEREO, and Enlil
stay on Modal's default region.

`sandbox/us_fetch_modal.py` is not part of `run_all.py`. Running it with
`python` only imports the module. It does not register a schedule.

```bash
modal run sandbox/us_fetch_modal.py::fetch_once
```

This runs once in Modal's cloud and then stops. The dashboard entry for
`ingest_cron` on that ephemeral app stays stopped. `Run now` in the Modal UI
also runs the function once. It does not turn the schedule on.

```bash
modal deploy sandbox/us_fetch_modal.py
```

This is a different app (`solar-gps-guardian-us-ingest`) from
`backend/app.py`. Deploy is what attaches the 10-minute cron. Stop that app,
or deploy again without the schedule, to turn it off. There is no separate
cron switch in the dashboard.

## Deploying the product backend

Install the CLI once. This is not the project virtual environment:

```bash
uv tool install modal
modal token new
```

`modal token new` opens a browser login and writes `~/.modal.toml`. It does
not print the GitHub Actions secrets. Create those under Modal Settings,
Developer, API tokens and service users, in the `humble92` workspace. Put the
two values in GitHub as `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`.

Create the Modal secrets before serve or deploy:

```bash
modal secret create nasa-api NASA_API_KEY=...
modal secret create mail-smtp SMTP_HOST=... SMTP_USER=... SMTP_PASS=... UNSUBSCRIBE_SECRET=...
modal secret create llm BASETEN_API_KEY=... BASETEN_MODEL=... FIREWORKS_API_KEY=... FIREWORKS_MODEL=...
```

The `llm` secret must exist before every deploy (use empty values if you
have no keys yet — the code skips unset providers). Without it, newsletter
issues are written by the template fallback and carry a `(template)` suffix
in the title. After adding real keys and redeploying, regenerate the issue
in place:

```bash
curl -X POST "$API/newsletters/generate" \
  -H "Content-Type: application/json" -d '{"period":"2026-09"}'
```

The title suffix then becomes `(baseten)` or `(fireworks)` instead of
`(template)`; the same row is overwritten, no duplicate.

`modal serve` and `modal deploy` do not read the repository `.env`. Only
those secrets are injected into containers.

From the repository root, not from `backend/`:

```bash
modal serve backend/app.py
modal deploy backend/app.py
```

`from backend import ...` requires the repository root on the Python path.
`cd backend && modal deploy app.py` looks for a package that is not there.

`modal serve` keeps a temporary cloud app while the command is open. The
terminal prints an HTTPS URL. Put that URL in `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_BASE=https://the-printed-host
```

Restart `npm run dev`. The page then calls `GET /snapshot` and
`POST /subscribe` on that cloud URL. Stopping `modal serve` removes the URL.

`modal deploy backend/app.py` keeps the app `solar-gps-guardian`. Schedules
come from the code:

| Function | Schedule |
|---|---|
| `ingest_cron` | Every 15 minutes from the deploy time (`modal.Period`) |
| `storm_watch` | Every 6 hours from the deploy time (`modal.Period`). Sends only when the score is CRITICAL. |
| `daily_digest` | 13:00 UTC every day (`modal.Cron`) |

`modal.Period` schedules restart their clock on each deploy. `modal.Cron`
stays on the UTC clock. Redeploying replaces the previous schedules. No
separate cron form is required in the Modal UI.

## Monthly newsletter (manual issue)

The monthly run also comes from the code (`monthly_newsletter` at
`Cron("5 0 1 * *")`), but one issue can be published on demand without
waiting for the 1st. The default period is the last complete month, so a
manual run now and the cron run later land on different periods and never
duplicate; calling the same period twice regenerates it in place
(`period` is UNIQUE, upsert on save).

```bash
API=https://humble92--solar-gps-guardian-api.us-east.modal.run

# Publish last complete month (e.g. September when run in October)
curl -X POST "$API/newsletters/generate" \
  -H "Content-Type: application/json" -d '{}'

# Publish a named period
curl -X POST "$API/newsletters/generate" \
  -H "Content-Type: application/json" -d '{"period":"2026-09"}'

# Verify: list, body, chart
curl "$API/newsletters"
curl "$API/newsletters/1"
curl -o chart.svg "$API/newsletters/1/chart.svg"
```

The response is `{id, period, title, source, sources_ok}`. `source` is
`baseten`/`fireworks` when an LLM key is configured, otherwise `template`.
`sources_ok` reports per-source collection status (`donki` fails from
non-US networks by design; `kyoto_dst`/`gfz_kp` work globally). The rows
land in the `newsletters` table of `/data/guardian.db` on the Modal Volume,
so they survive redeploys and appear under the site's `Newsletters` menu.

Pushing `main` runs `.github/workflows/modal-deploy.yml`, which executes
`modal deploy backend/app.py`. The workflow does nothing until the two GitHub
secrets exist. The `nasa-api` and `mail-smtp` secrets must already exist in
the Modal workspace.

Container placement lines start with `placement`. On your laptop during
deploy, `MODAL_REGION` is empty. Inside a container it is the narrow region
(`us-east`, and so on). After deploy, those lines are in the Modal app logs
(`modal app logs solar-gps-guardian`), not in the deploy terminal and not in
GitHub Actions.

The Starter plan includes $30 of compute credit per month. This workload is
a 15-minute ingest, an hourly storm check, one daily mail batch, and HTTP
when the page is opened. Pinning only the DONKI fetch to `region="us"`
applies the 1.15x region multiplier to that short container.

## Vercel

Import the GitHub repository with the project root set to `frontend/`. Set
`NEXT_PUBLIC_API_BASE` to the URL printed by `modal deploy`. That variable is
baked in at build time, so change it and deploy the frontend again.

A custom domain is added after the first Vercel deploy, under Settings,
Domains. That name is the site people open. It is not the Modal API URL.
