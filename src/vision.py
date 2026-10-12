"""Image and video processing for Pixel Quest.

Pipeline applied to every webcam frame (see docs/IVP_MAPPING.md):

    acquire BGR frame -> mirror -> downscale -> Gaussian blur
    -> BGR->HSV -> HSV threshold (binary mask)
    -> morphological opening + closing
    -> external contours -> largest blob above MIN_AREA -> centroid (image moments)
    -> exponential smoothing over time -> frame-to-frame velocity (motion estimate)

Diagnostics additionally compute grey-level frame differencing and a Canny edge
map. This module performs *tracking and motion estimation*; it does not
implement any form of video compression or a video codec.

The pure functions at the top are deterministic and are unit-tested with
synthetic frames. ``VisionTracker`` runs the pipeline on a background thread so
a slow camera never stalls the game loop.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

from . import config

Point = Tuple[float, float]


# ---------------------------------------------------------------------------
# HSV colour range
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HSVRange:
    """Inclusive HSV bounds in OpenCV units (H 0-179, S/V 0-255).

    When ``lower[0] > upper[0]`` the hue interval wraps around 180, which is
    required for red markers whose hue straddles 0.
    """

    lower: Tuple[int, int, int]
    upper: Tuple[int, int, int]
    name: str = "custom"

    @property
    def wraps_hue(self) -> bool:
        return self.lower[0] > self.upper[0]

    def to_dict(self) -> dict:
        return {"name": self.name, "lower": list(self.lower), "upper": list(self.upper)}

    @classmethod
    def from_dict(cls, data: dict) -> "HSVRange":
        lower = tuple(int(v) for v in data["lower"])
        upper = tuple(int(v) for v in data["upper"])
        if len(lower) != 3 or len(upper) != 3:
            raise ValueError("HSV bounds need three values")
        return cls(lower, upper, str(data.get("name", "custom")))

    @classmethod
    def preset(cls, name: str) -> "HSVRange":
        lower, upper = config.MARKER_PRESETS[name]
        return cls(tuple(lower), tuple(upper), name)

    def describe(self) -> str:
        (h0, s0, v0), (h1, s1, v1) = self.lower, self.upper
        return f"{self.name}: H{h0}-{h1} S{s0}-{s1} V{v0}-{v1}"


def load_hsv_range(path: Path = config.HSV_CONFIG_FILE) -> Optional[HSVRange]:
    """Load a user-calibrated range, returning None if absent or invalid."""
    try:
        return HSVRange.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_hsv_range(rng: HSVRange, path: Path = config.HSV_CONFIG_FILE) -> bool:
    try:
        Path(path).write_text(json.dumps(rng.to_dict(), indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def default_hsv_range() -> HSVRange:
    saved = load_hsv_range()
    if saved is not None:
        return saved
    name = config.DEFAULT_MARKER if config.DEFAULT_MARKER in config.MARKER_PRESETS else "green"
    return HSVRange.preset(name)


# ---------------------------------------------------------------------------
# Pure processing stages
# ---------------------------------------------------------------------------
def preprocess(frame: np.ndarray, size: Optional[Tuple[int, int]] = None,
               blur_ksize: int = config.BLUR_KSIZE, mirror: bool = False) -> np.ndarray:
    """Mirror, downscale and Gaussian-blur a BGR frame (image enhancement)."""
    if mirror:
        frame = cv2.flip(frame, 1)
    if size is not None and (frame.shape[1], frame.shape[0]) != tuple(size):
        frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    if blur_ksize and blur_ksize > 1:
        k = blur_ksize | 1  # kernel must be odd
        frame = cv2.GaussianBlur(frame, (k, k), 0)
    return frame


def bgr_to_hsv(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)


def segment_hsv(hsv: np.ndarray, rng: HSVRange) -> np.ndarray:
    """Threshold an HSV image into a binary mask (255 = marker colour)."""
    lo = np.array(rng.lower, dtype=np.uint8)
    hi = np.array(rng.upper, dtype=np.uint8)
    if rng.wraps_hue:
        upper_part = cv2.inRange(hsv, lo, np.array([179, hi[1], hi[2]], np.uint8))
        lower_part = cv2.inRange(hsv, np.array([0, lo[1], lo[2]], np.uint8), hi)
        return cv2.bitwise_or(upper_part, lower_part)
    return cv2.inRange(hsv, lo, hi)


def make_kernel(size: int = config.MORPH_KERNEL_SIZE) -> np.ndarray:
    """Elliptical structuring element; a disc treats all directions equally."""
    size = max(1, int(size))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def clean_mask(mask: np.ndarray, kernel_size: int = config.MORPH_KERNEL_SIZE,
               open_iter: int = config.MORPH_OPEN_ITER,
               close_iter: int = config.MORPH_CLOSE_ITER) -> np.ndarray:
    """Morphological opening (remove specks) followed by closing (fill holes)."""
    kernel = make_kernel(kernel_size)
    out = mask
    if open_iter > 0:
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel, iterations=open_iter)
    if close_iter > 0:
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
    return out


@dataclass
class Detection:
    found: bool
    x: float = 0.0              # centroid in processed-image pixels
    y: float = 0.0
    area: float = 0.0
    bbox: Optional[Tuple[int, int, int, int]] = None
    contour_count: int = 0      # all external contours, before area filtering
    rejected_small: int = 0     # contours discarded by the min-area rule


def find_marker(mask: np.ndarray, min_area: float = config.MIN_AREA) -> Detection:
    """Locate the largest blob in a binary mask and return its centroid.

    The centroid is computed from image moments: (m10/m00, m01/m00).
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    areas = [cv2.contourArea(c) for c in contours]
    valid = [(a, c) for a, c in zip(areas, contours) if a >= min_area]
    if not valid:
        return Detection(False, contour_count=len(contours), rejected_small=len(contours))
    area, best = max(valid, key=lambda item: item[0])
    m = cv2.moments(best)
    x, y, w, h = cv2.boundingRect(best)
    if m["m00"] > 0:
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
    else:  # degenerate contour - fall back to the box centre
        cx, cy = x + w / 2.0, y + h / 2.0
    return Detection(True, cx, cy, area, (x, y, w, h), len(contours),
                     len(contours) - len(valid))


def frame_difference(prev_gray: Optional[np.ndarray], gray: np.ndarray,
                     threshold: int = config.FRAME_DIFF_THRESHOLD):
    """Temporal frame differencing |I_t - I_(t-1)|.

    Returns (binary motion mask, fraction of pixels that changed).
    """
    if prev_gray is None or prev_gray.shape != gray.shape:
        return np.zeros_like(gray), 0.0
    diff = cv2.absdiff(gray, prev_gray)
    _, motion = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    return motion, float(np.count_nonzero(motion)) / motion.size


def edge_map(gray: np.ndarray, low: int = config.CANNY_LOW,
             high: int = config.CANNY_HIGH) -> np.ndarray:
    """Canny edge detection (diagnostic demonstration only)."""
    return cv2.Canny(gray, low, high)


def hsv_range_from_sample(hsv_roi: np.ndarray, h_margin: int = 8,
                          s_margin: int = 50, v_margin: int = 60) -> HSVRange:
    """Derive an HSV range from a patch of the marker (one-click calibration).

    Hue is circular, so the centre hue is a circular mean and the spread is
    measured as circular distance; the resulting interval may wrap past 180.
    """
    pixels = hsv_roi.reshape(-1, 3).astype(np.float64)
    if pixels.size == 0:
        raise ValueError("empty sample")
    angles = pixels[:, 0] * (2.0 * math.pi / 180.0)
    centre = math.atan2(np.sin(angles).mean(), np.cos(angles).mean())
    centre_h = (centre * 180.0 / (2.0 * math.pi)) % 180.0
    dist = np.abs((pixels[:, 0] - centre_h + 90.0) % 180.0 - 90.0)
    spread = float(np.percentile(dist, 90)) + h_margin
    spread = min(spread, 40.0)
    h_lo = int(round(centre_h - spread)) % 180
    h_hi = int(round(centre_h + spread)) % 180
    s_lo = int(np.clip(np.percentile(pixels[:, 1], 10) - s_margin, 40, 255))
    v_lo = int(np.clip(np.percentile(pixels[:, 2], 10) - v_margin, 40, 255))
    return HSVRange((h_lo, s_lo, v_lo), (h_hi, 255, 255), "sampled")


def centre_roi(img: np.ndarray, size: int = config.SAMPLE_BOX) -> np.ndarray:
    h, w = img.shape[:2]
    half = size // 2
    return img[h // 2 - half:h // 2 + half, w // 2 - half:w // 2 + half]


# ---------------------------------------------------------------------------
# Temporal processing
# ---------------------------------------------------------------------------
class PositionSmoother:
    """Exponential moving average of the centroid: p = a*z + (1-a)*p.

    If the marker disappears, the last position is held for ``hold_frames``
    frames so a single dropped detection does not make the ship jump.
    """

    def __init__(self, alpha: float = config.SMOOTHING_ALPHA,
                 hold_frames: int = config.LOST_HOLD_FRAMES):
        self.alpha = float(np.clip(alpha, 0.01, 1.0))
        self.hold_frames = hold_frames
        self.pos: Optional[Point] = None
        self.missed = 0

    def update(self, point: Optional[Point]) -> Optional[Point]:
        if point is not None:
            if self.pos is None:
                self.pos = point
            else:
                a = self.alpha
                self.pos = (a * point[0] + (1 - a) * self.pos[0],
                            a * point[1] + (1 - a) * self.pos[1])
            self.missed = 0
        else:
            self.missed += 1
            if self.missed > self.hold_frames:
                self.pos = None
        return self.pos

    @property
    def holding(self) -> bool:
        return self.pos is not None and self.missed > 0

    def reset(self) -> None:
        self.pos = None
        self.missed = 0


@dataclass
class MotionInfo:
    dx: float = 0.0             # displacement since previous frame (normalised)
    dy: float = 0.0
    vx: float = 0.0             # smoothed velocity (normalised units / s)
    vy: float = 0.0
    speed: float = 0.0
    direction: str = "--"


class MotionEstimator:
    """Frame-to-frame motion of the tracked centre.

    v_t = (p_t - p_(t-1)) / dt, smoothed with an EMA. This is a simple
    displacement-based motion estimate of one object - not block matching and
    not part of any compression scheme.
    """

    def __init__(self, smoothing: float = config.MOTION_SMOOTHING,
                 still_threshold: float = config.MOTION_STILL_THRESHOLD):
        self.smoothing = smoothing
        self.still_threshold = still_threshold
        self.prev: Optional[Point] = None
        self.prev_t: Optional[float] = None
        self.info = MotionInfo()

    def update(self, point: Optional[Point], t: float) -> MotionInfo:
        if point is None:
            self.prev, self.prev_t = None, None
            self.info = MotionInfo()
            return self.info
        if self.prev is None or self.prev_t is None or t <= self.prev_t:
            self.prev, self.prev_t = point, t
            self.info = MotionInfo(direction="STILL")
            return self.info
        dt = t - self.prev_t
        dx, dy = point[0] - self.prev[0], point[1] - self.prev[1]
        k = self.smoothing
        vx = k * (dx / dt) + (1 - k) * self.info.vx
        vy = k * (dy / dt) + (1 - k) * self.info.vy
        speed = math.hypot(vx, vy)
        self.info = MotionInfo(dx, dy, vx, vy, speed, self.direction_name(vx, vy, speed))
        self.prev, self.prev_t = point, t
        return self.info

    def direction_name(self, vx: float, vy: float, speed: float) -> str:
        if speed < self.still_threshold:
            return "STILL"
        parts = []
        if abs(vy) > 0.4 * speed:
            parts.append("UP" if vy < 0 else "DOWN")
        if abs(vx) > 0.4 * speed:
            parts.append("LEFT" if vx < 0 else "RIGHT")
        return "-".join(parts)


# ---------------------------------------------------------------------------
# Whole-frame pipeline
# ---------------------------------------------------------------------------
@dataclass
class VisionSettings:
    hsv_range: HSVRange = field(default_factory=default_hsv_range)
    process_size: Tuple[int, int] = (config.PROCESS_W, config.PROCESS_H)
    blur_ksize: int = config.BLUR_KSIZE
    kernel_size: int = config.MORPH_KERNEL_SIZE
    open_iter: int = config.MORPH_OPEN_ITER
    close_iter: int = config.MORPH_CLOSE_ITER
    min_area: float = config.MIN_AREA
    mirror: bool = config.MIRROR
    extras: bool = False        # compute edge map / frame difference


@dataclass
class FrameResult:
    frame: np.ndarray           # processed (mirrored, resized, blurred) BGR
    raw_mask: np.ndarray        # straight HSV threshold
    mask: np.ndarray            # after morphology
    gray: np.ndarray
    detection: Detection
    point: Optional[Point]      # normalised centroid (0..1) or None
    edges: Optional[np.ndarray] = None
    motion_mask: Optional[np.ndarray] = None
    motion_energy: float = 0.0


def process_frame(frame_bgr: np.ndarray, settings: VisionSettings,
                  prev_gray: Optional[np.ndarray] = None) -> FrameResult:
    """Run the full segmentation pipeline on one frame."""
    small = preprocess(frame_bgr, settings.process_size, settings.blur_ksize, settings.mirror)
    hsv = bgr_to_hsv(small)
    raw = segment_hsv(hsv, settings.hsv_range)
    mask = clean_mask(raw, settings.kernel_size, settings.open_iter, settings.close_iter)
    det = find_marker(mask, settings.min_area)
    h, w = mask.shape[:2]
    point = (det.x / w, det.y / h) if det.found else None
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    result = FrameResult(small, raw, mask, gray, det, point)
    if settings.extras:
        result.edges = edge_map(gray)
        result.motion_mask, result.motion_energy = frame_difference(prev_gray, gray)
    return result


# ---------------------------------------------------------------------------
# Frame sources
# ---------------------------------------------------------------------------
class SyntheticSource:
    """Project-generated test video: a green disc moving on a noisy background.

    Used for demos and tests on machines without a webcam. It also draws a tiny
    green speck (should be rejected by MIN_AREA / opening) and a blue block (a
    differently coloured distractor). Clearly synthetic - not real camera data.
    """

    def __init__(self, size=(640, 480), fps: float = 30.0, seed: int = 7,
                 colour_bgr=(60, 200, 40), realtime: bool = True):
        self.w, self.h = size
        self.fps = fps
        self.realtime = realtime
        self.colour = colour_bgr
        self.rng = np.random.default_rng(seed)
        self.i = 0
        self._last = 0.0
        base = np.zeros((self.h, self.w, 3), np.uint8)
        base[:] = (40, 30, 30)
        self.base = cv2.add(base, self.rng.integers(0, 25, base.shape, dtype=np.uint8))

    def isOpened(self) -> bool:  # noqa: N802 - mimics cv2.VideoCapture
        return True

    def position(self, i: int) -> Point:
        t = i / self.fps
        return (0.5 + 0.38 * math.sin(t * 0.9), 0.5 + 0.32 * math.sin(t * 1.3 + 0.6))

    def read(self):
        if self.realtime:
            wait = 1.0 / self.fps - (time.perf_counter() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.perf_counter()
        frame = self.base.copy()
        cv2.rectangle(frame, (40, 360), (110, 430), (200, 90, 20), -1)    # blue distractor
        cv2.circle(frame, (560, 60), 2, self.colour, -1)                   # tiny speck
        nx, ny = self.position(self.i)
        # draw un-mirrored so that after the mirror step x matches position()
        cx = int((1.0 - nx) * self.w) if config.MIRROR else int(nx * self.w)
        cv2.circle(frame, (cx, int(ny * self.h)), 34, self.colour, -1)
        self.i += 1
        return True, frame

    def release(self) -> None:
        pass


class LoopingVideoSource:
    """Wraps cv2.VideoCapture on a file and rewinds at the end."""

    def __init__(self, path: str):
        self.cap = cv2.VideoCapture(path)
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.period = 1.0 / max(1.0, min(fps, 60.0))
        self._last = 0.0

    def isOpened(self) -> bool:  # noqa: N802
        return self.cap.isOpened()

    def read(self):
        wait = self.period - (time.perf_counter() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.perf_counter()
        ok, frame = self.cap.read()
        if not ok:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return ok, frame

    def release(self) -> None:
        self.cap.release()


def open_camera(index: int):
    """Open a webcam, trying Windows-friendly backends first."""
    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(cv2.CAP_DSHOW)
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(cv2.CAP_MSMF)
    backends.append(cv2.CAP_ANY)
    for backend in backends:
        try:
            cap = cv2.VideoCapture(index, backend)
        except cv2.error:
            continue
        if cap is not None and cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAPTURE_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAPTURE_H)
            return cap
        if cap is not None:
            cap.release()
    return None


def make_source_factory(spec) -> Callable[[], object]:
    """Build a source factory from a CLI spec: index, 'synthetic' or a file."""
    spec = str(spec)
    if spec.lower() == "synthetic":
        return SyntheticSource
    if spec.lstrip("-").isdigit():
        return lambda: open_camera(int(spec))
    return lambda: LoopingVideoSource(spec)


# ---------------------------------------------------------------------------
# Threaded tracker
# ---------------------------------------------------------------------------
class TrackerStatus:
    OFF = "OFF"
    CONNECTING = "CONNECTING"
    TRACKING = "TRACKING"
    HOLDING = "HOLDING"         # marker briefly lost, last position kept
    SEARCHING = "SEARCHING"     # camera fine, no marker visible
    NO_CAMERA = "NO CAMERA"
    ERROR = "ERROR"


@dataclass
class TrackerState:
    status: str = TrackerStatus.OFF
    message: str = ""
    position: Optional[Point] = None
    motion: MotionInfo = field(default_factory=MotionInfo)
    result: Optional[FrameResult] = None
    frame_id: int = 0
    fps: float = 0.0
    process_ms: float = 0.0


class VisionTracker:
    """Runs capture + processing on a daemon thread; the game polls snapshot()."""

    MAX_READ_FAILURES = 30

    def __init__(self, settings: Optional[VisionSettings] = None,
                 source_factory: Optional[Callable[[], object]] = None):
        self.settings = settings or VisionSettings()
        self.source_factory = source_factory or (lambda: open_camera(config.CAMERA_INDEX))
        self.smoother = PositionSmoother()
        self.motion = MotionEstimator()
        self._state = TrackerState()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sample_requested = False
        self.last_sample: Optional[HSVRange] = None

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self.smoother.reset()
        self._set(status=TrackerStatus.CONNECTING, message="Opening camera...")
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None
        self._set(status=TrackerStatus.OFF, message="Webcam off", position=None, result=None)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- public API ------------------------------------------------------------
    def snapshot(self) -> TrackerState:
        with self._lock:
            s = self._state
            return TrackerState(s.status, s.message, s.position, s.motion, s.result,
                                s.frame_id, s.fps, s.process_ms)

    def set_hsv_range(self, rng: HSVRange) -> None:
        self.settings.hsv_range = rng
        self.smoother.reset()

    def request_sample(self) -> None:
        """Calibrate from the centre box of the next frame."""
        self._sample_requested = True

    # -- internals -------------------------------------------------------------
    def _set(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self._state, k, v)

    def _run(self) -> None:
        try:
            source = self.source_factory()
        except Exception as exc:  # camera drivers can raise anything
            self._set(status=TrackerStatus.ERROR, message=f"Camera error: {exc}")
            return
        if source is None or not source.isOpened():
            self._set(status=TrackerStatus.NO_CAMERA,
                      message="No webcam found - keyboard control active")
            return
        failures = 0
        prev_gray = None
        frame_id = 0
        fps = 0.0
        last_t = time.perf_counter()
        try:
            while not self._stop.is_set():
                try:
                    ok, frame = source.read()
                except cv2.error:
                    ok, frame = False, None
                if not ok or frame is None:
                    failures += 1
                    if failures >= self.MAX_READ_FAILURES:
                        self._set(status=TrackerStatus.ERROR, position=None,
                                  message="Camera stopped sending frames")
                        return
                    time.sleep(0.03)
                    continue
                failures = 0
                t0 = time.perf_counter()
                result = process_frame(frame, self.settings, prev_gray)
                prev_gray = result.gray
                if self._sample_requested:
                    self._sample_requested = False
                    try:
                        hsv = bgr_to_hsv(result.frame)
                        rng = hsv_range_from_sample(centre_roi(hsv))
                        self.last_sample = rng
                        self.set_hsv_range(rng)
                    except ValueError:
                        pass
                pos = self.smoother.update(result.point)
                motion = self.motion.update(pos, t0)
                if result.detection.found:
                    status, msg = TrackerStatus.TRACKING, "Marker locked"
                elif pos is not None:
                    status, msg = TrackerStatus.HOLDING, "Marker lost - holding"
                else:
                    status, msg = TrackerStatus.SEARCHING, "Show the coloured marker"
                now = time.perf_counter()
                dt = now - last_t
                last_t = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
                frame_id += 1
                self._set(status=status, message=msg, position=pos, motion=motion,
                          result=result, frame_id=frame_id, fps=fps,
                          process_ms=(now - t0) * 1000.0)
        finally:
            try:
                source.release()
            except Exception:
                pass
