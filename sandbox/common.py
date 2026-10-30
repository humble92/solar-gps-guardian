"""Shared helpers for Solar-GPS-Guardian sandbox fetchers (stdlib only)."""
import datetime as _dt
import json as _json
import urllib.error as _uerr
import urllib.parse as _uparse
import urllib.request as _ureq

UA = "SolarGPSGuardian-sandbox/1.0 (+hackathon test)"
TIMEOUT = 30


class FetchError(Exception):
    pass


def fetch(url, params=None, timeout=TIMEOUT):
    """GET url -> (status, raw_bytes). Raises FetchError on failure."""
    if params:
        url = url + "?" + _uparse.urlencode(params)
    req = _ureq.Request(url, headers={"User-Agent": UA})
    try:
        with _ureq.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except _uerr.HTTPError as e:
        raise FetchError(f"HTTP {e.code} for {url}: {e.reason}")
    except Exception as e:  # noqa: BLE001 - network errors vary
        raise FetchError(f"{type(e).__name__} for {url}: {e}")


def fetch_json(url, params=None, timeout=TIMEOUT):
    _, raw = fetch(url, params, timeout)
    return _json.loads(raw.decode("utf-8"))


def fetch_text(url, params=None, timeout=TIMEOUT):
    _, raw = fetch(url, params, timeout)
    return raw.decode("utf-8", errors="replace")


def utcnow():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def header(title, url):
    print(f"\n{'=' * 70}\n{title}\n  src: {url}\n  fetched_at(utc): {utcnow()}\n{'=' * 70}")
