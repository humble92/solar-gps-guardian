"""Local entrypoint: run the pipeline once, persist, assess, batch dry-run.

Usage:
  python -m backend.run_local [--subscribe email:lat:lon[:name]] [--batch daily|storm]
"""
import argparse
import json
import os

from . import llm, mailer, pipeline, risk
from .store import Store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subscribe", help="email:lat:lon[:region]")
    ap.add_argument("--batch", choices=["daily", "storm"])
    ap.add_argument("--db", default=os.environ.get("GUARDIAN_DB", "data/guardian.db"))
    args = ap.parse_args()

    store = Store(args.db)
    snap = pipeline.run_pipeline()
    pipeline.persist(store, snap)
    result = llm.advisory(snap)
    print(json.dumps({"snapshot_at": snap["fetched_at"], "degraded": snap["degraded"],
                      "flags": snap["flags"], "risk": result}, indent=1)[:3000])
    if args.subscribe:
        email, lat, lon, *rest = args.subscribe.split(":")
        sid = store.subscribe(email, rest[0] if rest else "", float(lat), float(lon))
        print(f"subscribed id={sid} email={email}")
    if args.batch:
        print("batch:", mailer.run_batch(store, snap, kind=args.batch, dry_dir="data/outbox"))


if __name__ == "__main__":
    main()
