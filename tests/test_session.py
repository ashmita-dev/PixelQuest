"""Game logic: collisions, scoring, lives, shield, difficulty and movement."""

import pytest

from src import config
from src.entities import Asteroid, Crystal, Drone, PowerCore
from src.session import GameSession


def session():
    return GameSession(seed=1, spawning=False)


def place(s, entity):
    entity.x, entity.y = s.ship.x, s.ship.y
    entity.vx = entity.vy = 0
    s.entities.append(entity)
    return entity


def kinds(events):
    return [e.kind for e in events]


def test_collecting_crystal_scores_and_removes_it():
    s = session()
    place(s, Crystal(0, 0))
    ev = s.check_collisions()
    assert kinds(ev) == ["collect"]
    assert s.score == config.CRYSTAL_POINTS and s.streak == 1
    s.update(0.0)
    assert s.entities == []


def test_combo_multiplier_grows_with_streak():
    s = session()
    for _ in range(config.COMBO_STEP):
        place(s, Crystal(0, 0))
        s.check_collisions()
    assert s.multiplier == 2
    place(s, Crystal(0, 0))
    ev = s.check_collisions()
    assert ev[0].value == config.CRYSTAL_POINTS * 2


def test_far_objects_do_not_collide():
    s = session()
    c = Crystal(s.ship.x + 200, s.ship.y, 0, 0)
    s.entities.append(c)
    assert s.check_collisions() == [] and c.alive


def test_hit_costs_life_resets_streak_and_grants_invulnerability():
    s = session()
    s.streak = 7
    place(s, Asteroid(0, 0, radius=20))
    assert kinds(s.check_collisions()) == ["hit"]
    assert s.lives == config.START_LIVES - 1 and s.streak == 0
    assert s.ship.invuln == pytest.approx(config.INVULN_TIME)
    place(s, Asteroid(0, 0, radius=20))
    assert s.check_collisions() == []          # invulnerable
    assert s.lives == config.START_LIVES - 1


def test_game_over_after_last_life():
    s = session()
    for _ in range(config.START_LIVES):
        s.ship.invuln = 0
        place(s, Drone(0, 0))
        events = s.check_collisions()
    assert s.lives == 0 and s.over and "gameover" in kinds(events)
    assert s.update(0.1) == []                 # frozen after game over


def test_power_core_shield_smashes_hazards():
    s = session()
    place(s, PowerCore(0, 0))
    assert kinds(s.check_collisions()) == ["core"]
    assert s.ship.shield > 0 and s.score == config.CORE_POINTS
    place(s, Asteroid(0, 0, radius=20))
    assert kinds(s.check_collisions()) == ["smash"]
    assert s.lives == config.START_LIVES
    assert s.score == config.CORE_POINTS + config.SHIELD_SMASH_POINTS


def test_level_progression_increases_speed():
    s = session()
    events = []
    for _ in range(int(config.LEVEL_DURATION / 0.05) + 2):
        events += s.update(0.05)
    assert s.level == 2 and "levelup" in kinds(events)
    assert s.speed_factor > 1.0
    assert s.hazard_interval < GameSession().hazard_interval


def test_spawning_creates_entities_and_offscreen_ones_are_removed():
    s = GameSession(seed=3)
    for _ in range(120):
        s.update(1 / 60)
    assert any(e.kind == "crystal" for e in s.entities)
    assert any(e.kind == "asteroid" for e in s.entities)
    for e in s.entities:
        e.y = s.h + 500
    s.update(1 / 60)
    assert all(e.y < s.h for e in s.entities)


def test_keyboard_moves_ship_and_bounds_clamp():
    s = session()
    x0 = s.ship.x
    for _ in range(10):
        s.update(1 / 60, key_dir=(1, 0))
    assert s.ship.x > x0
    for _ in range(600):
        s.update(1 / 60, key_dir=(1, -1))
    assert s.ship.x == s.bounds.right and s.ship.y == s.bounds.top


def test_webcam_target_pulls_ship_and_keyboard_overrides():
    s = session()
    target = (s.bounds.left + 50, s.bounds.top + 50)
    for _ in range(120):
        s.update(1 / 60, target=target)
    assert s.ship.x == pytest.approx(target[0], abs=2) and s.ship.y == pytest.approx(target[1], abs=2)
    for _ in range(30):
        s.update(1 / 60, key_dir=(1, 0), target=target)
    assert s.ship.x > target[0] + 50
