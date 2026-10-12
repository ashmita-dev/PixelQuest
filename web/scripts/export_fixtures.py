"""Export OpenCV reference results for the web port's cross-check tests.

    .venv\\Scripts\\python web\\scripts\\export_fixtures.py

Uses the desktop pipeline (src/vision.py, OpenCV) on project-generated
SYNTHETIC frames and writes web/tests/fixtures/: raw RGBA frames plus
OpenCV's blurred HSV, raw mask, cleaned mask and centroid. The JS tests then
check that web/public/js/vision.js reproduces them.
"""

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from generate_samples import scene  # noqa: E402
from src.vision import (HSVRange, VisionSettings, bgr_to_hsv, clean_mask, preprocess,  # noqa: E402
                        process_frame, segment_hsv)

OUT = ROOT / "web" / "tests" / "fixtures"
CASES = [  # name, seed, centre (640x480 coords), hue, preset
    ("green_centre", 1, (320, 240), 60, "green"),
    ("green_left", 2, (140, 160), 60, "green"),
    ("red_wrap", 3, (500, 200), 178, "red"),
    ("no_marker", 5, None, 60, "green"),
]


def b64(mask: np.ndarray) -> str:
    return base64.b64encode((mask > 0).astype(np.uint8).tobytes()).decode()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    expected = []
    for name, seed, centre, hue, preset in CASES:
        frame = cv2.resize(scene(seed, centre, hue=hue), (320, 240), interpolation=cv2.INTER_AREA)
        rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        (OUT / f"{name}.rgba").write_bytes(rgba.tobytes())
        rng = HSVRange.preset(preset)
        settings = VisionSettings(hsv_range=rng, mirror=False)
        res = process_frame(frame, settings)
        blurred = preprocess(frame, None, settings.blur_ksize)
        hsv = bgr_to_hsv(blurred)
        raw = segment_hsv(hsv, rng)
        d = res.detection
        expected.append({
            "name": name, "synthetic": True, "preset": preset, "width": 320, "height": 240,
            "hsv_blurred_b64": base64.b64encode(hsv.tobytes()).decode(),
            "raw_mask_b64": b64(raw),
            "clean_mask_b64": b64(clean_mask(raw)),
            "found": bool(d.found), "x": d.x, "y": d.y, "area": d.area,
        })
    (OUT / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    print(f"wrote {len(CASES)} fixtures to {OUT}")


if __name__ == "__main__":
    main()
