"""Alert batch: daily regional digest + storm-triggered sends.

Modes: SMTP via env (SMTP_HOST/USER/PASS) or file outbox when unset
(dry-run; writes data/outbox/*.eml). Dedup via store.send_log. Unsubscribe
links are HMAC-signed with UNSUBSCRIBE_SECRET.
"""
import hashlib
import hmac
import os
import pathlib
import smtplib
import time
from email.message import EmailMessage

from . import risk as risk_mod
from .local_score import score_point


def _secret():
    return os.environ.get("UNSUBSCRIBE_SECRET", "dev-secret-change-me").encode()


def sign(email):
    return hmac.new(_secret(), email.encode(), hashlib.sha256).hexdigest()[:24]


def verify(email, token):
    return hmac.compare_digest(sign(email), token or "")


def digest_for(sub, snapshot, kind="daily", scored=None):
    if scored is None:
        lat, lon = sub.get("lat"), sub.get("lon")
        if lat is None or lon is None:
            scored = risk_mod.assess(snapshot)
        else:
            scored = risk_mod.assess(snapshot, lat=lat, lon=lon)
    r = scored
    region = sub.get("region_name") or "your region"
    if kind == "storm":
        subject = "Solar wind Critical Alarm"
        lead = f"Solar-GPS-Guardian critical alarm for {region}"
    else:
        subject = "Solar wind daily digest"
        lead = f"Solar-GPS-Guardian daily digest for {region}"
    where = ""
    if sub.get("lat") is not None and sub.get("lon") is not None:
        where = f"Scored for {float(sub['lat']):.2f}, {float(sub['lon']):.2f}.\n"
    body = (
        f"{lead}\n"
        f"Generated: {snapshot.get('fetched_at')}\n"
        f"GPS risk: {r['level']} ({r['score']}/100)\n"
        f"Kp now {snapshot.get('now', {}).get('kp')} | forecast max Kp "
        f"{snapshot.get('forecast_3d', {}).get('max_kp')} | solar wind "
        f"{snapshot.get('now', {}).get('sw_speed')} km/s, Bz "
        f"{snapshot.get('now', {}).get('bz_gsm')} nT\n"
        f"{r['advisory']}\n"
        f"{where}"
    )
    if snapshot.get("degraded"):
        body += "(Note: degraded mode - SWPC baseline only.)\n"
    tok = sign(sub["email"])
    body += (f"\nUnsubscribe: /unsubscribe?email={sub['email']}&token={tok}\n")
    return subject, body


def storm_triggered(snapshot):
    """Planetary CRITICAL check with no viewer location.

    The mail batch does not use this. Extra mail goes out only when that
    subscriber's local score is CRITICAL.
    """
    r = risk_mod.assess(snapshot)
    return r["level"] == "CRITICAL", r


def deliver(to, subject, body, dry_dir=None):
    host = os.environ.get("SMTP_HOST")
    if not host or dry_dir:
        d = pathlib.Path(dry_dir or "data/outbox")
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{int(time.time() * 1000)}-{to.replace('@', '_at_')}.eml"
        p.write_text(f"To: {to}\nSubject: {subject}\n\n{body}")
        return str(p)
    msg = EmailMessage()
    msg["From"] = os.environ.get("ALERT_FROM_EMAIL", os.environ.get("SMTP_USER", "alerts@localhost"))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    return "smtp"


def _score_sub(sub, snapshot, grid):
    lat, lon = sub.get("lat"), sub.get("lon")
    if lat is None or lon is None:
        return risk_mod.assess(snapshot)
    return score_point(snapshot, lat, lon, grid)


def run_batch(store, snapshot, kind="daily", dry_dir=None, force=False):
    """kind: 'daily' (everyone) or 'storm' (only subscribers whose local score is CRITICAL)."""
    grid = store.load_tec_grid()
    if kind == "storm":
        event_key = f"{snapshot.get('fetched_at', '')[:13]}-CRITICAL"
    else:
        event_key = snapshot.get("fetched_at", "")[:10]
    sent, paths = 0, []
    for sub in store.list_active():
        scored = _score_sub(sub, snapshot, grid)
        if kind == "storm" and scored["level"] != "CRITICAL" and not force:
            continue
        email = sub["email"]
        if not force and store.already_sent(email, kind, event_key):
            continue
        subject, body = digest_for(sub, snapshot, kind=kind, scored=scored)
        paths.append(deliver(email, subject, body, dry_dir=dry_dir))
        store.log_sent(email, kind, event_key)
        sent += 1
    if kind == "storm" and sent == 0:
        return {"sent": 0, "skipped": "not triggered", "level": "below CRITICAL", "out": paths}
    return {"sent": sent, "event_key": event_key, "out": paths}
