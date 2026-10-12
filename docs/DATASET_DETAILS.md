# Dataset & Input Details

Pixel Quest has **no external or benchmark dataset**. Its primary input is the player's live
webcam. For testing, the repository holds a small set of **synthetic, project-generated** images.
No real-world accuracy figures are claimed anywhere in this project.

## 1. Inputs at a glance

| Input | Type | Origin | Stored in repo? | Used for |
|---|---|---|---|---|
| Live webcam stream | Live video | Player's camera via OpenCV | **No** (never saved) | Game control |
| `SyntheticSource` stream | Synthetic video, generated per frame | `src/vision.py` | No (generated at runtime) | Demo without webcam, tests, screenshots |
| `assets/samples/*.png` | Synthetic still images | `scripts/generate_samples.py`, fixed seeds | Yes (5 images) | Segmentation tests |
| `assets/samples/sequence/frame_00–09.png` | Synthetic image sequence | same script | Yes (10 frames) | Tracking / motion tests |
| `assets/samples/manifest.json` | Ground truth | same script | Yes | Expected centre, radius, hue per image |
| Optional user video file | Recorded video | Collected by the user (see §6) | No | Reproducible manual tests |

## 2. Live webcam input

* **Source:** default camera index 0 (`--camera N` or the `PIXELQUEST_CAMERA` variable to change it).
  On Windows the code tries the DirectShow, Media Foundation and default back ends in order.
* **Requested format:** 640×480 (`CAPTURE_W/H`). The camera may ignore this. The development
  webcam returned 640×480 frames.
* **Representation:** 8-bit, 3-channel **BGR** (`uint8`, shape `H×W×3`), OpenCV's native order.
* **Rate:** whatever the camera delivers, commonly about 30 fps. The diagnostics show the measured rate.
* **Retention:** frames live only in memory, for one processing step. The game never writes webcam
  frames to disk and sends nothing over the network.

## 3. Variables and parameters (all in `src/config.py`)

| Variable | Default | Meaning |
|---|---|---|
| `PROCESS_W × PROCESS_H` | 320 × 240 | Working resolution after downscaling |
| `MIRROR` | True | Horizontal flip so movement feels like a mirror |
| `BLUR_KSIZE` | 5 | Gaussian kernel size (odd); 0/1 disables |
| HSV `lower`, `upper` | green: (40,80,60)–(85,255,255) | Threshold bounds; H 0–179, S/V 0–255 |
| `MARKER_PRESETS` | green, blue, red, yellow, orange, pink | Ready-made ranges; red wraps (170→8) |
| `MORPH_KERNEL_SIZE` | 5 | Elliptical structuring element size |
| `MORPH_OPEN_ITER` / `MORPH_CLOSE_ITER` | 1 / 2 | Opening and closing iterations |
| `MIN_AREA` | 150 px² | Smaller blobs are rejected as noise |
| `SMOOTHING_ALPHA` | 0.35 | EMA weight of the newest centroid |
| `LOST_HOLD_FRAMES` | 8 | Frames to keep the last position after loss |
| `MOTION_SMOOTHING` | 0.5 | EMA factor for velocity |
| `FRAME_DIFF_THRESHOLD` | 25 | Grey-level change counted as motion (diagnostics) |
| `CANNY_LOW/HIGH` | 60 / 150 | Canny hysteresis thresholds (diagnostics) |
| `CONTROL_MARGIN` | 0.12 | Outer camera border mapped to the screen edge |

**Outputs per frame** (`FrameResult`): processed BGR frame, raw HSV mask, cleaned mask,
grey frame, `Detection` (found, centroid x/y in px, area, bounding box, blob count, rejected
count), normalised centre (0–1), and optionally the Canny edge map and frame-difference mask.

## 4. Pre-processing & morphology

1. Mirror (`cv2.flip(frame, 1)`).
2. Downscale to 320×240 with `INTER_AREA` (area averaging).
3. Gaussian blur 5×5.
4. BGR→HSV and `cv2.inRange` (two ranges OR'ed for wrapped hue).
5. Morphological opening (×1), then closing (×2), with a 5×5 ellipse.
6. External contours, area filter, largest blob, centroid from moments.

## 5. Synthetic test data (project-generated)

`python scripts/generate_samples.py` regenerates everything deterministically:

* 640×480 dark background, uniform noise (0–40 grey levels, seeded) and a vertical lighting gradient.
* A disc of radius 40 px in the marker hue, plus a small low-saturation highlight (tests closing).
* 30 isolated pixels in the marker colour (tests blur + opening).
* Distractors: a **blue** 90×90 box and a pale low-saturation disc.

| File | Marker | Ground truth (px) | Expected result |
|---|---|---|---|
| `synthetic_green_centre.png` | green (H 60) | (320, 240) | found, error < 3 px |
| `synthetic_green_left.png` | green | (140, 160) | found, error < 3 px |
| `synthetic_red_right.png` | red (H 178, wraps) | (500, 200) | found with red preset |
| `synthetic_blue_low.png` | blue (H 110) | (330, 400) | **limitation demo:** blue box is larger, so it is selected instead |
| `synthetic_no_marker.png` | none | – | green preset finds nothing |
| `sequence/frame_00…09.png` | green, moving right | in manifest | per-frame dx matches ground truth (±0.005) |

These images are **synthetic**. They show the algorithm behaves as designed. They do **not**
measure how well tracking works on real cameras, people or rooms.

## 6. Collecting optional real test samples (manual)

1. Run the calibrator: `.venv\Scripts\python scripts\calibrate_hsv.py`. Tune until only the marker is white, then press **S**.
2. To record a short clip for reproducible tests, use any webcam recorder (e.g. the Windows Camera app)
   and save as MP4. Keep it short and avoid filming people who have not agreed.
3. Replay it through the full game pipeline: `.venv\Scripts\python main.py --camera path\to\clip.mp4 --diag`.
4. Record what you observe (lighting, marker, background, whether the status stayed `TRACKING`) in
   `docs/PROGRESS.md`. Do not commit personal recordings.

## 7. Limitations

* **Lighting:** dim light lowers S and V below the thresholds. Strong coloured light shifts hue.
  Auto-exposure and white balance can change colours while you play.
* **Background:** any object of the marker's colour is a candidate, and the *largest* one wins.
  In one informal check on the development laptop, with **no marker** in view, the room
  background produced detections in 17/45 frames with the green preset (largest blob 1048 px²) and
  37/45 with blue; red, orange and pink produced none. A real marker held at 40–80 cm is
  usually larger than such blobs, but you should check diagnostics (TAB) before playing and choose a colour
  that is absent from your background.
* **Skin tones** can fall inside orange/red/pink ranges. Keep hands out of frame or use green/blue.
* **Single object:** only the largest blob is tracked. There is no identity across frames and no occlusion handling.
* Results differ between cameras, rooms and times of day. No accuracy figure is claimed.

## 8. Privacy

Frames are processed in memory and discarded. Nothing is saved, uploaded or logged. The only files
written at runtime are `hsv_config.json` (six threshold numbers) and `highscore.json` (one integer).
Both are git-ignored.

## 9. Expected output

With a correctly calibrated marker the diagnostics status shows `TRACKING`. The cleaned-mask
tile shows a single white blob, the crosshair sits on the marker, and the ship follows the marker. If
the marker leaves the view, the status reads `HOLDING` for 8 frames, then `SEARCHING`, and the ship coasts to a stop. Keyboard keys still work.
