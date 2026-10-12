"""One run of the game: spawning, collisions, scoring, lives and difficulty.

Contains no rendering or input handling so it can be unit-tested headlessly.
``update`` returns a list of events that the presentation layer turns into
particles, sounds and text.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

from . import config
from .entities import Asteroid, Crystal, Drone, Entity, PowerCore
from .player import Ship


@dataclass
class Event:
    kind: str                   # collect | core | hit | smash | levelup | gameover
    x: float = 0.0
    y: float = 0.0
    value: int = 0
    colour: Tuple[int, int, int] = config.WHITE


class GameSession:
    def __init__(self, width: int = config.SCREEN_W, height: int = config.SCREEN_H,
                 seed: Optional[int] = None, spawning: bool = True):
        self.w, self.h = width, height
        self.rng = random.Random(seed)
        m = config.PLAY_MARGIN
        self.bounds = pygame.Rect(m, m + 40, width - 2 * m, height - 2 * m - 40)
        self.ship = Ship(width / 2, height * 0.78, self.bounds)
        self.entities: List[Entity] = []
        self.spawning = spawning
        self.score_float = 0.0
        self.lives = config.START_LIVES
        self.level = 1
        self.elapsed = 0.0
        self.streak = 0
        self.best_streak = 0
        self.crystals = 0
        self.over = False
        self._t_crystal = 0.5
        self._t_hazard = 1.2
        self._t_core = 12.0
        self._t_drone = 6.0

    # ------------------------------------------------------------------ stats
    @property
    def score(self) -> int:
        return int(self.score_float)

    @property
    def multiplier(self) -> int:
        return min(config.MAX_MULTIPLIER, 1 + self.streak // config.COMBO_STEP)

    @property
    def speed_factor(self) -> float:
        return 1.0 + 0.12 * (self.level - 1)

    @property
    def hazard_interval(self) -> float:
        return max(0.32, 1.25 - 0.09 * (self.level - 1))

    # ------------------------------------------------------------------ spawning
    def _spawn(self) -> None:
        r = self.rng
        x = r.uniform(self.bounds.left + 20, self.bounds.right - 20)
        sf = self.speed_factor
        if self._t_crystal <= 0:
            self.entities.append(Crystal(x, -20, r.uniform(-20, 20), r.uniform(130, 190) * sf))
            self._t_crystal = r.uniform(0.55, 1.0)
        if self._t_hazard <= 0:
            ax = r.uniform(self.bounds.left, self.bounds.right)
            self.entities.append(Asteroid(ax, -50, r.uniform(-40, 40),
                                          r.uniform(140, 220) * sf, rng=r))
            self._t_hazard = self.hazard_interval * r.uniform(0.7, 1.3)
        if self._t_core <= 0:
            self.entities.append(PowerCore(x, -20, 0, 150 * sf))
            self._t_core = r.uniform(13, 20)
        if self.level >= 3 and self._t_drone <= 0:
            dx = r.uniform(self.bounds.left + 160, self.bounds.right - 160)
            self.entities.append(Drone(dx, -30, 160 * sf, r.uniform(80, 160), r.uniform(1.0, 2.0),
                                       r.uniform(0, 6.28)))
            self._t_drone = max(2.5, 8.0 - 0.5 * self.level) * r.uniform(0.8, 1.2)

    # ------------------------------------------------------------------ update
    def update(self, dt: float, key_dir=(0.0, 0.0), target=None) -> List[Event]:
        events: List[Event] = []
        if self.over:
            return events
        dt = min(dt, 0.05)  # avoid tunnelling after a stall
        self.elapsed += dt
        new_level = min(config.MAX_LEVEL, 1 + int(self.elapsed // config.LEVEL_DURATION))
        if new_level > self.level:
            self.level = new_level
            events.append(Event("levelup", self.w / 2, self.h / 2, new_level, config.CYAN))
        self.score_float += dt * self.level  # small survival bonus

        if self.spawning:
            self._t_crystal -= dt
            self._t_hazard -= dt
            self._t_core -= dt
            self._t_drone -= dt
            self._spawn()

        self.ship.update(dt, key_dir, target)
        for e in self.entities:
            e.update(dt)
        events.extend(self.check_collisions())
        self.entities = [e for e in self.entities if e.alive and not e.offscreen(self.w, self.h)]
        return events

    def check_collisions(self) -> List[Event]:
        events: List[Event] = []
        s = self.ship
        for e in self.entities:
            if not e.alive or not e.collides(s.x, s.y, s.radius):
                continue
            if e.kind == "crystal":
                e.alive = False
                self.streak += 1
                self.crystals += 1
                self.best_streak = max(self.best_streak, self.streak)
                pts = e.points * self.multiplier
                self.score_float += pts
                events.append(Event("collect", e.x, e.y, pts, e.colour))
            elif e.kind == "core":
                e.alive = False
                self.score_float += e.points
                s.shield = config.SHIELD_TIME
                events.append(Event("core", e.x, e.y, e.points, e.colour))
            elif s.shield > 0:
                e.alive = False
                self.score_float += config.SHIELD_SMASH_POINTS
                events.append(Event("smash", e.x, e.y, config.SHIELD_SMASH_POINTS, e.colour))
            elif s.invuln <= 0:
                e.alive = False
                self.lives -= 1
                self.streak = 0
                s.invuln = config.INVULN_TIME
                events.append(Event("hit", s.x, s.y, self.lives, config.DANGER))
                if self.lives <= 0:
                    self.over = True
                    events.append(Event("gameover", s.x, s.y, self.score, config.DANGER))
                    break
        return events
