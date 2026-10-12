"""Interactive HSV threshold tuner (OpenCV trackbars).

    python scripts/calibrate_hsv.py                 # webcam 0
    python scripts/calibrate_hsv.py --camera 1
    python scripts/calibrate_hsv.py --camera synthetic
    python scripts/calibrate_hsv.py --preset red

Windows: "Pixel Quest - camera" (frame + detected centre) and
"Pixel Quest - mask" (cleaned binary mask). Drag the sliders until only the
marker is white. Keys: S = save to hsv_config.json (the game loads it on start),
K = sample the colour inside the centre box, Q/Esc = quit without saving.
If H min > H max the hue range wraps around 180 (useful for red).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from src import config  # noqa: E402
from src.vision import (HSVRange, VisionSettings, bgr_to_hsv, centre_roi, default_hsv_range,  # noqa: E402
                        hsv_range_from_sample, make_source_factory, process_frame, save_hsv_range)

WIN, MASK = "Pixel Quest - camera", "Pixel Quest - mask"
SLIDERS = [("H min", 179), ("S min", 255), ("V min", 255), ("H max", 179), ("S max", 255), ("V max", 255)]


def set_sliders(rng: HSVRange) -> None:
    for (name, _), val in zip(SLIDERS, (*rng.lower, *rng.upper)):
        cv2.setTrackbarPos(name, MASK, int(val))


def read_sliders() -> HSVRange:
    v = [cv2.getTrackbarPos(name, MASK) for name, _ in SLIDERS]
    return HSVRange(tuple(v[:3]), tuple(v[3:]), "custom")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--camera", default=str(config.CAMERA_INDEX))
    p.add_argument("--preset", choices=sorted(config.MARKER_PRESETS), default=None)
    args = p.parse_args()

    source = make_source_factory(args.camera)()
    if source is None or not source.isOpened():
        print("Could not open the camera. Try --camera 1 or check Windows camera privacy settings.")
        return 1
    start = HSVRange.preset(args.preset) if args.preset else default_hsv_range()
    cv2.namedWindow(WIN)
    cv2.namedWindow(MASK)
    for name, maximum in SLIDERS:
        cv2.createTrackbar(name, MASK, 0, maximum, lambda _v: None)
    set_sliders(start)
    print(__doc__)
    try:
        while True:
            ok, frame = source.read()
            if not ok:
                print("Camera stopped sending frames.")
                return 1
            settings = VisionSettings(hsv_range=read_sliders())
            res = process_frame(frame, settings)
            view = res.frame.copy()
            h, w = view.shape[:2]
            half = config.SAMPLE_BOX // 2
            cv2.rectangle(view, (w // 2 - half, h // 2 - half), (w // 2 + half, h // 2 + half), (255, 255, 255), 1)
            if res.detection.found:
                x, y, bw, bh = res.detection.bbox
                cv2.rectangle(view, (x, y), (x + bw, y + bh), (0, 255, 255), 1)
                cv2.drawMarker(view, (int(res.detection.x), int(res.detection.y)), (255, 0, 255),
                               cv2.MARKER_CROSS, 14, 2)
            txt = f"area {res.detection.area:.0f}  {'FOUND' if res.detection.found else 'none'}"
            cv2.putText(view, txt, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.imshow(WIN, cv2.resize(view, (640, 480), interpolation=cv2.INTER_NEAREST))
            cv2.imshow(MASK, cv2.resize(np.hstack([res.raw_mask, res.mask]), (640, 240)))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                return 0
            if key == ord("k"):
                rng = hsv_range_from_sample(centre_roi(bgr_to_hsv(res.frame)))
                set_sliders(rng)
                print("Sampled", rng.describe())
            if key == ord("s"):
                rng = read_sliders()
                if save_hsv_range(rng):
                    print(f"Saved {rng.describe()} to {config.HSV_CONFIG_FILE}")
                return 0
    finally:
        source.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    sys.exit(main())
