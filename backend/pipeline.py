"""Pipeline runner: ordered providers -> versioned snapshot (docs/implementation.md 3.2).

Replace/reorder sources by editing pipeline.json only. Each provider runs
in isolation: a failure (or an empty, tolerated payload) never aborts the
snapshot; the fragment is marked unavailable and the service degrades.
"""
import importlib
import json
import pathlib
import time

from .providers.base import ProviderError, utcnow_iso

ROOT = pathlib.Path(__file__).parent
CONFIG = ROOT / "pipeline.json"
SNAPSHOT_VERSION = 1


def load_config(path=None):
    return json.loads(pathlib.Path(path or CONFIG).read_text())


def run_pipeline(env=None, config=None, now=None, fetchers=None):
    """fetchers maps a provider id to fetch(env) -> raw.

    Used so a blocked source (DONKI) can be fetched from a US container
    while every other provider runs in the caller's region. normalize()
    always stays in the caller.
    """
    cfg = config or load_config()
    fetchers = fetchers or {}
    fragments, health = {}, {}
    for pid in cfg.get("order", []):
        pcfg = cfg.get("providers", {}).get(pid, {})
        if not pcfg.get("enabled", True):
            health[pid] = {"ok": False, "note": "disabled"}
            continue
        t0 = time.time()
        try:
            mod = importlib.import_module(f".providers.{pid}", __package__)
            fetch = fetchers.get(pid, mod.fetch)
            raw = fetch(env)
            frag = mod.normalize(raw)
            fragments[pid] = frag
            health[pid] = {
                "ok": frag.get("ok", True),
                "latency_ms": round((time.time() - t0) * 1000),
                "stale_after": pcfg.get("stale_after", 1800),
            }
            if pid == "tec":
                fragments[pid]["available"] = frag.get("available", False)
        except Exception as e:  # noqa: BLE001 - isolate provider failures
            fragments[pid] = {"ok": False, "available": False, "error": str(e)[:200]}
            health[pid] = {"ok": False, "latency_ms": round((time.time() - t0) * 1000),
                           "error": str(e)[:120]}
    return build_snapshot(fragments, health, now=now)


def build_snapshot(fragments, health, now=None):
    rtsw = fragments.get("rtsw", {})
    kp = fragments.get("kp", {})
    fl = fragments.get("flares", {})
    f3 = fragments.get("forecast_3d", {})
    donki = fragments.get("donki", {})
    tec = fragments.get("tec", {})
    raw_grid = tec.get("grid") if isinstance(tec, dict) else None
    grid = list(raw_grid) if isinstance(raw_grid, list) else []
    if isinstance(tec, dict):
        tec.pop("grid", None)
    ov = fragments.get("ovation", {})
    raw_aurora = ov.get("grid") if isinstance(ov, dict) else None
    aurora = list(raw_aurora) if isinstance(raw_aurora, list) else []
    if isinstance(ov, dict):
        ov.pop("grid", None)
    snap = {
        "snapshot_version": SNAPSHOT_VERSION,
        "fetched_at": now or utcnow_iso(),
        "degraded": not (donki.get("ok") and tec.get("available", tec.get("ok"))),
        "flags": {
            "donki_available": bool(donki.get("ok")),
            "tec_available": bool(tec.get("available", tec.get("ok"))),
            "ovation_available": bool(ov.get("available")),
            "stale_sources": [p for p, h in health.items() if not h.get("ok")],
        },
        "now": {
            "kp": kp.get("kp"), "kp_1m": kp.get("kp_1m_estimated"),
            "g_scale": kp.get("g_scale"), "r_scale": kp.get("r_scale"),
            "sw_speed": rtsw.get("speed_km_s"), "sw_density": rtsw.get("density_cc"),
            "bz_gsm": rtsw.get("bz_gsm_nt"), "bt": rtsw.get("bt_nt"),
            "spacecraft": rtsw.get("spacecraft"),
        },
        "forecast_3d": {"max_kp": f3.get("max_kp"), "rows": f3.get("rows", []),
                        "storm_expected": f3.get("storm_expected")},
        "events": {
            "latest_flare": fl.get("latest_flare"),
            # GOES long-band flux at fetch time drives the dayside flare term.
            "xray_flux": fl.get("xray_long"), "xray_time": fl.get("xray_time"),
            "worst_flare_7d": fl.get("worst_7d_class"),
            "mx_flares_7d": fl.get("mx_flares_7d"),
            "donki_counts": donki.get("counts"),
            "cme_earth_arrivals": donki.get("earth_arrivals", []),
        },
        "tec": {"available": tec.get("available", tec.get("ok", False)),
                "latest_time": tec.get("latest_time"), "tec_max": tec.get("tec_max"),
                "grid_ref": "tec_grid:1"},
        "_tec_grid": grid,
        "aurora": {"available": bool(ov.get("available")),
                   "observation_time": ov.get("observation_time"),
                   "forecast_time": ov.get("forecast_time"),
                   "aurora_max": ov.get("aurora_max"), "grid_ref": "aurora_grid:1"},
        "_aurora_grid": aurora,
        "dst": fragments.get("dst", {}), "kp_gfz": fragments.get("kp_gfz", {}),
        "stereo": fragments.get("stereo", {}), "enlil": fragments.get("enlil", {}),
        "health": health, "fragments": fragments,
    }
    return snap


def persist(store, snap):
    """Save one planetary snapshot. Non-empty TEC and aurora grids go beside it.

    An empty grid leaves the previous cells in place so a missed tile does
    not wipe the last good lookup. The TEC grid keeps its tile time, so a
    score can tell how old it is (risk.TEC_MAX_AGE_H). The public snapshot keeps grid_ref, not
    the cells.
    """
    grid = snap.pop("_tec_grid", None)
    aurora = snap.pop("_aurora_grid", None)
    store.save_snapshot(snap)
    if grid:
        store.save_tec_grid({"time_tag": snap.get("tec", {}).get("latest_time"), "cells": grid})
    if aurora:
        store.save_aurora_grid(aurora)
    return snap


def health_summary(snapshot):
    return {pid: {"ok": h.get("ok"), "latency_ms": h.get("latency_ms")}
            for pid, h in snapshot.get("health", {}).items()}


if __name__ == "__main__":
    print(json.dumps(run_pipeline(), indent=1)[:4000])
