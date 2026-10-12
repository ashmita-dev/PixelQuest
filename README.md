# PIXEL QUEST

**A real-time webcam-controlled arcade game using image and video processing.**

Hold a coloured object in front of your webcam and steer a neon spaceship through an asteroid field.
Pixel Quest tracks the object with classical OpenCV techniques: HSV colour segmentation, morphological
filtering, contour centroids, temporal smoothing and frame-to-frame motion estimation. It uses no deep learning
and no cloud services. The keyboard always works as a fallback.

![Gameplay](docs/images/screen_gameplay.png)

| Title | Vision diagnostics (TAB) |
|---|---|
| ![Menu](docs/images/screen_menu.png) | ![Diagnostics](docs/images/screen_diagnostics.png) |

<sub>Screenshots are real renders of the game. The diagnostics panel in them is fed by the project's
**synthetic** test video (`--camera synthetic`), not a real webcam, and the ship is flown by the demo autopilot.</sub>

## Quick start (Windows)

```powershell
cd D:\Projects\PixelQuest
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py              # webcam (default marker colour: green)
.venv\Scripts\python main.py --keyboard   # no webcam
```

Other options: `--marker {green,blue,red,yellow,orange,pink}`, `--camera 1`, `--camera synthetic`,
`--camera clip.mp4`, `--diag`, `--fullscreen`, `--mute`. Full instructions are in [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

## Controls

Move the **marker** (or **arrows/WASD**) to fly. Hover the marker on a button to press it. **P/Esc** pause ·
**R** restart · **M** menu · **C** webcam/keyboard · **TAB** diagnostics · **K** sample marker colour ·
**H** next colour preset · **V** edges/frame-diff · **N** mute · **F11** fullscreen.

Collect cyan crystals (combo multiplier up to ×5), grab gold cores for a shield, and dodge asteroids and drones.
You have 3 lives, and the speed rises every 25 seconds.

## How the vision works

```
webcam → mirror → resize 320×240 → Gaussian blur → BGR→HSV → inRange mask
       → opening + closing → contours (area ≥ 150) → centroid (moments)
       → EMA smoothing → velocity (Δp/Δt) → ship target
```

* Runs on a background thread, so the game renders at 60 FPS regardless of the camera rate.
* On the development laptop the pipeline took about 1.2 ms per frame (single informal measurement).
* Camera missing, busy or failing? The status shows `NO CAMERA` or `ERROR`, and keyboard control continues.
* Calibrate a new colour live with **K**, or use `scripts/calibrate_hsv.py` (sliders). Both save to `hsv_config.json`.

Course-topic mapping: [docs/IVP_MAPPING.md](docs/IVP_MAPPING.md) · Inputs and test data:
[docs/DATASET_DETAILS.md](docs/DATASET_DETAILS.md) · Report: [docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md)
(`.docx`/`.pdf` alongside).

## Project layout

```
main.py                 launcher / CLI
src/config.py           all tunable parameters (gameplay + vision)
src/vision.py           image & video processing pipeline, camera sources, threaded tracker
src/session.py          game rules: spawning, collisions, scoring, lives, levels (no rendering)
src/player.py           ship movement and drawing
src/entities.py         crystals, power cores, asteroids, drones
src/effects.py          starfield, particles, glow, screen shake
src/ui.py               HUD, buttons, glowing text, diagnostics view
src/audio.py            procedurally generated sound effects
src/game.py             state machine, input, rendering
scripts/                HSV calibrator, synthetic-sample generator, screenshots, report builder
tests/                  pytest suite (synthetic frames, fake cameras, headless SDL)
assets/samples/         synthetic test images + ground-truth manifest
docs/                   mapping, dataset, demo guide, progress log, report
```

## Tests

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

65 tests cover segmentation (including the red hue wrap), morphology, centroids, blur, smoothing, motion,
frame differencing, Canny, colour sampling, camera-failure handling, game rules and headless app
start-up and state transitions. None of them need a webcam.

## Limitations

Colour tracking depends on lighting and background. Any larger object of the marker's colour wins, skin can
match red/orange/pink, and only one object is tracked. See [docs/DATASET_DETAILS.md §7](docs/DATASET_DETAILS.md).

## Tech

Python 3.11 · Pygame 2.6 · OpenCV · NumPy · pytest.
