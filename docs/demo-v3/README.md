# Demo video build

These scripts build `docs/hackathon-demo-v3.mp4`, the 3-minute demo video
(published at https://youtu.be/WcxweZub2GA). The narration, the animated
scenes, the music and the subtitles are generated; the live demo is
recorded from the production site.

## One-time setup

The video tools live in their own environment, not the project `.venv`.

```bash
uv venv --python 3.12 ~/demo-env/.venv
uv pip install --python ~/demo-env/.venv/bin/python numpy scipy soundfile kokoro-onnx playwright
mkdir -p ~/demo-env/models && cd ~/demo-env/models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
# espeak-ng rejects long data paths; narration.py reads this short copy.
cp -R ~/demo-env/.venv/lib/python3.12/site-packages/espeakng_loader ~/.cache/esng
~/demo-env/.venv/bin/python -m playwright install chromium
```

## Build

```bash
cd docs/demo-v3
export PY=~/demo-env/.venv/bin/python MODELS=~/demo-env/models
export CHROME=$($PY -c "from playwright.sync_api import sync_playwright as s; p=s().start(); print(p.chromium.executable_path); p.stop()")
./build.sh            # everything, about 15 minutes
./build.sh compose    # re-mix audio, subtitles and the final encode only
```

## What gets assembled

| Step | Script | Input | Output |
|---|---|---|---|
| 1. Narration | `narration.py` | the script inside the file, Kokoro model | `audio/*.wav`, `audio/timeline.json` |
| 2. Timing | `plan.py` | line lengths, per-scene pauses | `work/plan.json` (the master clock) |
| 3. Animated scenes | `render_motion.py` | `motion.html`, `degraded_banner.png`, the plan | `work/{hook,problem,insight,trust,close}.mp4` |
| 4. Live demo | `record_live.py` | the production site (live data), the plan | `work/live.mp4`, `work/live_events.json` (click and key times) |
| 5. Music, SFX, mix | `audio_mix.py` | narration, plan, live events | `work/mix.wav` |
| 6. Subtitles | `make_subs.py` | plan | `work/subs.ass` |
| 7. Final encode | the last ffmpeg call in `build.sh` | the six clips, the mix, the subtitles | `docs/hackathon-demo-v3.mp4` |

The animated scenes render frame by frame at 30 fps from `renderAt(t)` in
`motion.html`. The live demo is one continuous take: `record_live.py` warms
the site up with a dry run, then clicks and types on the plan's clock while
recording the screen.

## Reproducing the same video

- Steps 1, 2, 3, 5 and 6 are deterministic. Kokoro gives the same audio for
  the same text, and the music uses a fixed random seed.
- Step 4 is not. It records whatever the live site shows that day (Kp, TEC,
  scores, the newest newsletter), so a full build makes a different video.
- To rebuild the published video exactly, keep `work/live.mp4`,
  `work/live_events.json` and `audio/`, then run `./build.sh compose`.
  `work/` and `audio/` are git-ignored (about 300 MB), so back them up, or
  keep the final mp4.

## Notes for the next edit

- Keep the video under 3:00. If narration grows, trim the pauses in
  `plan.py` (`LAYOUT` and `LINE_GAP`) before cutting lines.
- If a line inside the live take (dashboard, route, storm, alerts) changes
  length, either re-record the live take or adjust that scene's `post` so
  the live segment keeps its length.
- Spoken text spells acronyms for the TTS. Letters with spaces work for
  `G P S`, `K P`, `T E C` and `C M E`, but write `AI` as one token: Kokoro
  reads `A I` as the article "a" plus "I". To check a spelling, print the
  phonemes with `kokoro_onnx.tokenizer.Tokenizer(...).phonemize(text, "en-us")`.
- Keep the DEGRADED part of the trust scene. `degraded_banner.png` is a real
  banner captured from a local run with DONKI unreachable, because
  production rarely shows DEGRADED. To recapture it, run the backend locally
  with DONKI blocked, point a local frontend build at it, and screenshot
  `.banner` at a 640-pixel-wide window with device scale 2.
- The risk code shown in the trust scene is the `CODE` array in
  `motion.html`. Update it whenever `score_for` in `backend/risk.py`
  changes.
