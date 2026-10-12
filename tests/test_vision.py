"""Image-processing tests on synthetic (project-generated) frames - no webcam."""

import numpy as np
import pytest

from src import vision
from src.vision import (HSVRange, MotionEstimator, PositionSmoother, SyntheticSource,
                        VisionSettings, bgr_to_hsv, clean_mask, edge_map, find_marker,
                        frame_difference, hsv_range_from_sample, preprocess, process_frame,
                        segment_hsv)

GREEN = HSVRange.preset("green")
RED = HSVRange.preset("red")


def test_bgr_to_hsv_shape_and_type(make_frame):
    hsv = bgr_to_hsv(make_frame())
    assert hsv.shape == (240, 320, 3) and hsv.dtype == np.uint8
    assert hsv[..., 0].max() <= 179  # OpenCV hue range


def test_segmentation_produces_binary_mask_of_disc(make_frame):
    frame = make_frame(centre=(100, 80), radius=20, hue=60)
    mask = segment_hsv(bgr_to_hsv(frame), GREEN)
    assert set(np.unique(mask)) <= {0, 255}
    area = np.count_nonzero(mask)
    assert abs(area - np.pi * 20 ** 2) < 0.1 * np.pi * 20 ** 2
    assert mask[80, 100] == 255 and mask[10, 10] == 0


def test_segmentation_rejects_other_colours(make_frame):
    blue = make_frame(hue=115)
    assert np.count_nonzero(segment_hsv(bgr_to_hsv(blue), GREEN)) == 0
    assert np.count_nonzero(segment_hsv(bgr_to_hsv(blue), HSVRange.preset("blue"))) > 1000


@pytest.mark.parametrize("hue", [2, 176])
def test_red_range_wraps_around_hue_zero(make_frame, hue):
    assert RED.wraps_hue
    mask = segment_hsv(bgr_to_hsv(make_frame(hue=hue)), RED)
    assert np.count_nonzero(mask) > 1000


def test_low_saturation_grey_is_not_detected(make_frame):
    grey = make_frame(centre=None, background=(128, 128, 128))
    assert np.count_nonzero(segment_hsv(bgr_to_hsv(grey), GREEN)) == 0


def test_opening_removes_isolated_noise_pixels():
    mask = np.zeros((100, 100), np.uint8)
    mask[30:60, 30:60] = 255                      # real object
    rng = np.random.default_rng(1)
    ys, xs = rng.integers(0, 100, 40), rng.integers(70, 100, 40)
    mask[ys, xs] = 255                            # salt noise
    cleaned = clean_mask(mask, kernel_size=5, open_iter=1, close_iter=0)
    assert np.count_nonzero(cleaned[:, 70:]) == 0
    assert np.count_nonzero(cleaned[35:55, 35:55]) == 400


def test_closing_fills_small_holes():
    mask = np.zeros((100, 100), np.uint8)
    mask[20:80, 20:80] = 255
    mask[48:52, 48:52] = 0                        # hole
    cleaned = clean_mask(mask, kernel_size=5, open_iter=0, close_iter=1)
    assert np.all(cleaned[48:52, 48:52] == 255)


def test_find_marker_centroid_is_accurate(make_frame):
    frame = make_frame(centre=(210, 150), radius=22, hue=60)
    det = find_marker(segment_hsv(bgr_to_hsv(frame), GREEN), min_area=50)
    assert det.found
    assert det.x == pytest.approx(210, abs=1.0) and det.y == pytest.approx(150, abs=1.0)
    x, y, w, h = det.bbox
    assert 40 <= w <= 46 and 40 <= h <= 46


def test_find_marker_picks_largest_blob_and_counts_rejections():
    mask = np.zeros((120, 160), np.uint8)
    mask[10:14, 10:14] = 255                      # 16 px speck (rejected)
    mask[60:100, 80:120] = 255                    # 40x40 object
    det = find_marker(mask, min_area=100)
    assert det.found and det.contour_count == 2 and det.rejected_small == 1
    assert det.x == pytest.approx(99.5, abs=1) and det.y == pytest.approx(79.5, abs=1)


def test_find_marker_ignores_blobs_below_min_area():
    mask = np.zeros((50, 50), np.uint8)
    mask[5:10, 5:10] = 255
    assert not find_marker(mask, min_area=150).found


def test_find_marker_on_empty_mask():
    det = find_marker(np.zeros((50, 50), np.uint8))
    assert not det.found and det.contour_count == 0


def test_preprocess_resizes_blurs_and_mirrors(make_frame):
    frame = make_frame(w=640, h=480, centre=(100, 240), radius=40)
    out = preprocess(frame, (320, 240), blur_ksize=5, mirror=True)
    assert out.shape == (240, 320, 3)
    det = find_marker(segment_hsv(bgr_to_hsv(out), GREEN), 50)
    assert det.x == pytest.approx(320 - 50, abs=2)   # mirrored: 100/640 -> 270/320


def test_gaussian_blur_reduces_noise_variance(make_frame):
    noisy = make_frame(centre=None, noise=60, seed=3)
    blurred = preprocess(noisy, None, blur_ksize=5)
    assert blurred.astype(float).std() < noisy.astype(float).std() * 0.6


def test_process_frame_returns_normalised_point(make_frame):
    settings = VisionSettings(hsv_range=GREEN, mirror=False, extras=True)
    res = process_frame(make_frame(centre=(80, 180), radius=25, noise=20), settings)
    assert res.detection.found
    assert res.point[0] == pytest.approx(0.25, abs=0.01)
    assert res.point[1] == pytest.approx(0.75, abs=0.01)
    assert res.edges is not None and np.count_nonzero(res.edges) > 0
    assert res.motion_energy == 0.0  # no previous frame


def test_process_frame_without_marker(make_frame):
    res = process_frame(make_frame(centre=None, noise=20), VisionSettings(hsv_range=GREEN))
    assert res.point is None and not res.detection.found


def test_frame_difference_measures_changed_pixels(make_frame):
    a = bgr_to_hsv(make_frame(centre=(100, 120)))[..., 2]
    b = bgr_to_hsv(make_frame(centre=(140, 120)))[..., 2]
    motion, energy = frame_difference(a, b)
    assert energy > 0.01 and motion.max() == 255
    _, same = frame_difference(a, a.copy())
    assert same == 0.0


def test_edge_map_finds_disc_boundary(make_frame):
    gray = bgr_to_hsv(make_frame(centre=(160, 120), radius=30))[..., 2]
    edges = edge_map(gray)
    assert edges[120, 160] == 0                    # interior is flat
    assert np.count_nonzero(edges[85:155, 125:195]) > 100


def test_position_smoother_reduces_jitter_and_holds():
    s = PositionSmoother(alpha=0.3, hold_frames=3)
    rng = np.random.default_rng(0)
    raw = [(0.5 + rng.normal(0, 0.02), 0.5 + rng.normal(0, 0.02)) for _ in range(200)]
    out = [s.update(p) for p in raw]
    assert np.std([p[0] for p in out[20:]]) < 0.6 * np.std([p[0] for p in raw[20:]])
    for _ in range(3):
        assert s.update(None) is not None and s.holding
    assert s.update(None) is None


def test_motion_estimator_velocity_and_direction():
    m = MotionEstimator(smoothing=1.0)
    m.update((0.2, 0.5), 0.0)
    info = m.update((0.3, 0.5), 0.1)
    assert info.dx == pytest.approx(0.1)
    assert info.vx == pytest.approx(1.0) and info.direction == "RIGHT"
    info = m.update((0.3, 0.4), 0.2)
    assert info.direction == "UP"
    assert m.update((0.3, 0.4), 0.3).direction == "STILL"
    assert m.update(None, 0.4).direction == "--"


def test_hsv_range_from_sample_detects_sampled_colour(make_frame):
    frame = make_frame(hue=100, noise=10)
    hsv = bgr_to_hsv(frame)
    rng = hsv_range_from_sample(hsv[110:130, 150:170])
    assert rng.lower[0] < 100 < rng.upper[0]
    assert np.count_nonzero(segment_hsv(hsv, rng)) > 1500
    assert np.count_nonzero(segment_hsv(bgr_to_hsv(make_frame(hue=60)), rng)) == 0


def test_hsv_range_from_red_sample_wraps(make_frame):
    hsv = bgr_to_hsv(make_frame(hue=178))
    patch = hsv[110:130, 150:170].copy()
    patch[::2, :, 0] = 1                           # mix of hue 178 and 1
    rng = hsv_range_from_sample(patch)
    assert rng.wraps_hue


def test_hsv_range_json_roundtrip(tmp_path):
    path = tmp_path / "hsv.json"
    assert vision.save_hsv_range(RED, path)
    loaded = vision.load_hsv_range(path)
    assert loaded == RED
    path.write_text("not json")
    assert vision.load_hsv_range(path) is None


def test_synthetic_video_is_tracked_frame_by_frame():
    src = SyntheticSource(realtime=False)
    settings = VisionSettings(hsv_range=GREEN)
    smoother, motion = PositionSmoother(alpha=1.0), MotionEstimator()
    prev = None
    errors = []
    for i in range(60):
        ok, frame = src.read()
        res = process_frame(frame, settings, prev)
        prev = res.gray
        assert res.detection.found, f"lost marker at frame {i}"
        # the 2-px green speck must never win over the real disc
        ex, ey = src.position(i)
        errors.append(np.hypot(res.point[0] - ex, res.point[1] - ey))
        motion.update(smoother.update(res.point), i / 30)
    assert max(errors) < 0.01
    assert motion.info.speed > 0
