# Image & Video Processing — Syllabus Mapping

This document maps course topics to the code that **actually exists** in this
repository. Every "Implemented" row names the function that does the work and the test that
checks it. Line numbers refer to `src/vision.py` at the time of writing.

Legend: **Implemented** = used by the game every frame · **Diagnostic demo** = really
computed, shown in the diagnostics view, not used for control · **Not implemented** = absent.

## Summary

| Course topic | Status | Where in the code | Tests |
|---|---|---|---|
| Image Segmentation (core) | Implemented | `segment_hsv` (l.123), `find_marker` (l.164) | `test_segmentation_*`, `test_find_marker_*`, `test_samples.py` |
| Fundamentals of Digital Video (core) | Implemented | `VisionTracker._run` (l.572), `open_camera` (l.455), `SyntheticSource`, `LoopingVideoSource` | `test_tracker.py`, `test_synthetic_video_is_tracked_frame_by_frame` |
| Motion Estimation (core) | Implemented (centroid displacement) | `MotionEstimator` (l.284) | `test_motion_estimator_velocity_and_direction`, `test_sequence_motion_direction` |
| Temporal frame differencing | Diagnostic demo | `frame_difference` (l.185) | `test_frame_difference_measures_changed_pixels` |
| Colour Image Processing | Implemented | `bgr_to_hsv` (l.119), `HSVRange` hue wrap, `hsv_range_from_sample` (l.204) | `test_red_range_wraps_around_hue_zero`, `test_hsv_range_from_*` |
| Morphological Processing | Implemented | `make_kernel` (l.134), `clean_mask` (l.140) | `test_opening_removes_isolated_noise_pixels`, `test_closing_fills_small_holes` |
| Image Enhancement (smoothing) | Implemented | `preprocess` (l.106) – Gaussian blur | `test_gaussian_blur_reduces_noise_variance` |
| Edge Detection | Diagnostic demo (Canny) | `edge_map` (l.198) | `test_edge_map_finds_disc_boundary` |
| Temporal smoothing / filtering | Implemented | `PositionSmoother` (l.236) – EMA | `test_position_smoother_reduces_jitter_and_holds` |
| Video compression / codecs | **Not implemented** | – | – |
| Block-matching or optical-flow motion estimation | **Not implemented** | – | – |
| Sobel, Hough, histogram equalisation, Fourier filtering | **Not implemented** | – | – |
| Deep-learning detection (YOLO, MediaPipe…) | **Not implemented** (deliberately) | – | – |

## Per-frame pipeline

```
webcam (BGR, ~640x480)
  │  cv2.VideoCapture.read()            ← Fundamentals of digital video
  ▼
mirror (cv2.flip) → downscale to 320x240 (INTER_AREA) → Gaussian blur 5x5   ← Image enhancement
  ▼
BGR → HSV (cv2.cvtColor)                                                    ← Colour image processing
  ▼
cv2.inRange(lower, upper)  (two ranges OR'ed if the hue wraps, e.g. red)    ← Segmentation
  ▼
opening (erode→dilate) then closing (dilate→erode), 5x5 ellipse              ← Morphology
  ▼
external contours → discard area < 150 px → largest → centroid via moments  ← Segmentation / region description
  ▼
EMA smoothing  p ← αz + (1-α)p,  α = 0.35,  hold 8 frames on loss          ← Temporal filtering
  ▼
v = (p_t − p_{t−1}) / Δt (EMA-smoothed) → speed, direction                  ← Motion estimation
  ▼
mapped to the play area → ship follows with frame-rate-independent easing
```

Diagnostics only (computed when TAB is on): grey-level `|I_t − I_{t−1}| > 25`
(frame differencing) and Canny edges (60/150).

## 1. Image Segmentation (core)

* **What:** thresholding in HSV space produces a binary mask `M(x,y) = 255` if
  `lower ≤ HSV(x,y) ≤ upper`, else 0 (`cv2.inRange`).
* **Hue wrap:** OpenCV hue is 0–179 and red sits at both ends. `HSVRange` treats
  `lower_h > upper_h` as a wrapped interval, and `segment_hsv` ORs the masks for
  `[lower_h,179]` and `[0,upper_h]`.
* **Region extraction:** `cv2.findContours(RETR_EXTERNAL)` gives connected blob
  outlines (Suzuki–Abe border following). Blobs under `MIN_AREA` (150 px² at 320×240) are
  rejected as noise. The largest remaining blob is chosen.
* **Centroid:** from image moments, `(x̄, ȳ) = (m10/m00, m01/m00)`.
* **Known failure modes** (tested, see `tests/test_samples.py`): a *larger* object of the
  same colour beats the marker (largest-blob rule); a low-saturation object is
  correctly ignored.

## 2. Fundamentals of Digital Video (core)

* Video is treated as a sequence of discrete frames `I_t` sampled at the camera rate (the
  test webcam delivered 640×480 BGR frames; frame rate depends on the camera).
* `VisionTracker` acquires frames on a background thread. The latest result is
  published under a lock, so the 60 FPS render loop never waits on the camera.
* Frame sources share one interface (`isOpened/read/release`): a real webcam (`open_camera`,
  tries DirectShow → Media Foundation → default on Windows), a video file (`LoopingVideoSource`) or the
  project-generated `SyntheticSource`.
* Failure handling: no device → `NO CAMERA`; driver exception → `ERROR`; 30 consecutive
  failed reads → `ERROR`. In every case keyboard control stays active.

## 3. Motion Estimation (core)

* `MotionEstimator` estimates the motion of **one tracked object** from the displacement
  of its smoothed centroid between consecutive frames: `d = p_t − p_{t−1}`,
  `v = d / Δt`, followed by an exponential moving average. It reports `dx, dy, vx, vy`,
  speed and a compass direction (STILL / UP / DOWN-LEFT …).
* The diagnostics overlay draws the velocity vector on the camera tile.
* `frame_difference` is a separate, whole-image temporal measure: the fraction of pixels
  whose grey level changed by more than 25 between frames ("Frame-diff motion %").
* **Not** implemented: block matching, optical flow (Lucas–Kanade/Farnebäck) or motion
  compensation. This project does **tracking and motion estimation only**. It does not
  compress video and contains no codec.

## 4. Colour Image Processing

* BGR→HSV separates chromaticity (H, S) from brightness (V). Thresholds are therefore far less
  sensitive to illumination changes than equivalent RGB thresholds.
* Presets for green, blue, red (wrapping), yellow, orange and pink are in `src/config.py`.
* One-key calibration (`hsv_range_from_sample`) computes the **circular mean** of hue
  in a 24×24 box (hue is an angle) and the 90th-percentile circular spread. It sets S/V
  lower bounds from the 10th percentile minus a margin.

## 5. Morphological Processing

* Structuring element: 5×5 ellipse (`cv2.MORPH_ELLIPSE`), so it responds equally in every direction.
* **Opening** (erosion then dilation, 1 iteration) deletes isolated pixels and thin
  speckles smaller than the kernel while restoring the size of larger blobs.
* **Closing** (dilation then erosion, 2 iterations) fills small holes, such as specular
  highlights on a shiny marker, and joins fragments.
* Configurable via `MORPH_KERNEL_SIZE`, `MORPH_OPEN_ITER` and `MORPH_CLOSE_ITER`. `docs/images/pipeline_stages.png`
  tiles 4→5 show opening removing salt noise.

## 6. Image Enhancement

* 5×5 Gaussian blur (`BLUR_KSIZE`) is applied after downscaling. It suppresses sensor noise before
  thresholding, so fewer isolated pixels pass the HSV test. The test checks that the
  standard deviation of a noisy frame drops by over 40 %.
* Downscaling with `INTER_AREA` both averages noise and cuts processing cost by 4×.

## 7. Edge Detection (diagnostic demonstration)

* `edge_map` runs Canny (hysteresis thresholds 60/150) on the grey frame. It is shown in
  the 4th diagnostics tile (press **V** to swap it for frame differencing). It is **not**
  used to steer the ship.

## Measured performance (honest scope)

On the development laptop the pipeline (`process_frame` without extras) took about **1.2 ms per
320×240 frame**. This was measured over 45 real webcam frames with no marker in view. It is a single
informal timing, not a benchmark.
