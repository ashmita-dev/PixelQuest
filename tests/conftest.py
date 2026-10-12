"""Test setup: headless SDL and synthetic-frame helpers. No webcam is ever opened."""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402


def hsv_colour_bgr(h, s=220, v=220):
    """Convert one OpenCV HSV colour to BGR."""
    px = np.uint8([[[h, s, v]]])
    return tuple(int(c) for c in cv2.cvtColor(px, cv2.COLOR_HSV2BGR)[0, 0])


def synthetic_frame(w=320, h=240, centre=(160, 120), radius=25, hue=60,
                    background=(40, 30, 30), noise=0, seed=0):
    """Dark frame containing one filled disc of the given OpenCV hue (synthetic)."""
    frame = np.zeros((h, w, 3), np.uint8)
    frame[:] = background
    if noise:
        rng = np.random.default_rng(seed)
        frame = cv2.add(frame, rng.integers(0, noise, frame.shape, dtype=np.uint8))
    if centre is not None:
        cv2.circle(frame, (int(centre[0]), int(centre[1])), radius, hsv_colour_bgr(hue), -1)
    return frame


@pytest.fixture
def make_frame():
    return synthetic_frame


@pytest.fixture(autouse=True)
def isolate_runtime_files(tmp_path, monkeypatch):
    """Keep tests from touching the real highscore / calibration files."""
    from src import config
    monkeypatch.setattr(config, "HIGHSCORE_FILE", tmp_path / "highscore.json")
    monkeypatch.setattr(config, "HSV_CONFIG_FILE", tmp_path / "hsv_config.json")
