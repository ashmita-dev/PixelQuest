"""Render real screenshots of the game for the docs (headless, no webcam).

    python scripts/capture_screenshots.py

The vision diagnostics in these screenshots are fed by the project's
SYNTHETIC video source (see src/vision.py: SyntheticSource), not a real
webcam, and gameplay is flown by the demo autopilot. Captions in the report
say so.
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

import main  # noqa: E402
from src import config  # noqa: E402
from src import game as g_mod  # noqa: E402

OUT = ROOT / "docs" / "images"


def run(game, seconds):
    for _ in range(int(seconds * 60)):
        game.update(1 / 60)
        game.draw()
        time.sleep(0.002)  # let the vision thread deliver frames


def save(game, name):
    pygame.image.save(game.screen, str(OUT / name))
    print("saved", name)


def main_() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    config.HIGHSCORE_FILE = OUT / "_tmp_highscore.json"   # don't touch the real one
    game = g_mod.Game(main.parse_args(["--camera", "synthetic", "--marker", "green", "--mute", "--seed", "5"]))
    game.vstate = game.tracker.snapshot()
    run(game, 1.5)
    save(game, "screen_menu.png")
    game.set_state(g_mod.HELP)
    run(game, 1.0)
    save(game, "screen_help.png")
    game.set_state(g_mod.MENU)
    game.autopilot = g_mod.Autopilot()
    game.start_game()
    run(game, 14)
    save(game, "screen_gameplay.png")
    game.toggle_diag()
    run(game, 2.0)
    save(game, "screen_diagnostics.png")
    game.toggle_diag()
    game.set_state(g_mod.PAUSE)
    run(game, 0.8)
    save(game, "screen_pause.png")
    game.set_state(g_mod.PLAY)
    game.autopilot = None
    game.session.lives = 1
    game.session.ship.invuln = game.session.ship.shield = 0
    from src.entities import Asteroid
    while not game.session.over:  # keep dropping an asteroid on the ship until it is hit
        game.session.entities.append(Asteroid(game.session.ship.x, game.session.ship.y, 0, 0, radius=30))
        run(game, 1 / 60)
    run(game, 3.0)
    save(game, "screen_gameover.png")
    game.tracker.stop()
    pygame.quit()
    config.HIGHSCORE_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main_()
