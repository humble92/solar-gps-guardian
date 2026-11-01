"""Record the live site from 'dashboard' through 'alerts' as one take.

Actions are scheduled on the plan clock. Frames come from the CDP
screencast with timestamps, so the clip keeps real timing. Writes
work/live.mp4 and work/live_events.json (click/typing times for SFX).

usage: record_live.py CHROME [--no-warm]
"""
import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).parent
WORK = HERE / "work"
SITE = "https://solar-gps-guardian.ninefruits.work"
FPS = 30

# Fake cursor, spotlight and camera, injected into every page.
OVERLAY = r"""
(() => {
  const css = `
  #__cur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;
    transform:translate(-3px,-2px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.6))}
  #__rip{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;border:3px solid #f5a623;
    z-index:2147483646;pointer-events:none;opacity:0}
  #__rip.go{animation:__r .55s ease-out}
  @keyframes __r{from{opacity:1;transform:scale(.6)}to{opacity:0;transform:scale(4)}}
  #__spot{position:fixed;z-index:2147483640;pointer-events:none;border:3px solid #f5a623;border-radius:12px;
    box-shadow:0 0 0 200vmax rgba(3,6,10,.38),0 0 24px rgba(245,166,35,.6);opacity:0;transition:opacity .45s}
  body{transform-origin:0 0;transition:transform 1.1s cubic-bezier(.65,0,.35,1)}`;
  const boot = () => {
    if (document.getElementById("__cur")) return;
    const st = document.createElement("style"); st.textContent = css; document.documentElement.appendChild(st);
    const c = document.createElement("div"); c.id = "__cur";
    c.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7.5 19 2.6-7.9L21 10.6z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    const r = document.createElement("div"); r.id = "__rip";
    const s = document.createElement("div"); s.id = "__spot";
    document.documentElement.append(s, r, c);
    const p = JSON.parse(sessionStorage.getItem("__cur") || "[640,360]");
    c.style.left = p[0] + "px"; c.style.top = p[1] + "px";
    addEventListener("mousemove", e => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px";
      sessionStorage.setItem("__cur", JSON.stringify([e.clientX, e.clientY])); }, true);
    addEventListener("mousedown", e => { r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
      r.classList.remove("go"); void r.offsetWidth; r.classList.add("go"); }, true);
    // spotlight follows its element every frame (scroll and camera moves)
    const tick = () => { const el = window.__spotEl;
      if (el && el.isConnected) { const b = el.getBoundingClientRect(), pad = window.__spotPad || 8;
        Object.assign(s.style, { left: b.left - pad + "px", top: b.top - pad + "px", width: b.width + 2 * pad + "px", height: b.height + 2 * pad + "px", opacity: 1 });
      } else s.style.opacity = 0;
      requestAnimationFrame(tick); };
    tick();
  };
  window.__spot = (el, pad) => { window.__spotEl = el; window.__spotPad = pad; };
  // Zoom so el's centre lands at the viewport centre. Measured at identity.
  window.__cam = (el, scale) => {
    const b = document.body, prev = b.style.transform;
    b.style.transition = "none"; b.style.transform = "none";
    const r = el ? el.getBoundingClientRect() : null;
    b.style.transform = prev; void b.offsetWidth; b.style.transition = "";
    if (!el || scale === 1) { b.style.transform = "none"; return; }
    const cx = r.left + r.width / 2 + scrollX, cy = r.top + r.height / 2 + scrollY;
    // keep the page edges outside the viewport (no empty band after zooming)
    const bw = document.documentElement.scrollWidth, bh = document.documentElement.scrollHeight;
    const clampv = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const tx = clampv(innerWidth / 2 + scrollX - cx * scale, scrollX + innerWidth - bw * scale, scrollX);
    const ty = clampv(innerHeight / 2 + scrollY - cy * scale, scrollY + innerHeight - bh * scale, scrollY);
    b.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", boot); else boot();
})();
"""


class Take:
    def __init__(self, page, cdp, t0_abs):
        self.page, self.cdp, self.t0_abs = page, cdp, t0_abs
        self.start = None
        self.events = []

    def now(self):
        return time.time() - self.start

    async def at(self, t_abs):
        d = (t_abs - self.t0_abs) - self.now()
        if d > 0:
            await asyncio.sleep(d)
        elif d < -0.3:
            print(f"  late by {-d:.2f}s at {t_abs:.1f}")

    def log(self, kind, **kw):
        self.events.append({"t": round(self.now() + self.t0_abs, 3), "kind": kind, **kw})

    async def move(self, loc, dx=0.5, dy=0.5, steps=28):
        b = await loc.bounding_box()
        await self.page.mouse.move(b["x"] + b["width"] * dx, b["y"] + b["height"] * dy, steps=steps)

    async def click(self, loc, **kw):
        await self.move(loc, **kw)
        await asyncio.sleep(0.12)
        self.log("click")
        await self.page.mouse.down()
        await self.page.mouse.up()

    async def type(self, loc, s, delay=0.075):
        await self.click(loc)
        await self.page.keyboard.press("Meta+A")
        await self.page.keyboard.press("Backspace")
        for ch in s:
            self.log("key")
            await self.page.keyboard.type(ch)
            await asyncio.sleep(delay)

    async def spot(self, sel, pad=8):
        if sel is None:
            await self.page.evaluate("window.__spot(null)")
        else:
            await self.page.evaluate("([s,p]) => window.__spot(document.querySelector(s), p)", [sel, pad])

    async def cam(self, sel, scale):
        await self.page.evaluate("([s,k]) => window.__cam(s && document.querySelector(s), k)", [sel, scale])
        self.log("whoosh")

    async def scroll(self, y):
        await self.page.evaluate(f"window.scrollTo({{top:{y},behavior:'smooth'}})")


async def scroll_to(take, sel, offset=24):
    y = await take.page.evaluate(
        "([s,o]) => document.querySelector(s).getBoundingClientRect().top + scrollY - o", [sel, offset])
    await take.scroll(y)


async def run(take, P):
    pg = take.page
    L = lambda scene, i: P[scene]["lines"][i]["start"]
    route_btn = pg.get_by_role("button", name="Assess route")
    ghost = pg.locator("button.ghost")
    # --- dashboard ---
    await take.at(L("dashboard", 1))
    await take.move(pg.locator(".badge.live"), steps=40)
    await take.spot(".badge.live", 6)
    await take.at(L("dashboard", 2))
    await take.spot(None)
    await take.cam(".banner", 1.18)
    await asyncio.sleep(1.3)
    await take.spot(".banner .badge", 6)
    await take.at(L("dashboard", 3))
    await take.spot(None)
    await take.cam(".grid", 1.18)
    for i, dt in enumerate((0.9, 2.6, 4.3)):
        await take.at(L("dashboard", 3) + dt)
        await take.spot(f".grid .card:nth-child({i + 1})", 6)
    # --- route ---
    await take.at(P["route"]["start"])
    await take.spot(None)
    await take.cam(None, 1)
    await scroll_to(take, "section:nth-of-type(1)")  # map section to the top
    await asyncio.sleep(0.9)
    await take.type(pg.get_by_label("From"), "Toronto, ON", delay=0.06)
    await take.type(pg.get_by_label("To"), "Ottawa, ON", delay=0.08)
    await asyncio.sleep(0.25)
    await take.click(route_btn)
    take.log("route_request")
    await pg.wait_for_function(
        "() => [...document.querySelectorAll('p.muted')].some(p => p.textContent.includes('GPS risk along corridor'))",
        timeout=20000)
    take.log("route_done")
    await take.at(L("route", 1))
    await take.spot("section:nth-of-type(1) .leaflet-container", 4)
    await take.at(L("route", 2))
    await take.spot("section:nth-of-type(2) p.muted", 8)
    # --- storm ---
    await take.at(L("storm", 0) + 1.2)
    await take.spot(None)
    await take.move(ghost)
    await take.at(L("storm", 0) + 2.9)
    await take.click(ghost)
    take.log("storm_on")
    await asyncio.sleep(0.4)
    await take.scroll(0)
    await take.at(L("storm", 1) - 0.2)
    await take.cam(".grid", 1.18)
    for i, dt in enumerate((0.3, 1.6, 3.0)):
        await take.at(L("storm", 1) + dt)
        await take.spot(f".grid .card:nth-child({i + 1})", 6)
    await take.at(L("storm", 2) - 0.3)
    await take.spot(None)
    await take.cam(".banner", 1.18)
    take.log("critical", at=L("storm", 2))
    await asyncio.sleep(1.2)
    await take.spot(".banner", 6)
    await take.at(L("storm", 3) - 0.2)
    await take.spot(None)
    await take.cam(None, 1)
    await scroll_to(take, "section:nth-of-type(1)")
    await asyncio.sleep(0.8)
    await take.click(ghost)
    take.log("route_storm")
    await pg.wait_for_function(
        "() => [...document.querySelectorAll('p.muted')].some(p => p.textContent.includes('Hypothetical superstorm'))",
        timeout=20000)
    take.log("route_storm_done")
    await asyncio.sleep(0.6)
    await take.spot("section:nth-of-type(2) p.muted", 8)
    await take.at(L("storm", 4))
    await take.spot("section:nth-of-type(1) .leaflet-container", 4)
    # --- alerts ---
    await take.at(P["alerts"]["start"])
    await take.spot(None)
    await scroll_to(take, "section:nth-of-type(3)", 200)
    await asyncio.sleep(0.8)
    await take.type(pg.get_by_label("Email"), "you@example.com", delay=0.07)
    await take.move(pg.get_by_role("button", name="Subscribe"))  # shown, not pressed
    await take.spot("section:nth-of-type(3) .row", 8)
    await take.at(L("alerts", 1) + 0.3)
    await take.spot("section:nth-of-type(3) p.muted", 8)
    await take.at(L("alerts", 2) - 0.6)
    await take.spot(None)
    await take.scroll(0)
    await asyncio.sleep(0.6)
    await take.click(pg.locator(".topnav a", has_text="Newsletters"))
    await pg.wait_for_selector(".nl-item", timeout=15000)
    await asyncio.sleep(0.8)
    await take.click(pg.locator(".nl-item", has_text="2026-10"))
    await pg.wait_for_selector(".md", timeout=20000)
    await asyncio.sleep(0.9)
    await take.page.evaluate("document.querySelector('.md img').scrollIntoView({behavior: 'smooth', block: 'center'})")


async def warm(ctx):
    """Dry run so Modal, OSRM, Nominatim and the tiles are warm for the take."""
    pg = await ctx.new_page()
    await pg.goto(SITE, wait_until="networkidle", timeout=60000)
    await pg.get_by_label("To").fill("Ottawa, ON")
    await pg.get_by_role("button", name="Assess route").click()
    await pg.wait_for_function("() => document.body.innerText.includes('GPS risk along corridor')", timeout=60000)
    await pg.locator("button.ghost").click()
    await pg.locator("button.ghost").click()
    await pg.wait_for_function("() => document.body.innerText.includes('Hypothetical superstorm')", timeout=60000)
    await pg.goto(SITE + "/newsletters/2", wait_until="networkidle")
    await pg.close()


async def main(chrome, no_warm):
    plan = json.loads((WORK / "plan.json").read_text())
    P = {s["scene"]: s for s in plan["scenes"]}
    t0, t1 = P["dashboard"]["start"], P["alerts"]["end"]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=chrome)
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5,
                                  geolocation={"latitude": 43.6532, "longitude": -79.3832},
                                  permissions=["geolocation"], color_scheme="dark")
        if not no_warm:
            await warm(ctx)
            print("warm")
        await ctx.add_init_script(OVERLAY)
        pg = await ctx.new_page()
        await pg.goto(SITE, wait_until="networkidle", timeout=60000)
        await pg.wait_for_selector(".badge.live", timeout=60000)
        await pg.wait_for_function("() => !document.querySelector('.banner').textContent.includes('Scoring')")
        await pg.mouse.move(900, 500)
        await asyncio.sleep(2.0)
        cdp = await ctx.new_cdp_session(pg)
        frames = []

        def on_frame(ev):
            frames.append((ev["metadata"]["timestamp"], ev["data"]))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))
        cdp.on("Page.screencastFrame", on_frame)
        take = Take(pg, cdp, t0)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90,
                                                "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        take.start = time.time()
        await run(take, P)
        await take.at(t1)
        await cdp.send("Page.stopScreencast")
        await b.close()

    dur = t1 - t0
    fdir = WORK / "live_frames"
    fdir.mkdir(exist_ok=True)
    for f in fdir.glob("*.jpg"):
        f.unlink()
    lines = []
    frames.sort(key=lambda f: f[0])
    rel = [(ts - take.start, data) for ts, data in frames]
    rel = [(max(0.0, t), d) for t, d in rel if t < dur]
    for i, (t, data) in enumerate(rel):
        name = f"{i:05d}.jpg"
        (fdir / name).write_bytes(base64.b64decode(data))
        nxt = rel[i + 1][0] if i + 1 < len(rel) else dur
        if i == 0:
            t = 0.0
        lines.append(f"file '{name}'\nduration {max(nxt - t, 0.001):.4f}")
    lines.append(f"file '{len(rel) - 1:05d}.jpg'")
    (fdir / "list.txt").write_text("\n".join(lines) + "\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(fdir / "list.txt"),
                    "-vf", f"scale=1920:1080,fps={FPS}", "-t", f"{dur:.3f}", "-c:v", "libx264", "-crf", "16",
                    "-preset", "medium", "-pix_fmt", "yuv420p", str(WORK / "live.mp4")], check=True)
    (WORK / "live_events.json").write_text(json.dumps(take.events, indent=1))
    print(f"live.mp4 {dur:.2f}s from {len(rel)} frames, {len(take.events)} events")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], "--no-warm" in sys.argv))
