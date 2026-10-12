"""The player's spaceship: movement model and procedural neon drawing."""

from __future__ import annotations

import math
from typing import Optional, Tuple

import pygame

from . import config
from .effects import blit_glow


class Ship:
    def __init__(self, x: float, y: float, bounds: pygame.Rect):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.bounds = bounds
        self.radius = config.SHIP_RADIUS
        self.invuln = 0.0
        self.shield = 0.0
        self.tilt = 0.0

    @property
    def pos(self) -> Tuple[float, float]:
        return self.x, self.y

    def update(self, dt: float, key_dir: Tuple[float, float],
               target: Optional[Tuple[float, float]]) -> None:
        """Keyboard input accelerates the ship; a webcam target pulls it.

        Keyboard input wins whenever a movement key is held, so the keyboard
        always works as a fallback even in webcam mode.
        """
        kx, ky = key_dir
        if kx or ky:
            mag = math.hypot(kx, ky)
            kx, ky = kx / mag, ky / mag
            self.vx += kx * config.SHIP_KEY_ACCEL * dt
            self.vy += ky * config.SHIP_KEY_ACCEL * dt
            speed = math.hypot(self.vx, self.vy)
            if speed > config.SHIP_KEY_MAX_SPEED:
                s = config.SHIP_KEY_MAX_SPEED / speed
                self.vx *= s
                self.vy *= s
            nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        elif target is not None:
            # first-order lag towards the target: frame-rate independent easing
            k = 1.0 - math.exp(-config.SHIP_FOLLOW_RATE * dt)
            nx = self.x + (target[0] - self.x) * k
            ny = self.y + (target[1] - self.y) * k
            if dt > 0:
                self.vx, self.vy = (nx - self.x) / dt, (ny - self.y) / dt
        else:
            decay = math.exp(-config.SHIP_KEY_DAMPING * dt)
            self.vx *= decay
            self.vy *= decay
            nx, ny = self.x + self.vx * dt, self.y + self.vy * dt

        b = self.bounds
        self.x = min(max(nx, b.left), b.right)
        self.y = min(max(ny, b.top), b.bottom)
        if self.x in (b.left, b.right):
            self.vx = 0.0
        if self.y in (b.top, b.bottom):
            self.vy = 0.0
        target_tilt = max(-1.0, min(1.0, self.vx / 600.0))
        self.tilt += (target_tilt - self.tilt) * min(1.0, dt * 10)
        self.invuln = max(0.0, self.invuln - dt)
        self.shield = max(0.0, self.shield - dt)

    @property
    def vulnerable(self) -> bool:
        return self.invuln <= 0 and self.shield <= 0

    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface, t: float) -> None:
        if self.invuln > 0 and int(t * 16) % 2 == 0:
            return  # blink while invulnerable
        x, y = self.x, self.y
        lean = self.tilt * 6

        flame = 18 + 8 * math.sin(t * 40) + max(0.0, -self.vy) * 0.02
        blit_glow(surf, (int(x), int(y + 22)), int(26 + flame * 0.4), (255, 60, 180), 0.9)
        pygame.draw.polygon(surf, (255, 120, 220),
                            [(x - 6, y + 14), (x + 6, y + 14), (x, y + 14 + flame)])
        pygame.draw.polygon(surf, (255, 240, 255),
                            [(x - 3, y + 14), (x + 3, y + 14), (x, y + 14 + flame * 0.5)])

        blit_glow(surf, (int(x), int(y)), 56, (0, 120, 160), 0.8)

        hull = [(x + lean * 0.3, y - 30), (x + 10, y - 6), (x + 26 - lean, y + 14),
                (x + 9, y + 10), (x, y + 16), (x - 9, y + 10), (x - 26 - lean, y + 14),
                (x - 10, y - 6)]
        pygame.draw.polygon(surf, (16, 30, 60), hull)
        pygame.draw.polygon(surf, config.CYAN, hull, 2)
        # wing accents
        pygame.draw.line(surf, config.MAGENTA, (x - 10, y - 2), (x - 22 - lean, y + 12), 2)
        pygame.draw.line(surf, config.MAGENTA, (x + 10, y - 2), (x + 22 - lean, y + 12), 2)
        # cockpit
        cockpit = [(x + lean * 0.3, y - 20), (x + 5, y - 4), (x, y + 2), (x - 5, y - 4)]
        pygame.draw.polygon(surf, (120, 220, 255), cockpit)
        pygame.draw.polygon(surf, config.WHITE, cockpit, 1)

        if self.shield > 0:
            fade = 1.0 if self.shield > 1.5 else (0.5 + 0.5 * math.sin(t * 30))
            r = 38 + 3 * math.sin(t * 6)
            blit_glow(surf, (int(x), int(y)), int(r * 1.6), (40, 90, 200), 0.7 * fade)
            col = tuple(int(c * fade) for c in config.ELECTRIC_BLUE)
            pygame.draw.circle(surf, col, (int(x), int(y)), int(r), 2)
            for i in range(6):
                a = t * 2 + i * math.tau / 6
                pygame.draw.circle(surf, config.CYAN,
                                   (int(x + math.cos(a) * r), int(y + math.sin(a) * r)), 2)
