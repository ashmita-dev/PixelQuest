# Progress Log

## Status — 2026-10-12

The game is playable, the vision pipeline is integrated, tests pass, the docs and report are written, and everything is pushed to GitHub.
**Interactive webcam play with a physical marker has not yet been tested** (see "Remaining manual steps").

## Completed

- [x] Environment inspected: empty folder, Windows 11, Python 3.11.9 venv (3.9–3.14 also installed), Git 2.52, gh 2.102 authenticated as `ashmita-dev`, empty public remote.
- [x] Git initialised on `main`, `origin` = https://github.com/ashmita-dev/PixelQuest.git
- [x] Arcade game: menu, help, play, pause, game over; crystals, power cores (shield), asteroids, drones; lives, combo, levels, high score.
- [x] Visuals: parallax starfield, glow, particles, screen shake, animated buttons, countdown, level banner; procedural sound.
- [x] Vision: threaded capture, mirror, downscale, Gaussian blur, BGR→HSV, `inRange` (hue wrap), opening and closing, contours, min-area filter, moments centroid, EMA smoothing, hold-on-loss, displacement velocity, frame differencing, Canny.
- [x] Keyboard fallback in every mode; webcam/keyboard switch (C); graceful NO CAMERA / ERROR handling.
- [x] Diagnostics view (TAB) with 4 live tiles and numeric readouts; live colour sampling (K); presets (H).
- [x] `scripts/calibrate_hsv.py` slider calibrator; `--camera synthetic` and video-file sources.
- [x] Synthetic samples + manifest, pipeline figures, real headless screenshots.
- [x] Docs: README, CLAUDE.md, IVP_MAPPING, DATASET_DETAILS, DEMO_GUIDE, PROJECT_REPORT (.md, .docx, .pdf).

## Commands run (and results)

| Command | Result |
|---|---|
| `py -3.11 -m venv .venv` + `pip install pygame opencv-python numpy pytest python-docx` | pygame 2.6.1, OpenCV 5.0.0, NumPy 2.4.6, pytest 9.1.1 |
| `main.py --keyboard --start menu/help --frames 90` (SDL dummy) | ran OK |
| `main.py --camera synthetic --diag --start play --autopilot --frames 900` | ran OK, status TRACKING |
| `python -m pytest -q` | first run: access violation (cached Font after `pygame.quit`), fixed; then 1 failing test (wrong assumption in the test), fixed; **final: 65 passed** |
| Webcam probe (`open_camera(0)`, 1 frame) | opened, 640×480 BGR frame read |
| 45 real frames, no marker, each preset | false detections: green 17/45, blue 37/45, yellow 15/45, red/orange/pink 0/45; ≈1.2 ms/frame |
| `scripts/generate_samples.py` | 15 synthetic samples; green finds 12/15 as expected |
| `scripts/capture_screenshots.py` | 6 screenshots in `docs/images/` |
| `scripts/build_report.py` | DOCX + PDF (11 pages, via Word) |
| `scripts/calibrate_hsv.py --help` | parses; **interactive window not exercised** |

## Test classification

- **Automated, executed:** 65 pytest tests (see `docs/PROJECT_REPORT.md` §7.1).
- **Synthetic-input tests:** all vision tests use generated frames, saved synthetic samples or `SyntheticSource`.
- **Real webcam, executed:** device opens and delivers frames; background false-positive check without a marker; timing.
- **Manual, still required (needs a person and a marker):** see below.

## Known issues / limitations

- Same-coloured background objects larger than the marker are tracked instead (documented, tested).
- The green and blue presets picked up background objects in the development room. Check TAB diagnostics, and use **H**/**K** to pick another colour.
- The diagnostics panel covers the right part of the play field while open.
- End-to-end input latency has not been measured.

## Remaining manual steps

1. `.venv\Scripts\python main.py`: hold a marker and confirm the status reads `TRACKING` and the ship follows smoothly.
2. Press TAB and confirm the mask shows one blob. Try **H** presets and **K** sampling with your actual marker.
3. Hover the marker over START until it triggers (gesture menu).
4. Hide the marker and confirm `HOLDING` → `SEARCHING`, and that the arrow keys still work.
5. Unplug the camera or block it in another app, and confirm the game reports it and keeps running.
6. Optionally run `scripts\calibrate_hsv.py`, tune, and press **S**.
7. Record what you observe here.
