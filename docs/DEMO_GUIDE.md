# Pixel Quest — Demo Guide

## 1. Install (Windows, PowerShell, from the project folder)

```powershell
cd D:\Projects\PixelQuest
py -3.11 -m venv .venv                       # any Python 3.9–3.13 with pygame wheels works
.venv\Scripts\python -m pip install -r requirements.txt
```

Optional, for tests and rebuilding the report:

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

## 2. Launch

| Command | What it does |
|---|---|
| `.venv\Scripts\python main.py` | Webcam control (falls back to keyboard automatically) |
| `.venv\Scripts\python main.py --keyboard` | Keyboard only; webcam never opened |
| `.venv\Scripts\python main.py --marker red` | Start with another colour preset |
| `.venv\Scripts\python main.py --camera 1` | Use a second camera |
| `.venv\Scripts\python main.py --camera synthetic --diag` | No webcam: project-generated test video drives the pipeline |
| `.venv\Scripts\python main.py --fullscreen` | Fullscreen (F11 toggles in game) |
| `.venv\Scripts\python scripts\calibrate_hsv.py` | Slider-based HSV tuner; **S** saves for the game |

## 3. Controls

| Key | Action |
|---|---|
| Move marker | Steer ship (webcam mode); hover a button ~1.4 s to press it |
| Arrows / WASD | Steer ship (always works, overrides webcam while held) |
| Enter / Space / click | Activate the highlighted button |
| P or Esc | Pause / resume |
| R | Restart (in game, pause, game over) |
| M | Main menu |
| C | Switch webcam ↔ keyboard (menu, pause, game over) |
| TAB | Show/hide vision diagnostics (game keeps running) |
| V | Diagnostics: swap Canny edges ↔ frame difference |
| K | Calibrate: sample the colour inside the white box |
| H | Cycle HSV presets |
| N | Mute · **F11** fullscreen |

**Gameplay:** collect cyan crystals (+10 × combo). Every 5 in a row raises the multiplier, up to ×5.
Gold power cores give +50 and a 6-second shield that smashes hazards. Avoid asteroids and, from level 3,
weaving magenta drones. You have 3 lives with 2 s of invulnerability after each hit. The level rises every 25 s.

## 4. Webcam & marker setup

* Use a **matte, saturated, single-colour** object about the size of a fist or larger: a ball, a sticky-note pad, a cup.
  Green or blue work if they don't appear in your background. Red and orange can clash with skin tones.
* Light the **front** of the marker. Avoid a bright window behind you.
* Sit 40–80 cm from the camera so the marker fills about 3–10 % of the picture.
* Press **TAB**. The "MORPHOLOGY" tile should show *one* white blob. If background objects light up,
  change preset (**H**), use another marker or remove the object.
* Custom colour: hold the marker inside the white square in the camera tile and press **K**. The range is
  saved to `hsv_config.json` and loaded next time. Delete that file to return to the default.

## 5. Two-to-three-minute demonstration script

1. **(0:00) Title screen.** "Pixel Quest is a neon arcade game you steer with any coloured object, using classical
   image processing in OpenCV. No deep learning is involved." Point out the INPUT card showing `WEBCAM: TRACKING`.
2. **(0:20) Gesture menu.** Hover the marker over START until the bar fills. This shows the tracked centre acting as a cursor.
3. **(0:35) Play for about 30 s.** Collect crystals and dodge asteroids. Mention combo, shield and level-up.
4. **(1:05) Press TAB.** Walk through the four tiles while still playing:
   * *Camera + Track* — the mirrored, downscaled, blurred frame with crosshair (centroid), box and velocity arrow.
   * *HSV Threshold* — "each pixel is converted from BGR to HSV and kept if its hue, saturation and value fall in the
     range shown below. Hue identifies the colour; the saturation and value limits reject grey and dark pixels."
   * *Morphology* — "opening (erode then dilate) deletes specks smaller than the 5×5 disc; closing fills holes
     like reflections. Blobs under 150 px are ignored, and the largest remaining blob is the marker."
   * *Canny / Frame difference* (press **V**) — "edges are only a demonstration. Frame difference shows which
     pixels changed between consecutive frames."
5. **(1:45) Motion.** Move the marker quickly left, then up. The *Velocity* line and arrow show
   `v = (p_t − p_{t−1}) / Δt` and the direction name. Note the centroid smoothing: `p ← 0.35·z + 0.65·p`.
   "This is tracking and motion estimation of one object. It is not video compression."
6. **(2:10) Robustness.** Hide the marker: status `HOLDING`, then `SEARCHING`. Use the arrow keys to show the
   keyboard fallback. Optionally press **K** with a different object to recalibrate live.
7. **(2:30) Close.** Pause (P), show restart/menu, and mention the 65 automated tests that run on synthetic frames.

**No webcam at the demo?** Run `main.py --camera synthetic --diag`. The project-generated video (a moving
green disc with distractors) drives exactly the same pipeline. Say clearly that it is synthetic.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `NO CAMERA` toast | Close other apps using the camera (Teams, Zoom, browser). Check *Settings → Privacy & security → Camera* → allow desktop apps. Try `--camera 1`. |
| Status stuck at `SEARCHING` | Press TAB. If the HSV tile is black, the colour is out of range: press **K** with the marker in the box, or press **H**. Add light. |
| Ship jumps to random places | A background object matches. Look at the HSV tile, remove the object or switch colour. |
| Jittery ship | Lower `SMOOTHING_ALPHA` in `src/config.py` (e.g. 0.2) for smoother but slightly laggier motion, or move closer for a bigger blob. |
| Laggy or low FPS | Close diagnostics (TAB); unplug/replug USB cameras; use `--keyboard` to rule out the camera. |
| Colours drift during play | The camera's auto white balance or exposure. Fix the lighting, or recalibrate with **K**. |
| Window too large or small | The window is resizable and scaled. F11 for fullscreen. |
| No sound | Audio is optional. A missing device is ignored. **N** toggles mute. |
| `ModuleNotFoundError` | Run with `.venv\Scripts\python`, not the system Python, after installing requirements. |
