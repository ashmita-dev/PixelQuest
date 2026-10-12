"""Pixel Quest launcher.

    python main.py                 # webcam control (falls back to keyboard)
    python main.py --keyboard      # keyboard only, webcam never opened
    python main.py --camera 1      # use a different webcam index
    python main.py --camera synthetic   # project-generated test video, no webcam needed
    python main.py --marker blue   # start with a different HSV preset
"""

import argparse
import sys

from src import config


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Pixel Quest - webcam-controlled neon arcade game")
    p.add_argument("--keyboard", action="store_true", help="keyboard control only (no webcam)")
    p.add_argument("--camera", default=None,
                   help="webcam index (default 0), 'synthetic', or a video file path")
    p.add_argument("--marker", choices=sorted(config.MARKER_PRESETS), default=None,
                   help="HSV preset for the marker colour (default: saved calibration or green)")
    p.add_argument("--fullscreen", action="store_true", help="start in fullscreen")
    p.add_argument("--mute", action="store_true", help="disable sound")
    p.add_argument("--diag", action="store_true", help="start with vision diagnostics visible")
    # testing / documentation helpers
    p.add_argument("--start", choices=["menu", "play", "help"], default="menu",
                   help="initial screen")
    p.add_argument("--autopilot", action="store_true", help="demo bot flies the ship")
    p.add_argument("--seed", type=int, default=None, help="random seed for reproducible runs")
    p.add_argument("--frames", type=int, default=None,
                   help="exit after N frames with fixed timestep (smoke tests)")
    p.add_argument("--screenshot", default=None, help="save a PNG of the final frame")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    from src.game import HELP, Game

    game = Game(args)
    if args.start == "play":
        game.start_game()
    elif args.start == "help":
        game.set_state(HELP)
    frames = game.run(max_frames=args.frames, screenshot=args.screenshot)
    if args.frames:
        print(f"Pixel Quest ran {frames} frames OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
