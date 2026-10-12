"""Collectibles and obstacles. Logic is display-independent; draw() is optional."""

from __future__ import annotations

import math
import random

import pygame

from . import config
from .effects import blit_glow


class Entity:
    kind = "entity"
    radius = 12.0
    colour = config.WHITE

    def __init__(self, x: float, y: float, vx: float = 0.0, vy: float = 120.0):
        self.x, self.y, self.vx, self.vy = float(x), float(y), vx, vy
        self.alive = True
        self.age = 0.0

    def update(self, dt: float) -> None:
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def offscreen(self, w: int, h: int) -> bool:
        r = self.radius * 2
        return self.y - r > h or self.x < -r * 3 or self.x > w + r * 3

    def collides(self, x: float, y: float, r: float) -> bool:
        return math.hypot(self.x - x, self.y - y) < self.radius + r

    def draw(self, surf: pygame.Surface, t: float) -> None:  # pragma: no cover - visual
        pygame.draw.circle(surf, self.colour, (int(self.x), int(self.y)), int(self.radius))


# --------------------------------------------------------------------------- pickups
class Crystal(Entity):
    """Energy crystal: the basic collectible."""

    kind = "crystal"
    radius = 14.0
    colour = config.CYAN
    points = config.CRYSTAL_POINTS

    def draw(self, surf, t):
        x, y = self.x, self.y + math.sin(self.age * 4) * 3
        s = 12 + math.sin(self.age * 6) * 1.5
        blit_glow(surf, (int(x), int(y)), 34, (0, 140, 170), 0.9)
        a = self.age * 2.2
        w = abs(math.cos(a)) * 0.6 + 0.4  # fake 3-D spin
        pts = [(x, y - s * 1.3), (x + s * w, y), (x, y + s * 1.3), (x - s * w, y)]
        pygame.draw.polygon(surf, (20, 90, 120), pts)
        pygame.draw.polygon(surf, self.colour, pts, 2)
        pygame.draw.line(surf, config.WHITE, (x, y - s * 1.3), (x, y + s * 1.3), 1)


class PowerCore(Entity):
    """Rare pickup: big points and a temporary shield."""

    kind = "core"
    radius = 16.0
    colour = config.GOLD
    points = config.CORE_POINTS

    def draw(self, surf, t):
        x, y = int(self.x), int(self.y)
        pulse = 0.5 + 0.5 * math.sin(self.age * 8)
        blit_glow(surf, (x, y), int(44 + 8 * pulse), (150, 110, 20), 1.0)
        pts = []
        for i in range(10):
            r = 17 if i % 2 == 0 else 8
            a = self.age * 1.5 + i * math.pi / 5
            pts.append((x + math.cos(a) * r, y + math.sin(a) * r))
        pygame.draw.polygon(surf, (120, 80, 10), pts)
        pygame.draw.polygon(surf, self.colour, pts, 2)
        pygame.draw.circle(surf, config.WHITE, (x, y), 4)


# --------------------------------------------------------------------------- hazards
class Asteroid(Entity):
    kind = "asteroid"
    colour = config.VIOLET

    def __init__(self, x, y, vx=0.0, vy=150.0, radius=None, rng: random.Random | None = None):
        super().__init__(x, y, vx, vy)
        rng = rng or random
        self.radius = radius if radius is not None else rng.uniform(18, 38)
        self.spin = rng.uniform(-2.0, 2.0)
        self.angle = rng.uniform(0, math.tau)
        n = rng.randint(8, 11)
        self.shape = [(math.tau * i / n, rng.uniform(0.75, 1.15)) for i in range(n)]

    def update(self, dt):
        super().update(dt)
        self.angle += self.spin * dt

    def points_list(self):
        return [(self.x + math.cos(a + self.angle) * self.radius * k,
                 self.y + math.sin(a + self.angle) * self.radius * k) for a, k in self.shape]

    def draw(self, surf, t):
        blit_glow(surf, (int(self.x), int(self.y)), int(self.radius * 2.0), (70, 20, 110), 0.8)
        pts = self.points_list()
        pygame.draw.polygon(surf, (30, 14, 50), pts)
        pygame.draw.polygon(surf, self.colour, pts, 2)
        cx, cy = self.x + math.cos(self.angle) * self.radius * 0.3, self.y + math.sin(self.angle) * self.radius * 0.3
        pygame.draw.circle(surf, (90, 40, 150), (int(cx), int(cy)), max(2, int(self.radius * 0.22)), 1)


class Drone(Entity):
    """Hunter drone: weaves sideways in a sine pattern (appears from level 3)."""

    kind = "drone"
    radius = 16.0
    colour = config.MAGENTA

    def __init__(self, x, y, vy=170.0, amplitude=140.0, freq=1.6, phase=0.0):
        super().__init__(x, y, 0.0, vy)
        self.base_x = x
        self.amplitude, self.freq, self.phase = amplitude, freq, phase

    def update(self, dt):
        self.age += dt
        self.y += self.vy * dt
        self.x = self.base_x + math.sin(self.age * self.freq * math.tau / 2 + self.phase) * self.amplitude

    def draw(self, surf, t):
        x, y = int(self.x), int(self.y)
        blit_glow(surf, (x, y), 40, (150, 20, 110), 1.0)
        a = self.age * 5
        for i in range(3):
            ang = a + i * math.tau / 3
            pygame.draw.line(surf, self.colour, (x, y),
                             (x + math.cos(ang) * 20, y + math.sin(ang) * 20), 2)
        pygame.draw.circle(surf, (50, 10, 40), (x, y), 11)
        pygame.draw.circle(surf, self.colour, (x, y), 11, 2)
        eye = 0.5 + 0.5 * math.sin(self.age * 12)
        pygame.draw.circle(surf, (255, int(80 + 150 * eye), 200), (x, y), 4)


PICKUP_KINDS = {"crystal", "core"}
HAZARD_KINDS = {"asteroid", "drone"}
