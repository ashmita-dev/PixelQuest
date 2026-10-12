"""Application start-up, keyboard fallback and state transitions (headless SDL)."""

import pygame
import pytest

import main
from src import game as game_mod
from src.ui import reset_caches
from src.vision import TrackerStatus


def make_game(*argv):
    return game_mod.Game(main.parse_args(["--mute", *argv]))


def press(g, key):
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def step(g, n=1):
    for _ in range(n):
        g.update(1 / 60)
        g.draw()


@pytest.fixture
def keyboard_game():
    g = make_game("--keyboard", "--seed", "4")
    g.vstate = g.tracker.snapshot()
    yield g
    g.tracker.stop()
    reset_caches()
    pygame.quit()


def test_dependencies_import():
    import cv2
    import numpy
    assert cv2.__version__ and numpy.__version__ and pygame.version.ver


def test_main_runs_headless_frames(capsys):
    assert main.main(["--keyboard", "--mute", "--frames", "20"]) == 0
    assert "ran 20 frames" in capsys.readouterr().out


def test_menu_to_play_pause_and_back(keyboard_game):
    g = keyboard_game
    assert g.state == game_mod.MENU and g.control == "keyboard"
    press(g, pygame.K_RETURN)
    assert g.state == game_mod.PLAY
    step(g, 5)
    press(g, pygame.K_p)
    assert g.state == game_mod.PAUSE
    press(g, pygame.K_ESCAPE)
    assert g.state == game_mod.PLAY
    press(g, pygame.K_m)
    assert g.state == game_mod.MENU


def test_game_over_screen_and_restart(keyboard_game):
    g = keyboard_game
    g.start_game()
    g.session.lives = 1
    g.session.ship.invuln = 0
    from src.entities import Asteroid
    a = Asteroid(g.session.ship.x, g.session.ship.y, 0, 0, radius=30)
    g.session.entities.append(a)
    step(g, 100)
    assert g.state == game_mod.OVER
    assert game_mod.load_highscore() == g.session.score
    press(g, pygame.K_r)
    assert g.state == game_mod.PLAY and g.session.lives == 3


def test_diagnostics_toggle_does_not_interrupt_play(keyboard_game):
    g = keyboard_game
    g.start_game()
    step(g, 3)
    press(g, pygame.K_TAB)
    assert g.show_diag and g.vision_settings.extras
    step(g, 3)
    assert g.state == game_mod.PLAY
    press(g, pygame.K_TAB)
    assert not g.show_diag


def test_webcam_failure_falls_back_to_keyboard_input():
    g = make_game("--camera", "no_such_camera_file.avi")
    g.vstate = g.tracker.snapshot()
    try:
        for _ in range(200):
            step(g)
            if g.vstate.status == TrackerStatus.NO_CAMERA:
                break
        assert g.vstate.status == TrackerStatus.NO_CAMERA
        assert any("keyboard" in t[0].lower() for t in g.toasts)
        g.start_game()
        g.session.spawning = False
        x0 = g.session.ship.x
        for _ in range(20):
            g.session.update(1 / 60, key_dir=(1, 0), target=g.webcam_point(g.vstate))
        assert g.session.ship.x > x0
    finally:
        g.tracker.stop()
        reset_caches()
        pygame.quit()


def test_synthetic_camera_drives_ship(tmp_path):
    g = make_game("--camera", "synthetic", "--marker", "green")
    g.vstate = g.tracker.snapshot()
    try:
        g.start_game()
        import time
        end = time.time() + 5
        while time.time() < end and g.vstate.status != TrackerStatus.TRACKING:
            step(g)
        assert g.vstate.status == TrackerStatus.TRACKING
        assert g.webcam_point(g.vstate) is not None
    finally:
        g.tracker.stop()
        reset_caches()
        pygame.quit()


def test_toggle_control_mode(keyboard_game):
    g = keyboard_game
    g.tracker.source_factory = lambda: None   # never touch a real webcam in tests
    press(g, pygame.K_c)
    assert g.control == "webcam" and "WEBCAM" in g.buttons[game_mod.MENU][1].label
    press(g, pygame.K_c)
    assert g.control == "keyboard"
