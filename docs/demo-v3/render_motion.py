"""Render the canvas explainer scenes in motion.html frame by frame.

usage: render_motion.py CHROME [scene ...]          -> work/<scene>.mp4
       render_motion.py CHROME --stills scene t ... -> work/still_<scene>_<t>.png
"""
import asyncio
import base64
import json
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).parent
WORK = HERE / "work"
FPS = 30
MOTION = ["hook", "problem", "insight", "trust", "close"]


def scene_info(plan, name):
    s = next(s for s in plan["scenes"] if s["scene"] == name)
    return {"name": name, "dur": round(s["end"] - s["start"], 3),
            "lines": [round(l["start"] - s["start"], 3) for l in s["lines"]]}


async def main(chrome, args):
    plan = json.loads((WORK / "plan.json").read_text())
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=chrome)
        pg = await b.new_page(viewport={"width": 1920, "height": 1080})
        await pg.goto((HERE / "motion.html").as_uri())
        await pg.evaluate("window.assetsReady")  # degraded banner image
        cdp = await pg.context.new_cdp_session(pg)

        async def grab(fmt="jpeg"):
            r = await cdp.send("Page.captureScreenshot", {"format": fmt, "quality": 92} if fmt == "jpeg" else {"format": fmt})
            return base64.b64decode(r["data"])

        if args and args[0] == "--stills":
            name, times = args[1], [float(x) for x in args[2:]]
            await pg.evaluate("s => window.SCENE = s", scene_info(plan, name))
            for t in times:
                await pg.evaluate(f"renderAt({t})")
                (WORK / f"still_{name}_{t:g}.png").write_bytes(await grab("png"))
            await b.close()
            return

        for name in args or MOTION:
            info = scene_info(plan, name)
            await pg.evaluate("s => window.SCENE = s", info)
            n = round(info["dur"] * FPS)
            ff = subprocess.Popen(
                ["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                 str(WORK / f"{name}.mp4")], stdin=subprocess.PIPE)
            for i in range(n):
                await pg.evaluate(f"renderAt({i / FPS})")
                ff.stdin.write(await grab())
            ff.stdin.close()
            ff.wait()
            print(f"{name}: {n} frames")
        await b.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
