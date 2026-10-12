"""Neon UI toolkit: glowing text, panels, buttons, HUD and the vision diagnostics view."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np
import pygame

from . import config
from .effects import blit_glow
from .vision import TrackerStatus

FONT_NAMES = "bahnschrift,segoeui,arial"


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> pygame.font.Font:
    try:
        return pygame.font.SysFont(FONT_NAMES, size, bold=bold)
    except Exception:  # pragma: no cover - extremely old/odd systems
        return pygame.font.Font(None, size)


@lru_cache(maxsize=512)
def text_surface(text: str, size: int, colour: tuple, glow: bool = True,
                 bold: bool = False) -> pygame.Surface:
    """Rendered text with an optional soft glow (cheap blur via downscaling)."""
    core = font(size, bold).render(text, True, colour)
    if not glow:
        return core
    pad = max(8, size // 2)
    w, h = core.get_width() + pad * 2, core.get_height() + pad * 2
    halo = pygame.Surface((w, h), pygame.SRCALPHA)
    halo.blit(core, (pad, pad))
    div = 6 if size < 40 else 10
    small = pygame.transform.smoothscale(halo, (max(1, w // div), max(1, h // div)))
    halo = pygame.transform.smoothscale(small, (w, h))
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(halo, (0, 0))
    out.blit(halo, (0, 0))
    out.blit(core, (pad, pad))
    return out


def reset_caches() -> None:
    """Font objects die with pygame.quit(); call this whenever pygame restarts."""
    font.cache_clear()
    text_surface.cache_clear()


def draw_text(surf, text, size, colour, pos, anchor="center", glow=True, bold=False,
              alpha: Optional[int] = None) -> pygame.Rect:
    img = text_surface(str(text), size, tuple(colour), glow, bold)
    if alpha is not None:
        img = img.copy()
        img.set_alpha(alpha)
    pad = max(8, size // 2) if glow else 0
    rect = pygame.Rect(0, 0, img.get_width() - 2 * pad, img.get_height() - 2 * pad)
    setattr(rect, anchor, (int(pos[0]), int(pos[1])))  # anchor the text, not its halo
    surf.blit(img, (rect.x - pad, rect.y - pad))
    return rect


def draw_panel(surf, rect, border=config.CYAN, alpha=170, radius=14, width=2) -> None:
    rect = pygame.Rect(rect)
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (8, 10, 30, alpha), panel.get_rect(), border_radius=radius)
    pygame.draw.rect(panel, (*border, 220), panel.get_rect(), width, border_radius=radius)
    surf.blit(panel, rect.topleft)


class Button:
    def __init__(self, label: str, center, size=(320, 62), colour=config.CYAN, action=None):
        self.label = label
        self.rect = pygame.Rect(0, 0, *size)
        self.rect.center = center
        self.colour = colour
        self.action = action
        self.hover = 0.0  # animated 0..1

    def update(self, dt: float, focused: bool) -> None:
        target = 1.0 if focused else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 12)

    def draw(self, surf, t: float, dwell: float = 0.0) -> None:
        h = self.hover
        grow = int(8 * h)
        r = self.rect.inflate(grow, grow // 2)
        if h > 0.05:
            blit_glow(surf, r.center, int(r.width * 0.55), tuple(int(c * 0.25 * h) for c in self.colour))
        panel = pygame.Surface(r.size, pygame.SRCALPHA)
        fill_alpha = int(60 + 90 * h)
        pygame.draw.rect(panel, (*[int(c * 0.25) for c in self.colour], fill_alpha),
                         panel.get_rect(), border_radius=12)
        pygame.draw.rect(panel, (*self.colour, 255), panel.get_rect(), 2, border_radius=12)
        surf.blit(panel, r.topleft)
        # animated scanning highlight
        if h > 0.05:
            sx = r.left + (t * 260) % (r.width + 60) - 30
            pygame.draw.line(surf, tuple(min(255, c + 60) for c in self.colour),
                             (max(r.left + 6, sx), r.bottom - 5), (min(r.right - 6, sx + 40), r.bottom - 5), 2)
        if dwell > 0:
            w = int((r.width - 12) * min(1.0, dwell))
            pygame.draw.rect(surf, config.MAGENTA, (r.left + 6, r.bottom - 9, w, 4), border_radius=2)
        col = config.WHITE if h > 0.5 else self.colour
        draw_text(surf, self.label, 28, col, r.center, bold=True)


# --------------------------------------------------------------------------- HUD
STATUS_COLOURS = {
    TrackerStatus.TRACKING: config.OK_GREEN,
    TrackerStatus.HOLDING: config.GOLD,
    TrackerStatus.SEARCHING: config.GOLD,
    TrackerStatus.CONNECTING: config.ELECTRIC_BLUE,
    TrackerStatus.NO_CAMERA: config.DANGER,
    TrackerStatus.ERROR: config.DANGER,
    TrackerStatus.OFF: config.DIM,
}


def draw_heart(surf, x, y, colour, filled=True):
    pts = []
    for i in range(24):
        a = math.tau * i / 24
        hx = 16 * math.sin(a) ** 3
        hy = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((x + hx * 0.7, y + hy * 0.7))
    if filled:
        blit_glow(surf, (x, y), 22, tuple(c // 3 for c in colour))
        pygame.draw.polygon(surf, colour, pts)
    pygame.draw.polygon(surf, colour, pts, 2)


def draw_hud(surf, session, control_label: str, status: str, t: float, fps: float) -> None:
    w = surf.get_width()
    bar = pygame.Surface((w, 58), pygame.SRCALPHA)
    bar.fill((6, 6, 24, 170))
    pygame.draw.line(bar, (*config.CYAN, 140), (0, 57), (w, 57), 1)
    surf.blit(bar, (0, 0))

    draw_text(surf, "SCORE", 16, config.DIM, (24, 10), "topleft", glow=False)
    draw_text(surf, f"{session.score:,}", 32, config.CYAN, (22, 24), "topleft", bold=True)

    for i in range(config.START_LIVES):
        alive = i < session.lives
        draw_heart(surf, 250 + i * 34, 30, config.MAGENTA if alive else (70, 40, 80), alive)

    draw_text(surf, f"LEVEL {session.level}", 26, config.VIOLET, (w // 2, 29), bold=True)
    if session.multiplier > 1:
        pulse = 0.7 + 0.3 * math.sin(t * 8)
        col = tuple(int(c * pulse) for c in config.GOLD)
        draw_text(surf, f"x{session.multiplier} COMBO", 20, col, (w // 2 + 150, 29), bold=True)
    if session.ship.shield > 0:
        draw_text(surf, f"SHIELD {session.ship.shield:0.1f}s", 18, config.ELECTRIC_BLUE,
                  (w // 2 - 170, 29), bold=True)

    scol = STATUS_COLOURS.get(status, config.DIM)
    draw_text(surf, control_label, 16, config.DIM, (w - 20, 10), "topright", glow=False)
    pygame.draw.circle(surf, scol, (w - 168, 38), 6)
    blit_glow(surf, (w - 168, 38), 16, tuple(c // 2 for c in scol))
    draw_text(surf, status, 20, scol, (w - 20, 38), "midright", bold=True)
    draw_text(surf, f"{fps:0.0f} FPS", 14, (80, 90, 130), (w - 20, surf.get_height() - 12),
              "midright", glow=False)


# --------------------------------------------------------------------------- diagnostics
def cv_to_surface(img: np.ndarray, size) -> pygame.Surface:
    if img.ndim == 2:
        rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    else:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_NEAREST)
    return pygame.image.frombuffer(rgb.tobytes(), size, "RGB")


def tint_mask(mask: np.ndarray, bgr) -> np.ndarray:
    out = np.zeros((*mask.shape, 3), np.uint8)
    out[mask > 0] = bgr
    return out


class DiagnosticsView:
    """2x2 grid: camera + overlay, raw HSV mask, cleaned mask, edges/frame-diff."""

    TILE = (232, 174)

    def __init__(self):
        self._frame_id = -1
        self._tiles = []
        self.second_view = "edges"  # or "motion"

    def _build_tiles(self, state) -> None:
        r = state.result
        cam = r.frame.copy()
        h, w = cam.shape[:2]
        half = config.SAMPLE_BOX // 2
        cv2.rectangle(cam, (w // 2 - half, h // 2 - half), (w // 2 + half, h // 2 + half),
                      (255, 255, 255), 1)
        det = r.detection
        if det.found:
            x, y, bw, bh = det.bbox
            cv2.rectangle(cam, (x, y), (x + bw, y + bh), (255, 240, 0), 1)
            cv2.drawMarker(cam, (int(det.x), int(det.y)), (200, 50, 255), cv2.MARKER_CROSS, 16, 2)
        if state.position is not None:
            px, py = int(state.position[0] * w), int(state.position[1] * h)
            cv2.circle(cam, (px, py), 6, (80, 255, 170), 2)
            m = state.motion
            cv2.arrowedLine(cam, (px, py), (int(px + m.vx * w * 0.25), int(py + m.vy * h * 0.25)),
                            (0, 200, 255), 2, tipLength=0.3)
        tiles = [("CAMERA + TRACK", cam),
                 ("HSV THRESHOLD", tint_mask(r.raw_mask, (255, 240, 0))),
                 ("MORPHOLOGY (OPEN+CLOSE)", tint_mask(r.mask, (120, 255, 80)))]
        if self.second_view == "motion" and r.motion_mask is not None:
            tiles.append(("FRAME DIFFERENCE", tint_mask(r.motion_mask, (255, 80, 200))))
        elif r.edges is not None:
            tiles.append(("CANNY EDGES (DEMO)", tint_mask(r.edges, (255, 200, 120))))
        else:
            tiles.append(("EXTRAS OFF", np.zeros_like(cam)))
        self._tiles = [(name, cv_to_surface(img, self.TILE)) for name, img in tiles]

    def draw(self, surf, state, settings, t: float) -> None:
        tw, th = self.TILE
        pad = 10
        pw, ph = tw * 2 + pad * 3, th * 2 + pad * 3 + 30 + 150
        x0 = surf.get_width() - pw - 12
        y0 = 66
        draw_panel(surf, (x0, y0, pw, ph), config.VIOLET, alpha=215)
        draw_text(surf, "VISION DIAGNOSTICS", 18, config.VIOLET, (x0 + pad, y0 + 8), "topleft", bold=True)
        if state.result is None:
            draw_text(surf, state.message or "No frames yet", 20, config.DIM,
                      (x0 + pw // 2, y0 + ph // 2), glow=False)
            self._frame_id = -1
            return
        if state.frame_id != self._frame_id:
            self._build_tiles(state)
            self._frame_id = state.frame_id
        for i, (name, img) in enumerate(self._tiles):
            tx = x0 + pad + (i % 2) * (tw + pad)
            ty = y0 + 34 + (i // 2) * (th + pad)
            surf.blit(img, (tx, ty))
            pygame.draw.rect(surf, (60, 60, 110), (tx, ty, tw, th), 1)
            label_bg = pygame.Surface((tw, 18), pygame.SRCALPHA)
            label_bg.fill((0, 0, 0, 150))
            surf.blit(label_bg, (tx, ty))
            draw_text(surf, name, 13, config.WHITE, (tx + 5, ty + 1), "topleft", glow=False)

        det = state.result.detection
        m = state.motion
        pos = state.position
        lines = [
            (f"Status: {state.status}", STATUS_COLOURS.get(state.status, config.WHITE)),
            (f"Range {settings.hsv_range.describe()}", config.CYAN),
            (f"Blobs {det.contour_count} (rejected<{int(settings.min_area)}px: {det.rejected_small})"
             f"   area {det.area:0.0f}px", config.WHITE),
            ("Centre  --" if pos is None else
             f"Centre ({pos[0]:0.3f}, {pos[1]:0.3f})  d=({m.dx:+0.3f}, {m.dy:+0.3f})/frame", config.WHITE),
            (f"Velocity ({m.vx:+0.2f}, {m.vy:+0.2f})/s  speed {m.speed:0.2f}  {m.direction}", config.GOLD),
            (f"Frame-diff motion {state.result.motion_energy * 100:0.1f}%   cam {state.fps:0.0f} fps"
             f"   proc {state.process_ms:0.1f} ms", config.WHITE),
            ("K sample colour in box   H next preset   V edges/diff   TAB hide", config.DIM),
        ]
        ly = y0 + 34 + 2 * (th + pad) + 4
        for text, col in lines:
            draw_text(surf, text, 15, col, (x0 + pad + 2, ly), "topleft", glow=False)
            ly += 20
