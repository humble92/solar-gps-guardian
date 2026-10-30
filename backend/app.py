"""Modal app: ingestion crons + snapshot API + alert batch (deploy-only).

Deploy from the user's machine (this sandbox cannot reach Modal's API):
  modal secret create nasa-api NASA_API_KEY=...        (kept for later; DONKI does not send it)
  modal secret create mail-smtp SMTP_HOST=... SMTP_USER=... SMTP_PASS=... UNSUBSCRIBE_SECRET=...
  modal deploy backend/app.py

Only DONKI is fetched from region="us". Measured 2026-10-26: GSFC/DONKI
fails from Canadian egress, while SWPC, Kyoto Dst, and GFZ work globally.
CDAWeb/OMNI is not on the live pipeline. Every other function uses Modal's
default region (1.0x). MODAL_REGION is logged once a container is running.
"""
import os
from pathlib import Path

import modal

# DONKI (ccmc.gsfc.nasa.gov) is the only live provider fetched from the US.
US_REGION = "us"
US_PROVIDERS = ("donki",)

app = modal.App("solar-gps-guardian")


def _ignore_shipped_source(path: Path) -> bool:
    """True means leave the file out of the container.

    Modal's default ships only .py files, which drops pipeline.json.
    Tests stay out. Deploy from the repository root so the package name
    `backend` resolves.
    """
    if "tests" in path.parts:
        return True
    return path.suffix not in {".py", ".json"}


def _with_backend(base: modal.Image) -> modal.Image:
    # /root/app.py is only the entrypoint. `import backend` needs the package.
    return base.add_local_python_source("backend", ignore=_ignore_shipped_source)


image = _with_backend(
    modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]")
)
vol = modal.Volume.from_name("guardian-data", create_if_missing=True)
# NOTE: the "llm" secret must exist before `modal deploy` (create it even
# with empty values if unused); newsletter writing skips providers whose
# key+model are both unset.
SECRETS = [modal.Secret.from_name("nasa-api"), modal.Secret.from_name("mail-smtp"),
           modal.Secret.from_name("llm")]
DB = "/data/guardian.db"


def _log_placement(stage: str, requested_region: str = "default") -> None:
    """Log requested region and where this process is actually running.

    During `modal deploy` / `modal serve` on the laptop, MODAL_REGION is
    empty because no container exists yet. Inside a container it is the
    narrow region Modal assigned.
    """
    print(
        "placement "
        f"stage={stage} "
        f"requested_region={requested_region} "
        f"us_providers={','.join(US_PROVIDERS)} "
        f"MODAL_REGION={os.environ.get('MODAL_REGION', '')} "
        f"MODAL_CLOUD_PROVIDER={os.environ.get('MODAL_CLOUD_PROVIDER', '')} "
        f"MODAL_TASK_ID={os.environ.get('MODAL_TASK_ID', '')}",
        flush=True,
    )


_log_placement("module_import", requested_region="default")


def _function_kwargs(**extra):
    opts = dict(
        image=image,
        volumes={"/data": vol},
        secrets=SECRETS,
    )
    opts.update(extra)
    return opts


def _store():
    from backend.store import Store
    return Store(DB)


def _run_pipeline():
    """Run every provider here, except US-blocked ones, which hop to the US."""
    from backend import pipeline

    def _remote(pid):
        def _fetch(env=None):
            return fetch_us_provider.remote(pid, env)
        return _fetch

    return pipeline.run_pipeline(fetchers={pid: _remote(pid) for pid in US_PROVIDERS})


# Stdlib-only image: this container exists just long enough to call DONKI.
_us_image = _with_backend(modal.Image.debian_slim(python_version="3.12"))


@app.function(image=_us_image, secrets=[modal.Secret.from_name("nasa-api")],
              region=US_REGION, timeout=300)
def fetch_us_provider(pid: str, env=None):
    _log_placement("fetch_us_provider.start", requested_region=US_REGION)
    try:
        if pid not in US_PROVIDERS:
            raise RuntimeError(f"{pid} is not a US-egress provider")
        import importlib
        mod = importlib.import_module(f"backend.providers.{pid}")
        return mod.fetch(env=env)
    finally:
        _log_placement("fetch_us_provider.end", requested_region=US_REGION)


@app.function(**_function_kwargs(timeout=300))
def ingest_once():
    _log_placement("ingest_once.start")
    try:
        snap = _run_pipeline()
        _store().save_snapshot(snap)
        vol.commit()
        return {"fetched_at": snap["fetched_at"], "degraded": snap["degraded"],
                "flags": snap["flags"]}
    finally:
        _log_placement("ingest_once.end")


@app.function(**_function_kwargs(timeout=300, schedule=modal.Period(minutes=15)))
def ingest_cron():
    _log_placement("ingest_cron.start")
    try:
        ingest_once.local()
    finally:
        _log_placement("ingest_cron.end")


@app.function(**_function_kwargs(timeout=300, schedule=modal.Cron("0 13 * * *")))
def daily_digest():
    _log_placement("daily_digest.start")
    try:
        from backend import mailer
        snap = _store().load_snapshot()
        if snap:
            mailer.run_batch(_store(), snap, kind="daily")
            vol.commit()
    finally:
        _log_placement("daily_digest.end")


@app.function(**_function_kwargs(timeout=300, schedule=modal.Period(hours=1)))
def storm_watch():
    _log_placement("storm_watch.start")
    try:
        from backend import mailer
        snap = _store().load_snapshot()
        if snap:
            mailer.run_batch(_store(), snap, kind="storm")
            vol.commit()
    finally:
        _log_placement("storm_watch.end")


@app.function(**_function_kwargs(timeout=600, schedule=modal.Cron("5 0 1 * *")))
def monthly_newsletter():
    _log_placement("monthly_newsletter.start")
    try:
        from backend import newsletter
        out = newsletter.generate(_store())
        vol.commit()
        return out
    finally:
        _log_placement("monthly_newsletter.end")


@app.function(**_function_kwargs())
@modal.asgi_app()
def api():
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from backend import llm, mailer, pipeline, risk

    _log_placement("api.build.start")

    @asynccontextmanager
    async def _lifespan(_web):
        _log_placement("api.startup")
        yield
        _log_placement("api.shutdown")

    web = FastAPI(title="Solar-GPS-Guardian", lifespan=_lifespan)
    # Browser frontend (Vercel/localhost) calls this API cross-origin.
    # Without CORS headers the browser blocks every response, so the UI
    # silently falls back to demo data. Open for the hackathon demo;
    # restrict allow_origins to the site domain for production.
    web.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @web.get("/snapshot")
    def snapshot():
        return _store().load_snapshot() or _run_pipeline()

    @web.get("/risk")
    def risk_ep():
        return llm.advisory(snapshot())

    @web.get("/health")
    def health():
        return pipeline.health_summary(snapshot())

    @web.post("/subscribe")
    def subscribe(body: dict):
        sid = _store().subscribe(body["email"], body.get("region_name", ""),
                                 float(body["lat"]), float(body["lon"]),
                                 float(body.get("radius_km", 100)))
        return {"id": sid, "unsubscribe_token": mailer.sign(body["email"])}

    @web.get("/unsubscribe")
    def unsubscribe(email: str, token: str):
        if not mailer.verify(email, token):
            return {"ok": False, "error": "bad token"}
        return {"ok": _store().unsubscribe(email)}

    @web.get("/newsletters")
    def newsletters():
        return _store().list_newsletters()

    @web.get("/newsletters/{nid}")
    def newsletter_one(nid: int):
        row = _store().get_newsletter(nid)
        if not row:
            return {"error": "not found"}
        row.pop("chart_svg", None)
        return row

    @web.get("/newsletters/{nid}/chart.svg")
    def newsletter_chart(nid: int):
        from fastapi.responses import Response
        row = _store().get_newsletter(nid)
        svg = (row or {}).get("chart_svg")
        if not svg:
            return Response(content="", media_type="image/svg+xml", status_code=404)
        return Response(content=svg, media_type="image/svg+xml")

    @web.post("/newsletters/generate")
    def newsletter_generate(body: dict):
        from backend import newsletter
        out = newsletter.generate(_store(), period=body.get("period"))
        vol.commit()
        return out

    _log_placement("api.build.end")
    return web
