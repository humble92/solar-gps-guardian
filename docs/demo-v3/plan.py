"""Lay narration lines on one absolute clock -> work/plan.json.

pre/post are music-only seconds around a scene. gaps[i] adds silence after
line i, for on-screen action (typing, a click, an alarm).
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

LAYOUT = {
    "hook":      {"pre": 2.2, "post": 0.6},
    "problem":   {"pre": 0.3, "post": 0.4},
    "insight":   {"pre": 0.3, "post": 0.4},
    "dashboard": {"pre": 0.4, "post": 0.3},
    "route":     {"pre": 0.2, "post": 1.0, "gaps": {0: 2.4}},
    "storm":     {"pre": 0.3, "post": 0.6, "gaps": {0: 1.1, 2: 1.0, 3: 0.5}},
    "alerts":    {"pre": 0.3, "post": 0.1},
    "trust":     {"pre": 0.3, "post": 0.4},
    "close":     {"pre": 0.6, "post": 2.4},
}
LINE_GAP = 0.3  # silence after each narration line


def main():
    timeline = json.loads((HERE / "audio" / "timeline.json").read_text())
    t = 0.0
    scenes = []
    for s in timeline:
        cfg = LAYOUT[s["scene"]]
        start = t
        t += cfg["pre"]
        lines = []
        for i, ln in enumerate(s["lines"]):
            lines.append({"file": ln["file"], "start": round(t, 3), "dur": ln["dur"], "text": ln["text"]})
            t += ln["dur"] + LINE_GAP + cfg.get("gaps", {}).get(i, 0.0)
        t += cfg["post"] - LINE_GAP
        scenes.append({"scene": s["scene"], "start": round(start, 3), "end": round(t, 3), "lines": lines})
    plan = {"total": round(t, 3), "scenes": scenes}
    (HERE / "work").mkdir(exist_ok=True)
    (HERE / "work" / "plan.json").write_text(json.dumps(plan, indent=1))
    for s in scenes:
        print(f"{s['scene']:10s} {s['start']:7.2f} -> {s['end']:7.2f}  lines at " +
              ", ".join(f"{l['start']:.1f}" for l in s["lines"]))
    print("TOTAL", plan["total"])


if __name__ == "__main__":
    main()
