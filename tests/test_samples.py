"""Checks the committed synthetic sample images against their ground-truth manifest."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.vision import HSVRange, MotionEstimator, VisionSettings, process_frame

SAMPLES = Path(__file__).resolve().parent.parent / "assets" / "samples"
MANIFEST = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
PRESET_FOR_HUE = {60: "green", 178: "red", 110: "blue"}


@pytest.mark.parametrize("entry", MANIFEST, ids=[m["file"] for m in MANIFEST])
def test_sample_centroid_matches_ground_truth(entry):
    assert entry["synthetic"] is True
    frame = cv2.imread(str(SAMPLES / entry["file"]))
    assert frame is not None and frame.shape[:2] == (480, 640)
    preset = PRESET_FOR_HUE.get(entry["marker_hue"], "green")
    res = process_frame(frame, VisionSettings(hsv_range=HSVRange.preset(preset), mirror=False))
    if entry["marker_centre_px"] is None:
        assert not res.detection.found     # distractors must not trigger the green preset
        return
    assert res.detection.found
    gx, gy = entry["marker_centre_px"]
    err_px = np.hypot(res.point[0] * 640 - gx, res.point[1] * 480 - gy)
    if entry["marker_selected_expected"]:
        assert err_px < 3.0
    else:
        # documented limitation: a larger same-coloured object beats the marker
        assert err_px > 50


def test_sequence_motion_direction():
    seq = sorted((m for m in MANIFEST if m["file"].startswith("sequence/")), key=lambda m: m["file"])
    est = MotionEstimator(smoothing=1.0)
    settings = VisionSettings(hsv_range=HSVRange.preset("green"), mirror=False)
    for i, m in enumerate(seq):
        res = process_frame(cv2.imread(str(SAMPLES / m["file"])), settings)
        info = est.update(res.point, i / 30)
        if i:
            truth_dx = (m["marker_centre_px"][0] - seq[i - 1]["marker_centre_px"][0]) / 640
            assert info.dx == pytest.approx(truth_dx, abs=0.005)
            assert "RIGHT" in info.direction
