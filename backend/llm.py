"""LLM advisory: fixed numbers -> prose (Baseten primary, Fireworks fallback).

If no API keys are configured, returns the deterministic template advisory
from risk.py (product still works). The LLM receives the locked numeric
payload and must echo the score back; mismatches fall back to template.
"""
import json
import os
import urllib.request

from .risk import assess

TEMPLATE_ONLY = "template"


def _chat(base, key, model, payload):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content":
             "You are a space-weather driver advisor. Use ONLY the numbers given. "
             "Reply with one short paragraph ending with the line: SCORE: <n>"},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "max_tokens": 220,
    }).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def advisory(snapshot, tec_local=None):
    locked = assess(snapshot, tec_local=tec_local)
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
            text = _chat(base, key, model, {"risk": locked})
            if f"SCORE: {locked['score']}" in text:
                return {**locked, "advisory": text.strip(), "advisory_source": name}
        except Exception:  # noqa: BLE001 - fall through to next provider/template
            continue
    return {**locked, "advisory_source": TEMPLATE_ONLY}
