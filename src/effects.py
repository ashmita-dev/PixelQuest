"""Visual effects: parallax starfield, additive particles, glow sprites, shake."""

from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from . import config


@lru_cache(maxsize=2048)
def glow_sprite(radius: int, colour: tuple, intensity: float = 1.0) -> pygame.Surface:
    """Pre-rendered radial glow, meant to be blitted with BLEND_RGB_ADD."""
    radius = max(2, int(radius))
    size = radius * 2
    surf = pygame.Surface((size, size))
    surf.fill((0, 0, 0))
    steps = min(radius, 24)
    for i in range(steps, 0, -1):
        r = radius * i / steps
        f = (1.0 - i / steps) ** 2 * intensity
        c = tuple(min(255, int(ch * f)) for ch in colour)
        pygame.draw.circle(surf, c, (radius, radius), int(r))
    return surf


def blit_glow(target: pygame.Surface, pos, radius: int, colour, intensity: float = 1.0) -> None:
    spr = glow_sprite(int(radius), tuple(colour), round(intensity, 2))
    target.blit(spr, (pos[0] - spr.get_width() // 2, pos[1] - spr.get_height() // 2),
                special_flags=pygame.BLEND_RGB_ADD)


def make_background(w: int, h: int) -> pygame.Surface:
    """Vertical gradient with a faint nebula."""
    bg = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        c = [int(a + (b - a) * t) for a, b in zip(config.BG_TOP, config.BG_BOTTOM)]
        pygame.draw.line(bg, c, (0, y), (w, y))
    rnd = random.Random(3)
    for _ in range(6):
        col = rnd.choice([(30, 8, 60), (8, 20, 60), (40, 6, 40)])
        blit_glow(bg, (rnd.randint(0, w), rnd.randint(0, h)), rnd.randint(180, 360), col, 1.0)
    return bg


class Starfield:
    """Three layers of stars scrolling at different speeds (parallax)."""

    LAYERS = ((90, 18, 1, 90), (60, 45, 1, 160), (28, 110, 2, 235))  # count, speed, size, brightness

    def __init__(self, w: int, h: int, seed: int = 11):
        self.w, self.h = w, h
        rnd = random.Random(seed)
        self.stars = []
        for count, speed, size, bright in self.LAYERS:
            for _ in range(count):
                tint = rnd.choice([(1, 1, 1), (0.7, 0.9, 1), (0.9, 0.75, 1)])
                col = tuple(int(bright * t) for t in tint)
                self.stars.append([rnd.uniform(0, w), rnd.uniform(0, h), speed, size, col,
                                   rnd.uniform(0, math.tau)])
        self.offset_x = 0.0

    def update(self, dt: float, speed_mult: float = 1.0, drift_x: float = 0.0) -> None:
        self.offset_x = drift_x
        for s in self.stars:
            s[1] += s[2] * speed_mult * dt
            if s[1] > self.h:
                s[1] -= self.h
                s[0] = random.uniform(0, self.w)

    def draw(self, surf: pygame.Surface, t: float) -> None:
        for x, y, speed, size, col, phase in self.stars:
            px = (x - self.offset_x * speed * 0.15) % self.w
            if size > 1:
                tw = 0.75 + 0.25 * math.sin(t * 3 + phase)
                c = tuple(int(v * tw) for v in col)
                pygame.draw.circle(surf, c, (int(px), int(y)), size)
                if speed > 100:  # streak for the nearest layer
                    pygame.draw.line(surf, (c[0] // 3, c[1] // 3, c[2] // 3),
                                     (int(px), int(y)), (int(px), int(y - speed * 0.08)))
            else:
                surf.set_at((int(px), int(y)), col)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "colour", "drag")

    def __init__(self, x, y, vx, vy, life, size, colour, drag=2.5):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.colour, self.drag = size, colour, drag


class ParticleSystem:
    MAX = 900

    def __init__(self):
        self.particles: list[Particle] = []

    def burst(self, x, y, colour, count=24, speed=260.0, life=0.7, size=4.0) -> None:
        for _ in range(count):
            a = random.uniform(0, math.tau)
            v = random.uniform(0.25, 1.0) * speed
            self.particles.append(Particle(x, y, math.cos(a) * v, math.sin(a) * v,
                                           random.uniform(0.5, 1.0) * life,
                                           random.uniform(0.5, 1.0) * size, colour))
        self._trim()

    def ring(self, x, y, colour, count=32, speed=320.0, life=0.5) -> None:
        for i in range(count):
            a = math.tau * i / count
            self.particles.append(Particle(x, y, math.cos(a) * speed, math.sin(a) * speed,
                                           life, 3.0, colour, drag=1.5))
        self._trim()

    def trail(self, x, y, colour, vx=0.0, vy=160.0, size=3.0, life=0.35) -> None:
        self.particles.append(Particle(x + random.uniform(-3, 3), y, vx + random.uniform(-25, 25),
                                       vy + random.uniform(0, 60), life, size, colour, drag=1.0))
        self._trim()

    def _trim(self) -> None:
        if len(self.particles) > self.MAX:
            del self.particles[: len(self.particles) - self.MAX]

    def update(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            decay = max(0.0, 1.0 - p.drag * dt)
            p.vx *= decay
            p.vy *= decay
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

    def draw(self, surf: pygame.Surface) -> None:
        for p in self.particles:
            f = max(1, int(8 * p.life / p.max_life)) / 8.0  # quantised so glow sprites cache
            r = max(1, int(p.size * (0.4 + 0.6 * f)))
            c = tuple(int(ch * f) for ch in p.colour)
            blit_glow(surf, (int(p.x), int(p.y)), r * 3, c, 1.0)
            pygame.draw.circle(surf, tuple(min(255, ch + 60) for ch in c), (int(p.x), int(p.y)), r)

    def clear(self) -> None:
        self.particles.clear()


class FloatingText:
    def __init__(self, text, x, y, colour, life=0.9):
        self.text, self.x, self.y, self.colour = text, x, y, colour
        self.life = self.max_life = life


class ScreenShake:
    def __init__(self):
        self.strength = 0.0

    def kick(self, amount: float) -> None:
        self.strength = max(self.strength, amount)

    def update(self, dt: float) -> None:
        self.strength = max(0.0, self.strength - 40.0 * dt)

    def offset(self):
        if self.strength <= 0:
            return 0, 0
        s = self.strength
        return int(random.uniform(-s, s)), int(random.uniform(-s, s))
