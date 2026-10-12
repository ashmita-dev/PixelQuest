"""Central configuration for Pixel Quest.

Everything that a player or examiner may want to tune lives here: window size,
gameplay balance, colour palette and - most importantly - the image-processing
parameters used by ``src/vision.py``.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Window / timing
# ---------------------------------------------------------------------------
TITLE = "PIXEL QUEST"
SCREEN_W = 1280          # logical resolution; the window is scaled to fit
SCREEN_H = 720
FPS = 60

# ---------------------------------------------------------------------------
# Neon palette (RGB)
# ---------------------------------------------------------------------------
BG_TOP = (6, 4, 20)
BG_BOTTOM = (14, 6, 38)
CYAN = (0, 240, 255)
ELECTRIC_BLUE = (40, 120, 255)
VIOLET = (150, 80, 255)
MAGENTA = (255, 50, 200)
GOLD = (255, 210, 80)
WHITE = (235, 240, 255)
DIM = (120, 130, 170)
DANGER = (255, 70, 110)
OK_GREEN = (80, 255, 170)

# ---------------------------------------------------------------------------
# Gameplay balance
# ---------------------------------------------------------------------------
START_LIVES = 3
SHIP_RADIUS = 16                 # collision radius (smaller than the sprite)
SHIP_KEY_ACCEL = 3600.0          # px/s^2 for keyboard control
SHIP_KEY_MAX_SPEED = 620.0       # px/s
SHIP_KEY_DAMPING = 7.0           # velocity decay per second when no key held
SHIP_FOLLOW_RATE = 12.0          # how quickly the ship chases the webcam target
INVULN_TIME = 2.0                # seconds of invulnerability after a hit
SHIELD_TIME = 6.0                # seconds a power core shield lasts
LEVEL_DURATION = 25.0            # seconds per difficulty level
MAX_LEVEL = 12
CRYSTAL_POINTS = 10
CORE_POINTS = 50
SHIELD_SMASH_POINTS = 25
COMBO_STEP = 5                   # crystals needed per multiplier step
MAX_MULTIPLIER = 5
PLAY_MARGIN = 40                 # ship cannot leave this inner margin

# ---------------------------------------------------------------------------
# Image / video processing  (see docs/IVP_MAPPING.md)
# ---------------------------------------------------------------------------
# Camera index can be overridden with the PIXELQUEST_CAMERA environment
# variable or the --camera command-line option.
CAMERA_INDEX = int(os.environ.get("PIXELQUEST_CAMERA", "0"))
CAPTURE_W = 640                  # requested capture size (camera may ignore)
CAPTURE_H = 480
PROCESS_W = 320                  # frames are downscaled before processing
PROCESS_H = 240
MIRROR = True                    # flip horizontally so it feels like a mirror

BLUR_KSIZE = 5                   # Gaussian blur kernel (odd); 0/1 disables
MORPH_KERNEL_SIZE = 5            # elliptical structuring element size
MORPH_OPEN_ITER = 1              # opening = erosion then dilation (removes specks)
MORPH_CLOSE_ITER = 2             # closing = dilation then erosion (fills holes)
MIN_AREA = 150                   # px^2 at PROCESS_W x PROCESS_H; smaller blobs ignored
SMOOTHING_ALPHA = 0.35           # exponential moving average weight of new sample
LOST_HOLD_FRAMES = 8             # keep last position this many frames after loss
MOTION_SMOOTHING = 0.5           # EMA factor for velocity estimate
MOTION_STILL_THRESHOLD = 0.08    # normalised units / s considered "still"
FRAME_DIFF_THRESHOLD = 25        # grey-level change counted as motion
CANNY_LOW = 60
CANNY_HIGH = 150
SAMPLE_BOX = 24                  # side of centre square used for colour sampling
CONTROL_MARGIN = 0.12            # outer camera border that maps to screen edge

# HSV ranges use OpenCV conventions: H 0-179, S 0-255, V 0-255.
# If lower hue > upper hue the range wraps around 180 (needed for red).
MARKER_PRESETS = {
    "green":  ((40, 80, 60),   (85, 255, 255)),
    "blue":   ((95, 120, 60),  (130, 255, 255)),
    "red":    ((170, 120, 70), (8, 255, 255)),
    "yellow": ((20, 110, 110), (34, 255, 255)),
    "orange": ((8, 150, 120),  (20, 255, 255)),
    "pink":   ((140, 80, 90),  (169, 255, 255)),
}
DEFAULT_MARKER = os.environ.get("PIXELQUEST_MARKER", "green")

# Files written at runtime (git-ignored)
HSV_CONFIG_FILE = PROJECT_ROOT / "hsv_config.json"
HIGHSCORE_FILE = PROJECT_ROOT / "highscore.json"
