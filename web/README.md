# Pixel Quest — Web Version

**Play:** https://ashmita-dev.github.io/PixelQuest/

A browser port of the desktop Pygame/OpenCV game in this repository. It has the same neon arcade gameplay, scoring,
hazards, effects and colour-marker tracking, written in plain HTML, CSS and JavaScript ES modules. There is no
build step and there are no runtime dependencies. The desktop version in the repository root is unchanged.

## Playing

1. Open the link. The title screen appears and the keyboard works immediately.
2. Optional: click **ENABLE WEBCAM** (or press **C**) and allow camera access when the browser asks.
   Hold a brightly coloured object (default **green**). The ship follows its centre, and hovering the marker over
   START GAME presses it.
3. Press **Enter** or click **START GAME**.

| Input | Action |
|---|---|
| Coloured marker (webcam) | Steer; hover a button ~1.4 s to press it (not WEBCAM/FULLSCREEN) |
| Arrow keys / WASD | Steer (always works; overrides the webcam while held) |
| Press-and-drag (mouse / touch) | Steer |
| Enter / Space / click | Activate the highlighted button |
| P or Esc | Pause / resume · **R** restart · **M** menu |
| C | Webcam on/off (outside gameplay) |
| TAB | Vision diagnostics (camera, HSV mask, morphology, Sobel / frame difference) |
| K | Calibrate: sample the colour in the white box (saved in this browser) |
| H | Next colour preset (green, blue, red, yellow, orange, pink) |
| V | Diagnostics: Sobel edges ↔ frame difference |
| N | Mute · **F** fullscreen |

URL options: `?marker=red` picks the starting preset, `?diag` opens diagnostics, and `?webcam` requests the camera on load.

## Privacy

Webcam frames are processed **only in your browser**, on a Web Worker. No frame is uploaded, stored or sent
anywhere. The site is static, so there is no server code. Only the high score and an optional calibrated HSV range
are kept, in `localStorage`. The page loads a font from Google Fonts. If that fails, system fonts are used.

## How the tracking works (same pipeline as `src/vision.py`)

```
getUserMedia → mirrored 320×240 canvas → getImageData → [Web Worker]
  5×5 Gaussian blur → RGB→HSV (OpenCV units) → threshold (hue wrap for red)
  → opening ×1 + closing ×2 with the 5×5 ellipse → 8-connected components (area ≥ 150 px)
  → largest blob → centroid from pixel moments → [main thread] EMA smoothing (α 0.35) → velocity Δp/Δt
```

### Differences from the desktop OpenCV version (honest list)

| Stage | Desktop (OpenCV) | Web (this folder) |
|---|---|---|
| Downscaling | `cv2.resize(INTER_AREA)` | `canvas.drawImage` (browser's own filtering) |
| Blur, HSV | `cv2.GaussianBlur`, `cv2.cvtColor` | Re-implemented. Matches OpenCV within ±2 levels on ≥99 % of pixels (tested) |
| Morphology | `cv2.morphologyEx` | Re-implemented. **Identical output** to OpenCV on the test fixtures (tested) |
| Regions | `findContours` + `contourArea` + contour moments | Connected-component labelling + pixel count + pixel moments. Centroid within 1 px of OpenCV (tested) |
| Edge demo | Canny | **Sobel** gradient magnitude (Canny is not implemented in the web version) |
| Concurrency | Python thread | Web Worker (main-thread fallback if module workers are unavailable) |

Like the desktop version, this does tracking and motion estimation only. It does not compress video and contains no codec.

## Development

```powershell
cd web
npm test                                   # 22 Node tests (no browser or camera needed)
python -m http.server 8000 --directory public   # then open http://localhost:8000
```

* `scripts/export_fixtures.py` regenerates `tests/fixtures/` from the desktop OpenCV pipeline. Run it with the repo's
  `.venv`. The fixtures are **synthetic** project-generated frames.
* `tests/e2e_browser.py` drives the real Chrome browser with Playwright (`pip install playwright`). Chrome's fake camera
  plays a video rendered from the project's synthetic moving green disc, so no real camera or person is used.
  Run it as `python web/tests/e2e_browser.py http://localhost:8000/`.
* Deployment: `.github/workflows/pages.yml` runs `npm test` and publishes `web/public` to GitHub Pages on every push to
  `main` that touches `web/`.

Requirements for visitors: a recent Chrome, Edge, Firefox or Safari. The webcam needs HTTPS, which GitHub Pages provides,
plus the visitor's permission. Without a webcam, or if permission is refused, the game stays fully playable with the keyboard, mouse or touch.
