"""GFZ Kp nowcast (CC BY 4.0): authoritative Kp cross-check for SWPC."""
from .base import ProviderError, frag, http_get_text

ID = "kp_gfz"
URL = "https://kp.gfz.de/app/files/Kp_ap_nowcast.txt"


def fetch(env=None):
    return {"text": http_get_text(URL)}


def normalize(raw):
    lines = [ln for ln in raw.get("text", "").splitlines()
             if ln.strip() and not ln.startswith("#")]
    if not lines:
        raise ProviderError("kp_gfz: empty nowcast")
    parts = lines[-1].split()
    # Columns (tail): ... Kp ap ... ; Kp is the 8th field in GFZ layout.
    try:
        kp = float(parts[7])
    except (IndexError, ValueError):
        kp = None
    return frag(last_line=lines[-1][:160], kp=kp, license="CC BY 4.0 (GFZ)")
