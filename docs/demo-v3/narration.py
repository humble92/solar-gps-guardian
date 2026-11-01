"""Narration for docs/hackathon-demo-v3.mp4.

Each line is (subtitle text, spoken text). The spoken text spells out
acronyms so the TTS reads them letter by letter. Every line is rendered
on its own so subtitle timing is exact.

Writes audio/<scene>_<n>.wav and audio/timeline.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SCENES = [
    ("hook", [
        ("May 10th, 2024.", "May tenth, twenty twenty-four."),
        ("The strongest solar storm in over twenty years hits Earth.",
         "The strongest solar storm in over twenty years hits Earth."),
        ("Auroras glow as far south as Florida.", "Auroras glow as far south as Florida."),
        ("And in the middle of planting season, farmers watch their GPS-guided tractors drift off line, and park them.",
         "And in the middle of planting season, farmers watch their G P S guided tractors drift off line... and park them."),
    ]),
    ("problem", [
        ("GPS works by timing radio signals from satellites.",
         "G P S works by timing radio signals from satellites."),
        ("On the way down, they pass through a layer of electrically charged air, high above us.",
         "On the way down, they pass through a layer of electrically charged air, high above us."),
        ("When the Sun erupts, that layer churns, the signals bend, and your position quietly drifts.",
         "When the Sun erupts, that layer churns, the signals bend, and your position quietly drifts."),
        ("Warnings exist, but they're written for scientists, with one number for the entire planet.",
         "Warnings exist, but they're written for scientists. With one number, for the entire planet."),
    ]),
    ("insight", [
        ("But a solar storm doesn't hit everywhere equally.",
         "But a solar storm doesn't hit everywhere equally."),
        ("It's strongest in the ring where auroras glow, and that ring moves toward the equator as a storm grows.",
         "It's strongest in the ring where auroras glow. And that ring moves toward the equator, as a storm grows."),
        ("A flare only disturbs the side of Earth facing the Sun, and only while it lasts.",
         "A flare only disturbs the side of Earth facing the Sun, and only while it lasts."),
        ("And the charged layer is thicker over some places than others.",
         "And the charged layer is thicker over some places than others."),
        ("One global number is like a forecast with one temperature for the whole planet.",
         "One global number is like a weather forecast with one temperature, for the whole planet."),
        ("Solar-GPS-Guardian turns that global data into a GPS risk score for where you actually are.",
         "Solar G P S Guardian turns that global data into a G P S risk score, for where you actually are."),
    ]),
    ("dashboard", [
        ("Here's the live site. No login, no app.", "Here's the live site. No login. No app."),
        ("Every fifteen minutes it gathers free public data from NASA, NOAA and others.",
         "Every fifteen minutes, it gathers free public data from NASA, Noah, and others."),
        ("At the top, one plain answer: low, moderate, or critical, for your exact spot.",
         "At the top, one plain answer. Low, moderate, or critical. For your exact spot."),
        ("Below it, the evidence: the storm level on a 0 to 9 scale, the 3-day forecast, and the strongest recent flare.",
         "Below it, the evidence. The storm level on a zero to nine scale, the three day forecast, and the strongest recent flare."),
    ]),
    ("route", [
        ("Planning a drive? Type two places.", "Planning a drive? Type two places."),
        ("It checks points all along the road, because the risk can change along the way.",
         "It checks points all along the road, because the risk can change along the way."),
        ("The riskiest point decides the color. A calm stretch never hides a dangerous one.",
         "The riskiest point decides the color. A calm stretch never hides a dangerous one."),
    ]),
    ("storm", [
        ("So what would a real superstorm look like? Press simulate.",
         "So what would a real superstorm look like? Press simulate."),
        ("Storm level 8 out of 9. A major flare. A cloud of solar plasma on its way.",
         "Storm level, eight out of nine. A major flare. A cloud of solar plasma, on its way."),
        ("100 out of 100. Critical.", "One hundred, out of one hundred. Critical."),
        ("Press again, and that storm is laid over a real drive, point by point.",
         "Press again, and that storm is laid over a real drive, point by point."),
        ("That's when a fleet should stop trusting GPS alone.",
         "That's when a fleet should stop trusting G P S alone."),
    ]),
    ("alerts", [
        ("You don't have to keep checking. Leave an email and a region. No account.",
         "You don't have to keep checking. Leave an email and a region. No account."),
        ("You get a daily summary, and an alarm only when your area turns critical.",
         "You get a daily summary, and an alarm only when your area turns critical."),
        ("And each month, AI writes a short recap of last month's space weather, from the recorded numbers.",
         "And each month, A I writes a short recap of last month's space weather, from the recorded numbers."),
    ]),
    ("trust", [
        ("And you can trust the number. It comes from a simple, published formula, not from AI.",
         "And you can trust the number. It comes from a simple, published formula. Not from A I."),
        ("Each storm level adds points. A big flare in progress and incoming plasma add more.",
         "Each storm level adds points. A big flare in progress, and incoming plasma, add more."),
        ("AI only puts the result into words. It never changes it.",
         "A I only puts the result into words. It never changes it."),
        ("If a data source goes down, the page says so, and keeps working with what it has, instead of guessing.",
         "If a data source goes down, the page says so, and keeps working with what it has, instead of guessing."),
    ]),
    ("close", [
        ("The next storm is already on its way.", "The next storm is already on its way."),
        ("Solar-GPS-Guardian. Know before your GPS does.",
         "Solar G P S Guardian. Know before your G P S does."),
    ]),
]

VOICE = "af_heart"
SPEED = 1.0
LINE_GAP = 0.35  # seconds of silence after each line inside a scene


def main(models_dir):
    from kokoro_onnx import EspeakConfig, Kokoro
    # espeak-ng rejects long data paths; ~/.cache/esng links to espeakng_loader.
    esng = Path.home() / ".cache" / "esng"
    tts = Kokoro(str(Path(models_dir) / "kokoro-v1.0.onnx"), str(Path(models_dir) / "voices-v1.0.bin"),
                 espeak_config=EspeakConfig(lib_path=str(esng / "libespeak-ng.dylib"),
                                            data_path=str(esng / "espeak-ng-data")))
    out = Path(__file__).parent / "audio"
    out.mkdir(exist_ok=True)
    timeline = []
    for scene, lines in SCENES:
        entries = []
        t = 0.0
        for n, (sub, spoken) in enumerate(lines):
            samples, sr = tts.create(spoken, voice=VOICE, speed=SPEED, lang="en-us")
            samples = np.asarray(samples, dtype=np.float32)
            # trim leading/trailing near-silence so gaps are controlled here
            idx = np.where(np.abs(samples) > 0.01)[0]
            if len(idx):
                samples = samples[max(0, idx[0] - int(0.03 * sr)):idx[-1] + int(0.08 * sr)]
            path = out / f"{scene}_{n}.wav"
            sf.write(path, samples, sr)
            dur = len(samples) / sr
            entries.append({"file": path.name, "start": round(t, 3), "dur": round(dur, 3), "text": sub})
            t += dur + LINE_GAP
        timeline.append({"scene": scene, "lines": entries, "speech": round(t - LINE_GAP, 3)})
        print(f"{scene:10s} {t - LINE_GAP:6.2f}s")
    (out / "timeline.json").write_text(json.dumps(timeline, indent=1))
    print("total speech", round(sum(s["speech"] for s in timeline), 2))


if __name__ == "__main__":
    main(sys.argv[1])
