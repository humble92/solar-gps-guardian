#!/bin/bash
# Build docs/hackathon-demo-v3.mp4 (1920x1080, ~2:57).
#
#   PY=<python with kokoro-onnx numpy scipy soundfile playwright>
#   CHROME=<chromium executable>  MODELS=<dir with kokoro-v1.0.onnx, voices-v1.0.bin>
#   ./build.sh            # everything
#   ./build.sh compose    # only re-mix audio and re-assemble
#
# Steps: narration (Kokoro TTS) -> plan -> motion scenes (canvas, frame by
# frame) -> live take of the deployed site -> synthesized score/SFX mix ->
# subtitles -> final encode.
set -euo pipefail
cd "$(dirname "$0")"
: "${PY:?set PY}"
mkdir -p work

if [ "${1:-all}" = all ]; then
  : "${CHROME:?set CHROME}" "${MODELS:?set MODELS}"
  "$PY" narration.py "$MODELS"
  python3 plan.py
  "$PY" render_motion.py "$CHROME"
  "$PY" record_live.py "$CHROME"
fi

"$PY" audio_mix.py
python3 make_subs.py

# Live take gets the same 0.35s edge fades as the canvas scenes.
LIVE_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 work/live.mp4)
ffmpeg -y -v error \
  -i work/hook.mp4 -i work/problem.mp4 -i work/insight.mp4 -i work/live.mp4 \
  -i work/trust.mp4 -i work/close.mp4 -i work/mix.wav \
  -filter_complex "\
[3:v]fade=in:st=0:d=0.35,fade=out:st=$(python3 -c "print($LIVE_DUR-0.35)"):d=0.35[lv];\
[0:v][1:v][2:v][lv][4:v][5:v]concat=n=6:v=1:a=0,fps=30,format=yuv420p,subtitles=work/subs.ass[v];\
[6:a]volume=3dB,alimiter=limit=0.89:level=false,loudnorm=I=-13:TP=-1.0:LRA=11[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart -shortest ../hackathon-demo-v3.mp4
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 ../hackathon-demo-v3.mp4
