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


def _secret():
    return os.environ.get("UNSUBSCRIBE_SECRET", "dev-secret-change-me").encode()


def sign(email):
    return hmac.new(_secret(), email.encode(), hashlib.sha256).hexdigest()[:24]


def verify(email, token):
    return hmac.compare_digest(sign(email), token or "")


def digest_for(sub, snapshot):
    r = risk_mod.assess(snapshot)
    body = (
        f"Solar-GPS-Guardian daily digest for {sub.get('region_name') or 'your region'}\n"
        f"Generated: {snapshot.get('fetched_at')}\n"
        f"GPS risk: {r['level']} ({r['score']}/100)\n"
        f"Kp now {snapshot.get('now', {}).get('kp')} | forecast max Kp "
        f"{snapshot.get('forecast_3d', {}).get('max_kp')} | solar wind "
        f"{snapshot.get('now', {}).get('sw_speed')} km/s, Bz "
        f"{snapshot.get('now', {}).get('bz_gsm')} nT\n"
        f"{r['advisory']}\n"
    )
    if snapshot.get("degraded"):
        body += "(Note: degraded mode - SWPC baseline only.)\n"
    tok = sign(sub["email"])
    body += (f"\nUnsubscribe: /unsubscribe?email={sub['email']}&token={tok}\n")
    return "Solar wind daily digest", body


def storm_triggered(snapshot):
    r = risk_mod.assess(snapshot)
    g = snapshot.get("now", {}).get("g_scale") or {}
    try:
        gnum = int(g.get("Scale") or 0)
    except ValueError:
        gnum = 0
    return r["level"] in ("MODERATE", "CRITICAL") or gnum >= 1, r


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


def run_batch(store, snapshot, kind="daily", dry_dir=None, force=False):
    """kind: 'daily' (all subscribers) or 'storm' (only when triggered)."""
    if kind == "storm":
        trig, r = storm_triggered(snapshot)
        if not trig and not force:
            return {"sent": 0, "skipped": "not triggered", "level": r["level"]}
        event_key = f"{snapshot.get('fetched_at', '')[:13]}-{r['level']}"
    else:
        event_key = snapshot.get("fetched_at", "")[:10]
    sent, paths = 0, []
    for sub in store.list_active():
        email = sub["email"]
        if not force and store.already_sent(email, kind, event_key):
            continue
        subject, body = digest_for(sub, snapshot)
        paths.append(deliver(email, subject, body, dry_dir=dry_dir))
        store.log_sent(email, kind, event_key)
        sent += 1
    return {"sent": sent, "event_key": event_key, "out": paths}
