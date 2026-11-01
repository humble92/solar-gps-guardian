"""Synthesize the score and SFX, then mix them under the narration.

Everything is generated here (no licensed samples). Reads work/plan.json
and work/live_events.json; writes work/mix.wav (48 kHz stereo).
"""
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

HERE = Path(__file__).parent
WORK = HERE / "work"
SR = 48000
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(3)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


NOTE = {n: i for i, n in enumerate("C C# D D# E F F# G G# A A# B".split())}


def m(name):  # "D3" -> midi
    return 12 * (int(name[-1]) + 1) + NOTE[name[:-1]]


CHORDS = {  # voicings, low to high
    "Dm": ["D3", "A3", "D4", "F4", "A4"], "Bb": ["A#2", "F3", "A#3", "D4", "F4"],
    "F": ["F2", "C3", "F3", "A3", "C4"], "C": ["C3", "G3", "C4", "E4", "G4"],
    "Gm": ["G2", "D3", "G3", "A#3", "D4"], "A": ["A2", "E3", "A3", "C#4", "E4"],
    "Dsus": ["D3", "A3", "D4", "E4", "A4"], "D": ["D3", "A3", "D4", "F#4", "A4", "E5"],
}


def lp(x, fc, order=2):
    return sosfilt(butter(order, min(fc, SR / 2 - 100) / (SR / 2), "low", output="sos"), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc / (SR / 2), "high", output="sos"), x)


def bp(x, lo, hi):
    return sosfilt(butter(2, [lo / (SR / 2), hi / (SR / 2)], "band", output="sos"), x)


def env(n, a, r, sustain=1.0):
    e = np.ones(n) * sustain
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, sustain, na) if na < n else np.linspace(0, sustain, n)[:na]
    if nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def saw(f, n, detune=0.0):
    t = np.arange(n) / SR
    ph = (t * f * (1 + detune) + rng.random()) % 1.0
    return 2 * ph - 1


def sine(f, n, phase=0.0):
    return np.sin(2 * np.pi * f * np.arange(n) / SR + phase)


class Track:
    def __init__(self, dur):
        self.n = int(dur * SR) + SR * 4
        self.L = np.zeros(self.n)
        self.R = np.zeros(self.n)

    def add(self, t, x, gain=1.0, pan=0.0):
        i = int(t * SR)
        if i >= self.n or i + len(x) <= 0:
            return
        if i < 0:
            x, i = x[-i:], 0
        x = x[: self.n - i] * gain
        self.L[i:i + len(x)] += x * np.sqrt((1 - pan) / 2)
        self.R[i:i + len(x)] += x * np.sqrt((1 + pan) / 2)

    def stereo(self):
        return np.stack([self.L, self.R], 1)


# ---------------- instruments ----------------
def pad(chord, dur, bright=1800):
    n = int((dur + 1.6) * SR)
    x = np.zeros(n)
    for name in CHORDS[chord] if isinstance(chord, str) else chord:
        f = hz(m(name))
        for d in (-0.004, 0.0, 0.005):
            x += saw(f, n, d)
    x = lp(x, bright, 2) / 12
    return x * env(n, 0.9, 1.6)


def pluck(name, dur=0.5, bright=3000):
    n = int((dur + 0.3) * SR)
    f = hz(m(name))
    x = 0.7 * sine(f, n) + 0.3 * saw(f, n)
    x = lp(x, bright) * np.exp(-np.arange(n) / SR * 6)
    return x * env(n, 0.004, 0.08)


def bass(name, dur):
    n = int(dur * SR)
    f = hz(m(name))
    x = 0.8 * sine(f, n) + 0.35 * lp(saw(f, n), 500)
    return x * env(n, 0.01, 0.08)


def kick(level=1.0):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 28)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    return x * level


def hat(level=1.0, decay=40):
    n = int(0.12 * SR)
    x = hp(rng.standard_normal(n), 7000) * np.exp(-np.arange(n) / SR * decay)
    return x * 0.25 * level


def boom(length=3.0):
    n = int(length * SR)
    t = np.arange(n) / SR
    f = 30 + 70 * np.exp(-t * 6)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    x += lp(rng.standard_normal(n), 900) * np.exp(-t * 4) * 0.5
    return x


def riser(length):
    n = int(length * SR)
    t = np.arange(n) / SR
    k = t / length
    noise = rng.standard_normal(n)
    # sweep: blend progressively brighter filtered noise
    x = lp(noise, 400) * (1 - k) + lp(noise, 6000) * k
    f = 110 * 2 ** (k * 2)
    x += 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR)
    return x * k ** 2.2 * 0.6


def whoosh(length=0.7, lo=300, hi=4000):
    n = int(length * SR)
    k = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    x = bp(noise, lo, hi) * np.sin(np.pi * k) ** 2
    return x * 0.5


def click(level=1.0):
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    x = (sine(2600, n) * 0.5 + hp(rng.standard_normal(n), 2000) * 0.5) * np.exp(-t * 300)
    return x * level


def key():
    n = int(0.025 * SR)
    t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 1500, 6000) * np.exp(-t * 400)
    return x * (0.25 + 0.15 * rng.random())


def ding(name="A5", level=1.0):
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    f = hz(m(name))
    x = (sine(f, n) + 0.4 * sine(2 * f, n) + 0.15 * sine(3.01 * f, n)) * np.exp(-t * 3.2)
    return x * env(n, 0.003, 0.2) * 0.35 * level


def alarm(cycles=3):
    seg = int(0.22 * SR)
    parts = []
    for i in range(cycles * 2):
        f = 880 if i % 2 == 0 else 660
        x = np.tanh(3 * sine(f, seg)) * env(seg, 0.01, 0.04)
        parts.append(lp(x, 3500))
    return np.concatenate(parts) * 0.35


def glitch(length=0.25):
    n = int(length * SR)
    x = np.sign(sine(rng.integers(300, 2400), n)) * (rng.random(n) > 0.3)
    return lp(x, 5000) * env(n, 0.002, 0.05) * 0.12


def error_tone():
    seg = int(0.16 * SR)
    a = np.tanh(2 * sine(330, seg)) * env(seg, 0.005, 0.03)
    b = np.tanh(2 * sine(247, seg * 2)) * env(seg * 2, 0.005, 0.1)
    return lp(np.concatenate([a, b]), 2500) * 0.3


def heartbeat():
    return np.concatenate([kick(0.8), np.zeros(int(0.05 * SR))])[: int(0.5 * SR)]


def reverb(x, secs=2.6, wet=0.28):
    n = int(secs * SR)
    t = np.arange(n) / SR
    ir_l = rng.standard_normal(n) * np.exp(-t * 3.0 / secs * 2.2)
    ir_r = rng.standard_normal(n) * np.exp(-t * 3.0 / secs * 2.2)
    ir_l, ir_r = lp(ir_l, 5000), lp(ir_r, 5000)
    ir_l /= np.sqrt(np.sum(ir_l ** 2)); ir_r /= np.sqrt(np.sum(ir_r ** 2))
    out = np.empty_like(x)
    out[:, 0] = x[:, 0] + wet * fftconvolve(x[:, 0], ir_l)[: len(x)]
    out[:, 1] = x[:, 1] + wet * fftconvolve(x[:, 1], ir_r)[: len(x)]
    return out


# ---------------- arrangement ----------------
ARP = [0, 2, 3, 4, 3, 2, 1, 2]  # indices into the chord voicing, 8ths


def section(tr, t0, t1, chords, *, pad_g=0.0, arp_g=0.0, bass_g=0.0, kick_g=0.0, hat_g=0.0,
            bright=1800, arp_oct=1, fade_in=0.0):
    t, bar = t0, 0
    while t < t1 - 0.05:
        c = chords[bar % len(chords)]
        d = min(BAR, t1 - t)
        voicing = CHORDS[c]
        if pad_g:
            tr.add(t, pad(c, d, bright), pad_g)
        for i in range(8):
            tt = t + i * BEAT / 2
            if tt >= t1:
                break
            ramp = min(1.0, (tt - t0) / fade_in) if fade_in else 1.0
            if arp_g:
                nm = voicing[ARP[i] % len(voicing)]
                nm = nm[:-1] + str(int(nm[-1]) + arp_oct)
                tr.add(tt, pluck(nm, 0.4), arp_g * ramp, pan=0.35 if i % 2 else -0.35)
            if hat_g and i % 2 == 1:
                tr.add(tt, hat(), hat_g * ramp, pan=0.2)
            if kick_g and i % 4 == 0:
                tr.add(tt, kick(), kick_g * ramp)
            if bass_g and i % 2 == 0:
                root = voicing[0]
                tr.add(tt, bass(root[:-1] + str(int(root[-1]) - 1), BEAT * 0.9), bass_g * ramp)
        t += BAR
        bar += 1


def drone(tr, t0, t1, notes=("D2", "A2"), g=0.18, cutoff=600):
    n = int((t1 - t0) * SR)
    x = np.zeros(n)
    for nm in notes:
        x += saw(hz(m(nm)), n, 0.002) + saw(hz(m(nm)), n, -0.003)
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.15 * np.arange(n) / SR)
    x = lp(x, cutoff) * lfo
    tr.add(t0, x * env(n, 1.5, 1.2), g / len(notes))


def wind(tr, t0, t1, g=0.12):
    n = int((t1 - t0) * SR)
    k = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 200, 1200) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.21 * k))
    tr.add(t0, x * env(n, 2.0, 1.5), g)


def build(plan, events):
    P = {s["scene"]: s for s in plan["scenes"]}
    L = lambda sc, i: P[sc]["lines"][i]["start"]
    total = plan["total"]
    mus, fx = Track(total), Track(total)

    # HOOK
    h = P["hook"]
    drone(mus, 0, L("hook", 3) + 0.3, ("D1", "A1", "D2"), 0.5, 500)
    wind(mus, 0, L("hook", 2), 0.10)
    fx.add(2.0, boom(4), 0.55)
    fx.add(2.2, whoosh(1.6, 200, 2500), 0.6)
    fx.add(L("hook", 1) - 2.0, riser(2.0), 0.55)
    fx.add(L("hook", 1), boom(3), 0.5)
    fx.add(L("hook", 2) - 0.4, whoosh(0.9, 400, 6000), 0.5)
    mus.add(L("hook", 2), pad(["D4", "F#4", "A4", "C#5", "E5"], L("hook", 3) - L("hook", 2) + 0.5, 3500), 0.35)
    for i in range(10):
        nm = ["A5", "C#6", "E6", "F#6", "A6"][i % 5]
        mus.add(L("hook", 2) + 0.15 + i * 0.27, ding(nm, 0.5), 0.5, pan=(-1) ** i * 0.5)
    fx.add(L("hook", 3) - 0.4, whoosh(0.9, 300, 4000), 0.5)
    tick_end = h["end"] - 1.0
    t = L("hook", 3)
    while t < tick_end:  # tension ticks + pulsing low D
        k = (t - L("hook", 3)) / (tick_end - L("hook", 3))
        mus.add(t, hat(1.0, 90), 0.5 + 0.6 * k, pan=0.3)
        mus.add(t, bass("D1", BEAT / 2 * 0.8), 0.18 + 0.3 * k)
        t += BEAT / 2
    drone(mus, L("hook", 3), tick_end, ("D2", "D#2"), 0.25, 700)
    for dt in (2.6, 3.4, 4.2):
        fx.add(L("hook", 3) + dt, error_tone(), 0.45)

    # PROBLEM
    p = P["problem"]
    fx.add(p["start"] - 0.25, whoosh(0.8), 0.45)
    section(mus, p["start"], L("problem", 3), ["Dm", "Bb", "Gm", "A"], pad_g=0.65, arp_g=0.21, bright=1400, fade_in=2.5)
    churn_n = int((L("problem", 3) - L("problem", 2)) * SR)
    fx.add(L("problem", 2), bp(rng.standard_normal(churn_n), 800, 3000) * (rng.random(churn_n) > 0.97) * env(churn_n, 1, 1), 0.25)
    j0 = L("problem", 3)
    for i in range(14):
        fx.add(j0 + i * 0.07 + 0.05, glitch(), 0.8, pan=rng.uniform(-0.7, 0.7))
    drone(mus, j0, p["end"] + 0.3, ("D2", "A2"), 0.4, 500)
    fx.add(j0 + 2.0, riser(1.4), 0.4)
    fx.add(j0 + 3.4, boom(2.5), 0.55)

    # INSIGHT
    s = P["insight"]
    fx.add(s["start"] - 0.25, whoosh(0.8), 0.45)
    section(mus, s["start"], L("insight", 5) - 0.05, ["Bb", "F", "C", "Dm"], pad_g=0.45, arp_g=0.15, kick_g=0.0, bright=2200, fade_in=2.0)
    section(mus, L("insight", 3), L("insight", 5) - 0.05, ["C", "Dm"], kick_g=0.3, hat_g=0.25, fade_in=3)
    for i, nm in ((1, "A5"), (2, "C#6"), (3, "E6")):
        fx.add(L("insight", i), ding(nm), 0.7)
    fx.add(L("insight", 4) + 2.2, whoosh(0.4, 1500, 8000), 0.5)
    fx.add(L("insight", 5) - 2.0, riser(2.0), 0.5)
    fx.add(L("insight", 5), boom(2.5), 0.4)
    section(mus, L("insight", 5), s["end"], ["F", "C"], pad_g=0.5, arp_g=0.18, kick_g=0.45, hat_g=0.35, bass_g=0.25, bright=3000)
    fx.add(L("insight", 5) + 1.6, ding("D6"), 0.6)

    # LIVE: dashboard + route
    d, r, st = P["dashboard"], P["route"], P["storm"]
    fx.add(d["start"] - 0.25, whoosh(0.8), 0.45)
    section(mus, d["start"], st["start"] + 2.5, ["Dm", "Bb", "F", "C"], pad_g=0.38, arp_g=0.14, kick_g=0.38, hat_g=0.25, bass_g=0.22, bright=2400)

    # STORM
    on = next((e["t"] for e in events if e["kind"] == "storm_on"), L("storm", 0) + 3.0)
    fx.add(on - 2.3, riser(2.3), 0.55)
    fx.add(on, boom(4), 0.75)
    fx.add(on, whoosh(1.2, 100, 1500), 0.5)
    storm_end = P["alerts"]["start"] + 0.4
    drone(mus, on, storm_end, ("D1", "A1", "D#2"), 0.5, 450)
    t = on + 0.5
    while t < storm_end - 0.4:
        k = min(1.0, (t - on) / 9)
        mus.add(t, bass("D1", BEAT / 4 * 0.8), 0.22 + 0.2 * k)
        if (t - on) % BEAT < BEAT / 4 - 1e-3:
            mus.add(t, heartbeat(), 0.45)
        t += BEAT / 4
    section(mus, on + 0.5, storm_end, ["Dm", "Dm", "Bb", "A"], pad_g=0.32, bright=900)
    crit = L("storm", 2)
    fx.add(crit - 0.05, alarm(3), 0.55)
    fx.add(crit - 0.05, boom(2.0), 0.4)
    done = next((e["t"] for e in events if e["kind"] == "route_storm_done"), L("storm", 3) + 2)
    fx.add(done, boom(2.0), 0.45)
    fx.add(done, ding("D#5", 0.8), 0.5)

    # ALERTS
    a = P["alerts"]
    fx.add(a["start"], whoosh(1.0, 200, 3000), 0.4)
    section(mus, a["start"] + 0.3, a["end"], ["F", "C", "Dm", "Bb"], pad_g=0.65, arp_g=0.22, hat_g=0.28, kick_g=0.25, bright=2600, fade_in=2)

    # TRUST
    tr_ = P["trust"]
    fx.add(tr_["start"] - 0.25, whoosh(0.8), 0.45)
    section(mus, tr_["start"], tr_["end"] - 0.6, ["Bb", "F", "C", "Dm"], pad_g=0.42, arp_g=0.14, kick_g=0.3, hat_g=0.2, bass_g=0.2, bright=2200, fade_in=2)
    for i in range(4):
        fx.add(L("trust", 1) + i * 0.6, click(0.8), 0.6)
    fx.add(L("trust", 2) + 1.6, click(1.0), 0.8)
    fx.add(L("trust", 2) + 1.6, ding("A4"), 0.5)
    fx.add(L("trust", 3) + 1.4, error_tone(), 0.55)
    fx.add(L("trust", 3) + 3.2, ding("E6"), 0.5)

    # CLOSE
    c = P["close"]
    fx.add(c["start"] - 0.25, whoosh(1.0), 0.45)
    drone(mus, c["start"], L("close", 1), ("D2", "A2"), 0.35, 700)
    hit = L("close", 1) - 0.2
    fx.add(hit - 2.4, riser(2.4), 0.55)
    fx.add(hit, boom(4), 0.6)
    mus.add(hit, pad("D", c["end"] - hit, 4000), 0.75)
    mus.add(hit, bass("D1", c["end"] - hit) * np.exp(-np.arange(int((c["end"] - hit) * SR)) / SR * 0.4), 0.35)
    for i in range(14):
        nm = ["D6", "F#6", "A6", "E6", "A5"][i % 5]
        mus.add(hit + 0.2 + i * 0.32, ding(nm, 0.6), 0.45, pan=(-1) ** i * 0.6)

    # UI SFX from the live take
    for e in events:
        if e["kind"] == "click":
            fx.add(e["t"], click(), 0.55)
        elif e["kind"] == "key":
            fx.add(e["t"], key(), 0.6, pan=0.1)
        elif e["kind"] == "whoosh":
            fx.add(e["t"], whoosh(0.9, 500, 5000), 0.18)
    return mus, fx, total


def narration(plan):
    tr = Track(plan["total"])
    for s in plan["scenes"]:
        for ln in s["lines"]:
            x, sr = sf.read(HERE / "audio" / ln["file"])
            if sr != SR:
                x = resample_poly(x, SR, sr)
            tr.add(ln["start"], x, 1.0)
    return tr


def main():
    plan = json.loads((WORK / "plan.json").read_text())
    ev_path = WORK / "live_events.json"
    events = json.loads(ev_path.read_text()) if ev_path.exists() else []
    mus, fx, total = build(plan, events)
    voice = narration(plan).stereo()
    music = reverb(mus.stereo(), 2.8, 0.35)
    sfx = reverb(fx.stereo(), 1.8, 0.18)
    # duck music under the voice (smoothed speech envelope)
    e = np.abs(voice[:, 0])
    win = int(0.25 * SR)
    e = np.convolve(e, np.ones(win) / win, mode="same")
    speaking = np.clip(e / 0.02, 0, 1)
    speaking = np.convolve(speaking, np.ones(int(0.4 * SR)) / int(0.4 * SR), mode="same")
    duck = 1 - 0.72 * speaking
    music *= (duck * 0.32)[:, None]
    mix = voice * 1.0 + music + sfx * 0.45 * (1 - 0.4 * speaking)[:, None]
    n = int(total * SR)
    mix = mix[:n]
    fade = int(0.8 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix /= max(1.0, np.max(np.abs(mix)) / 0.95)
    sf.write(WORK / "mix.wav", mix.astype(np.float32), SR)
    sf.write(WORK / "music_only.wav", (mix - voice[:n]).astype(np.float32), SR)
    print("mix.wav", round(n / SR, 2), "s")


if __name__ == "__main__":
    main()
