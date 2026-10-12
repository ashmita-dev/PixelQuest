"""End-to-end browser test for the web version (real Chrome via Playwright).

    pip install playwright            # uses the installed Chrome; no browser download
    python web/tests/e2e_browser.py http://localhost:8000/ [--headed] [--shots DIR]

The "webcam" is Chrome's fake capture device playing a Y4M file rendered from
the project's SYNTHETIC test video (src/vision.py SyntheticSource: a moving
green disc plus distractors). No real camera or person is involved.
Checks: page loads without errors, keyboard controls, camera-permission denial
fallback, camera granted -> TRACKING -> ship follows the marker, diagnostics.
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from src.vision import SyntheticSource  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def make_y4m(path: Path, frames=120):
    src = SyntheticSource(realtime=False)
    with open(path, "wb") as f:
        f.write(b"YUV4MPEG2 W640 H480 F30:1 Ip A1:1 C420jpeg\n")
        for _ in range(frames):
            _, bgr = src.read()
            f.write(b"FRAME\n" + cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420).tobytes())


def js(page, expr):
    return page.evaluate(expr)


def wait_js(page, expr, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if js(page, expr):
            return True
        time.sleep(0.1)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--shots", default=None)
    a = ap.parse_args()
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    y4m = tmp / "synthetic.y4m"
    make_y4m(y4m)
    args = ["--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={y4m}", "--autoplay-policy=no-user-gesture-required"]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not a.headed, args=args)

        # ---- 1. keyboard play, camera permission NOT granted ----------------
        ctx = browser.new_context(viewport={"width": 1366, "height": 768})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        resp = page.goto(a.url, wait_until="networkidle")
        check("page loads (HTTP 200)", resp and resp.status == 200, f"status={resp.status if resp else None}")
        check("game boots to title screen", wait_js(page, "window.__pq && window.__pq.state === 'menu'"))
        check("served over secure context", js(page, "window.isSecureContext"))
        time.sleep(1.0)
        if shots:
            page.screenshot(path=str(shots / "web_menu.png"))
        page.keyboard.press("Enter")
        check("Enter starts the game", wait_js(page, "__pq.state === 'play'", 3))
        time.sleep(1.8)  # countdown
        x0 = js(page, "__pq.session.ship.x")
        page.keyboard.down("ArrowRight"); time.sleep(0.5); page.keyboard.up("ArrowRight")
        x1 = js(page, "__pq.session.ship.x")
        check("ArrowRight moves the ship", x1 > x0 + 50, f"x {x0:.0f} -> {x1:.0f}")
        y0 = js(page, "__pq.session.ship.y")
        page.keyboard.down("w"); time.sleep(0.4); page.keyboard.up("w")
        check("W moves the ship up", js(page, "__pq.session.ship.y") < y0 - 30)
        time.sleep(3)
        check("entities spawn during play", js(page, "__pq.session.entities.length") > 0,
              f"n={js(page, '__pq.session.entities.length')}")
        page.keyboard.press("p")
        check("P pauses", js(page, "__pq.state") == "pause")
        page.keyboard.press("Escape")
        check("Esc resumes", js(page, "__pq.state") == "play")
        page.keyboard.press("r")
        check("R restarts (fresh session)", js(page, "__pq.state === 'play' && __pq.session.elapsed < 0.5"))
        page.keyboard.press("m")
        check("M returns to menu", js(page, "__pq.state") == "menu")
        page.keyboard.press("c")
        check("camera denied -> DENIED status, no crash",
              wait_js(page, "__pq.cam.status === 'DENIED' || __pq.cam.status === 'NO CAMERA'", 6),
              f"status={js(page, '__pq.cam.status')}")
        check("denial shows a toast", js(page, "__pq.toasts.some(t => /keyboard still works/i.test(t.msg))"))
        page.keyboard.press("Enter")
        time.sleep(1.8)
        x0 = js(page, "__pq.session.ship.x")
        page.keyboard.down("ArrowLeft"); time.sleep(0.4); page.keyboard.up("ArrowLeft")
        check("keyboard still works after camera denial", js(page, "__pq.session.ship.x") < x0 - 40)
        # pointer / touch-style drag
        box = page.locator("#game").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.2, box["y"] + box["height"] * 0.8)
        page.mouse.down(); time.sleep(0.6)
        sx = js(page, "__pq.session.ship.x")
        page.mouse.up()
        check("pointer drag steers the ship", sx < 1280 * 0.35, f"ship x={sx:.0f}")
        # game over path (force)
        js(page, "__pq.session.lives = 1; __pq.session.ship.invuln = 0; __pq.session.ship.shield = 0")
        page.evaluate("""async () => {
            const { Asteroid } = await import(new URL('js/logic.js', location.href));
            const s = __pq.session;
            s.entities.push(new Asteroid(s.ship.x, s.ship.y, 0, 0, 40));
        }""")
        ok_over = wait_js(page, "__pq.state === 'over'", 5)
        check("game over screen reachable", ok_over, f"state={js(page, '__pq.state')}")
        if shots and ok_over:
            time.sleep(0.8)
            page.screenshot(path=str(shots / "web_gameover.png"))
        check("no JavaScript errors (keyboard session)", not errors, "; ".join(errors[:3]))
        ctx.close()

        # ---- 2. camera permission granted (fake synthetic video) ------------
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, permissions=["camera"])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(a.url, wait_until="networkidle")
        wait_js(page, "window.__pq && __pq.state === 'menu'")
        page.keyboard.press("c")
        check("camera granted -> TRACKING on synthetic marker",
              wait_js(page, "__pq.cam.status === 'TRACKING'", 10), f"status={js(page, '__pq.cam.status')}")
        p1 = js(page, "__pq.cam.position"); time.sleep(0.8); p2 = js(page, "__pq.cam.position")
        moved = p1 and p2 and abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) > 0.02
        check("tracked centre moves with the synthetic marker", moved, f"{p1} -> {p2}")
        check("camera frame rate measured", js(page, "__pq.cam.fps") > 5, f"fps={js(page, '__pq.cam.fps'):.1f}")
        proc = js(page, "__pq.cam.procMs")
        check("per-frame processing time reported", proc > 0, f"proc={proc:.1f} ms in worker (this machine, headless)")
        check("vision runs in a Web Worker", js(page, "!!__pq.cam.worker"))
        check("hovering marker cannot switch webcam off", js(page, "__pq.buttons.menu[1].dwell === false"))
        js(page, "__pq.focus = 0")  # the synthetic marker may be hovering another button
        page.keyboard.press("Enter")
        check("game starts in webcam mode", wait_js(page, "__pq.state === 'play'", 3), f"state={js(page, '__pq.state')}")
        time.sleep(2.5)
        errs = []
        for _ in range(10):
            time.sleep(0.25)
            st = js(page, "[__pq.session.ship.x, __pq.session.ship.y, ...(__pq.webcamPoint() || [NaN, NaN])]")
            errs.append(((st[0] - st[2]) ** 2 + (st[1] - st[3]) ** 2) ** 0.5)
        mean = sum(errs) / len(errs)
        check("ship follows the webcam target", mean < 120, f"mean distance {mean:.0f}px")
        page.keyboard.press("Tab")
        time.sleep(1.0)
        check("TAB diagnostics on, game keeps running", js(page, "__pq.showDiag && __pq.state === 'play' && __pq.cam.result.edges !== null"))
        if shots:
            page.screenshot(path=str(shots / "web_diagnostics.png"))
        page.keyboard.press("v"); time.sleep(0.5)
        check("V swaps to frame difference", js(page, "__pq.diagView === 'motion' && __pq.cam.result.motionMask !== null"))
        page.keyboard.press("Tab")
        page.keyboard.press("m")
        page.keyboard.press("c")
        check("C turns the webcam off again", wait_js(page, "!__pq.cam.running", 3))
        check("no JavaScript errors (webcam session)", not errors, "; ".join(errors[:3]))
        if shots:
            page.goto(a.url + ("&" if "?" in a.url else "?") + "autopilot=1&seed=5", wait_until="networkidle")
            wait_js(page, "window.__pq && __pq.state === 'menu'")
            page.keyboard.press("Enter")
            time.sleep(12)
            page.screenshot(path=str(shots / "web_gameplay.png"))
        ctx.close()
        browser.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} browser checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
