"""Provider contract for open-data sources (see docs/implementation.md section 3.2).

A provider is a plain module defining:
  ID: str
  fetch(params, http) -> raw       # network only, via shared http helper
  normalize(raw) -> fragment dict  # typed fragment for the snapshot
  stale_after(params) -> seconds   # optional; defaults to 1800

Providers must stay framework-free (no Modal/LLM/email imports) so the whole
pipeline can be re-hosted unchanged. Failures raise ProviderError; the
pipeline runner catches per-provider and degrades gracefully.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "SolarGPSGuardian/1.0 (+hackathon)"
TIMEOUT = 30


class ProviderError(Exception):
    pass


def http_get_json(url, params=None, timeout=TIMEOUT):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ProviderError(f"GET {url}: {type(e).__name__}: {e}")


def http_get_text(url, params=None, timeout=TIMEOUT):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise ProviderError(f"GET {url}: {type(e).__name__}: {e}")


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def frag(ok=True, **kw):
    d = {"ok": ok}
    d.update(kw)
    return d
