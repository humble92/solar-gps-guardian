"""work/plan.json -> work/subs.ass (narration captions + live-demo chapter tags)."""
import json
from pathlib import Path

HERE = Path(__file__).parent
WORK = HERE / "work"

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Helvetica Neue,42,&H00FFFFFF,&H00FFFFFF,&H40000000,&H40000000,1,0,0,0,100,100,0,0,3,14,0,2,260,260,46,1
Style: Tag,Helvetica Neue,30,&H0023A6F5,&H0023A6F5,&H30140F0B,&H30140F0B,1,0,0,0,100,100,2,0,3,12,0,8,40,40,26,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

TAGS = {
    "dashboard": "LIVE DEMO  ·  1  Your GPS risk, right now",
    "route": "LIVE DEMO  ·  2  Check a drive",
    "storm": "LIVE DEMO  ·  3  Superstorm simulation",
    "alerts": "LIVE DEMO  ·  4  Alerts and monthly recap",
}


def ts(t):
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    mi, s = divmod(r, 60)
    return f"{int(h)}:{int(mi):02d}:{s:05.2f}"


def main():
    plan = json.loads((WORK / "plan.json").read_text())
    ev = []
    for s in plan["scenes"]:
        if s["scene"] in TAGS:
            ev.append(f"Dialogue: 1,{ts(s['start'] + 0.3)},{ts(s['end'] - 0.1)},Tag,,0,0,0,,{{\\fad(300,200)}}{TAGS[s['scene']]}")
        for ln in s["lines"]:
            end = ln["start"] + ln["dur"] + 0.25
            ev.append(f"Dialogue: 0,{ts(ln['start'] - 0.05)},{ts(end)},Sub,,0,0,0,,{ln['text']}")
    (WORK / "subs.ass").write_text(HEADER + "\n".join(ev) + "\n")
    print(len(ev), "events")


if __name__ == "__main__":
    main()
