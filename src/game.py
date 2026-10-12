"""Pixel Quest application: state machine, input, rendering and webcam integration."""

from __future__ import annotations

import json
import math
from typing import Optional

import pygame

from . import config
from .audio import Audio
from .effects import FloatingText, ParticleSystem, ScreenShake, Starfield, blit_glow, make_background
from .player import Ship
from .session import GameSession
from .ui import Button, DiagnosticsView, draw_hud, draw_panel, draw_text
from .vision import (HSVRange, TrackerStatus, VisionSettings, VisionTracker, default_hsv_range,
                     save_hsv_range)

MENU, PLAY, PAUSE, OVER, HELP = "menu", "play", "pause", "over", "help"
DWELL_TIME = 1.4  # seconds the webcam cursor must hover a button to press it

HELP_LINES = [
    ("WEBCAM CONTROL", config.CYAN),
    ("Hold a brightly coloured object (default: GREEN) about 40-80 cm from the camera.", config.WHITE),
    ("Move it left/right/up/down - the ship follows its centre.", config.WHITE),
    ("Hover the marker over a button to press it. Press TAB for the vision diagnostics.", config.WHITE),
    ("Different marker? Hold it in the white box in diagnostics and press K, or H for presets.", config.WHITE),
    ("", config.WHITE),
    ("KEYBOARD CONTROL", config.MAGENTA),
    ("Arrow keys / WASD move  -  P or ESC pause  -  R restart  -  M menu", config.WHITE),
    ("C switch webcam/keyboard  -  N mute  -  F11 fullscreen", config.WHITE),
    ("", config.WHITE),
    ("GAMEPLAY", config.GOLD),
    ("Collect cyan crystals (+10). Every 5 in a row raises the combo multiplier.", config.WHITE),
    ("Gold power cores give +50 and a shield that smashes hazards.", config.WHITE),
    ("Avoid asteroids and magenta drones. You have 3 lives. Speed rises every 25 s.", config.WHITE),
]


def load_highscore() -> int:
    try:
        return int(json.loads(config.HIGHSCORE_FILE.read_text(encoding="utf-8"))["best"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def save_highscore(score: int) -> None:
    try:
        config.HIGHSCORE_FILE.write_text(json.dumps({"best": int(score)}), encoding="utf-8")
    except OSError:
        pass


class Autopilot:
    """Demo bot for headless smoke tests and screenshots (not used in normal play)."""

    def target(self, session: GameSession):
        s = session.ship
        best, best_d = None, 1e9
        for e in session.entities:
            if e.kind in ("crystal", "core") and e.y < s.y:
                d = math.hypot(e.x - s.x, e.y - s.y)
                if d < best_d:
                    best, best_d = e, d
        tx, ty = (best.x, best.y + 60) if best else (session.w / 2, session.h * 0.75)
        for e in session.entities:
            if e.kind in ("asteroid", "drone"):
                dx, dy = s.x - e.x, s.y - e.y
                d = math.hypot(dx, dy) or 1
                if d < 150:
                    tx += dx / d * 180
                    ty += dy / d * 90
        return tx, max(session.h * 0.45, ty)


class Game:
    def __init__(self, args):
        self.args = args
        pygame.init()
        flags = pygame.SCALED | pygame.RESIZABLE
        if getattr(args, "fullscreen", False):
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H), flags)
        pygame.display.set_caption("Pixel Quest - webcam arcade")
        self.clock = pygame.time.Clock()
        self.w, self.h = config.SCREEN_W, config.SCREEN_H
        self.world = pygame.Surface((self.w, self.h))
        self.background = make_background(self.w, self.h)
        self.stars = Starfield(self.w, self.h)
        self.particles = ParticleSystem()
        self.shake = ScreenShake()
        self.audio = Audio(enabled=not getattr(args, "mute", False))
        self.texts: list[FloatingText] = []
        self.toasts: list[list] = []  # [text, colour, time_left]
        self.t = 0.0
        self.fps = 0.0
        self.flash = 0.0
        self.banner = None  # (text, time_left)
        self.fade = 1.0
        self.highscore = load_highscore()
        self.new_record = False
        self.over_delay = 0.0
        self.ready = 0.0
        self.autopilot = Autopilot() if getattr(args, "autopilot", False) else None
        self.seed = getattr(args, "seed", None)
        self._pending_sample = 0.0

        # --- vision ---------------------------------------------------------
        from .vision import make_source_factory
        rng = (HSVRange.preset(args.marker) if getattr(args, "marker", None)
               else default_hsv_range())
        self.presets = list(config.MARKER_PRESETS)
        self.vision_settings = VisionSettings(hsv_range=rng)
        camera_spec = getattr(args, "camera", None)
        if camera_spec is None:
            camera_spec = config.CAMERA_INDEX
        self.tracker = VisionTracker(self.vision_settings, make_source_factory(camera_spec))
        self.diag = DiagnosticsView()
        self.show_diag = False
        self.control = "keyboard" if getattr(args, "keyboard", False) else "webcam"
        self._last_status = None
        if self.control == "webcam":
            self.tracker.start()
        if getattr(args, "diag", False):
            self.toggle_diag()

        self.session = GameSession(self.w, self.h, seed=self.seed)
        self.menu_ship = Ship(self.w / 2, self.h * 0.5, pygame.Rect(0, 0, self.w, self.h))
        self.state = MENU
        self.focus = 0
        self.dwell = 0.0
        self.buttons = {}
        self._build_buttons()

    # ------------------------------------------------------------------ buttons
    def _build_buttons(self) -> None:
        cx = self.w // 2
        self.buttons[MENU] = [
            Button("START GAME", (cx, 400), colour=config.CYAN, action=self.start_game),
            Button(self.control_button_label(), (cx, 478), colour=config.VIOLET, action=self.toggle_control),
            Button("HOW TO PLAY", (cx, 556), colour=config.ELECTRIC_BLUE, action=lambda: self.set_state(HELP)),
            Button("QUIT", (cx, 634), colour=config.MAGENTA, action=self.quit),
        ]
        self.buttons[PAUSE] = [
            Button("RESUME", (cx, 330), action=lambda: self.set_state(PLAY)),
            Button("RESTART", (cx, 408), colour=config.VIOLET, action=self.start_game),
            Button("MAIN MENU", (cx, 486), colour=config.MAGENTA, action=lambda: self.set_state(MENU)),
        ]
        self.buttons[OVER] = [
            Button("PLAY AGAIN", (cx, 520), action=self.start_game),
            Button("MAIN MENU", (cx, 598), colour=config.MAGENTA, action=lambda: self.set_state(MENU)),
        ]
        self.buttons[HELP] = [
            Button("BACK", (cx, 650), colour=config.CYAN, action=lambda: self.set_state(MENU)),
        ]

    def control_button_label(self) -> str:
        return "CONTROL: WEBCAM" if self.control == "webcam" else "CONTROL: KEYBOARD"

    # ------------------------------------------------------------------ actions
    def set_state(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        self.focus = 0
        self.dwell = 0.0
        self.fade = 0.6
        self.audio.play("select")

    def start_game(self) -> None:
        self.session = GameSession(self.w, self.h, seed=self.seed)
        self.session.spawning = False
        self.ready = 1.6
        self.particles.clear()
        self.texts.clear()
        self.new_record = False
        self.over_delay = 0.0
        self.banner = None
        self.state = None  # force transition even from PLAY
        self.set_state(PLAY)

    def toggle_control(self) -> None:
        if self.control == "webcam":
            self.control = "keyboard"
            self.tracker.stop()
            self.toast("Keyboard control active", config.VIOLET)
        else:
            self.control = "webcam"
            self.tracker.start()
            self.toast("Starting webcam...", config.CYAN)
        self.buttons[MENU][1].label = self.control_button_label()

    def toggle_diag(self) -> None:
        self.show_diag = not self.show_diag
        self.vision_settings.extras = self.show_diag

    def cycle_preset(self) -> None:
        cur = self.vision_settings.hsv_range.name
        i = (self.presets.index(cur) + 1) % len(self.presets) if cur in self.presets else 0
        self.tracker.set_hsv_range(HSVRange.preset(self.presets[i]))
        self.toast(f"Marker preset: {self.presets[i].upper()}", config.CYAN)

    def sample_colour(self) -> None:
        if self.control != "webcam" or self.tracker.snapshot().result is None:
            self.toast("Webcam not running - cannot sample colour", config.DANGER)
            return
        self.tracker.request_sample()
        self._pending_sample = 0.3

    def quit(self) -> None:
        self.running = False

    def toast(self, text: str, colour=config.WHITE, life: float = 2.8) -> None:
        self.toasts = [t for t in self.toasts if t[0] != text][-2:]
        self.toasts.append([text, colour, life])

    # ------------------------------------------------------------------ input
    def key_dir(self):
        k = pygame.key.get_pressed()
        x = (k[pygame.K_RIGHT] or k[pygame.K_d]) - (k[pygame.K_LEFT] or k[pygame.K_a])
        y = (k[pygame.K_DOWN] or k[pygame.K_s]) - (k[pygame.K_UP] or k[pygame.K_w])
        return float(x), float(y)

    def webcam_point(self, state) -> Optional[tuple]:
        """Map the normalised tracked centre onto the play area."""
        if self.control != "webcam" or state.position is None:
            return None
        m = config.CONTROL_MARGIN
        u = min(1.0, max(0.0, (state.position[0] - m) / (1 - 2 * m)))
        v = min(1.0, max(0.0, (state.position[1] - m) / (1 - 2 * m)))
        b = self.session.bounds
        return b.left + u * b.width, b.top + v * b.height

    def handle_event(self, ev) -> None:
        if ev.type == pygame.QUIT:
            self.quit()
            return
        buttons = self.buttons.get(self.state, [])
        if ev.type == pygame.MOUSEMOTION:
            for i, b in enumerate(buttons):
                if b.rect.collidepoint(ev.pos):
                    self.focus = i
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in buttons:
                if b.rect.collidepoint(ev.pos):
                    b.action()
                    return
        if ev.type != pygame.KEYDOWN:
            return
        key = ev.key
        # global keys
        if key == pygame.K_TAB:
            self.toggle_diag()
        elif key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
        elif key == pygame.K_n:
            self.toast("Sound off" if self.audio.toggle_mute() else "Sound on")
        elif key == pygame.K_c and self.state in (MENU, PAUSE, HELP, OVER):
            self.toggle_control()
        elif key == pygame.K_h:
            self.cycle_preset()
        elif key == pygame.K_k:
            self.sample_colour()
        elif key == pygame.K_v:
            self.diag.second_view = "motion" if self.diag.second_view == "edges" else "edges"
            self.diag._frame_id = -1
        # state keys
        if self.state == PLAY:
            if key in (pygame.K_p, pygame.K_ESCAPE):
                self.set_state(PAUSE)
            elif key == pygame.K_r:
                self.start_game()
            elif key == pygame.K_m:
                self.set_state(MENU)
            return
        if self.state == PAUSE and key in (pygame.K_p, pygame.K_ESCAPE):
            self.set_state(PLAY)
            return
        if self.state == PAUSE and key == pygame.K_r:
            self.start_game()
            return
        if self.state in (PAUSE, OVER, HELP) and key == pygame.K_m:
            self.set_state(MENU)
            return
        if self.state == HELP and key == pygame.K_ESCAPE:
            self.set_state(MENU)
            return
        if self.state == OVER and key == pygame.K_r:
            self.start_game()
            return
        if self.state == MENU and key in (pygame.K_ESCAPE, pygame.K_q):
            self.quit()
            return
        if buttons:
            if key in (pygame.K_UP, pygame.K_w):
                self.focus = (self.focus - 1) % len(buttons)
                self.audio.play("select")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.focus = (self.focus + 1) % len(buttons)
                self.audio.play("select")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                buttons[self.focus].action()

    # ------------------------------------------------------------------ update
    def update(self, dt: float) -> None:
        self.t += dt
        vstate = self.tracker.snapshot()
        self._report_status(vstate)
        if getattr(self, "_pending_sample", 0) > 0:
            self._pending_sample -= dt
            if self._pending_sample <= 0 and self.tracker.last_sample is not None:
                rng = self.tracker.last_sample
                save_hsv_range(rng)
                self.toast(f"Calibrated & saved {rng.describe()}", config.OK_GREEN, 4)
        self.vstate = vstate
        cam_pt = self.webcam_point(vstate)

        speed = 1.0
        if self.state == PLAY:
            speed = self.session.speed_factor * 1.6
            self._update_play(dt, cam_pt)
        elif self.state in (MENU, HELP):
            self.menu_ship.x = self.w / 2 + math.sin(self.t * 0.8) * 340
            self.menu_ship.y = self.h * 0.5 + math.sin(self.t * 1.6) * 20
            self.menu_ship.tilt = math.cos(self.t * 0.8) * 0.8
            if int(self.t * 60) % 2 == 0:
                self.particles.trail(self.menu_ship.x, self.menu_ship.y + 26, config.MAGENTA)
        self.stars.update(dt, speed, (self.session.ship.x - self.w / 2) * 0.3 if self.state == PLAY else 0)
        self.particles.update(dt)
        self.shake.update(dt)
        self.flash = max(0.0, self.flash - dt * 2.5)
        self.fade = max(0.0, self.fade - dt * 2.5)
        for ft in self.texts:
            ft.life -= dt
            ft.y -= 50 * dt
        self.texts = [ft for ft in self.texts if ft.life > 0]
        for toast in self.toasts:
            toast[2] -= dt
        self.toasts = [t for t in self.toasts if t[2] > 0]
        if self.banner:
            self.banner = (self.banner[0], self.banner[1] - dt)
            if self.banner[1] <= 0:
                self.banner = None

        buttons = self.buttons.get(self.state, [])
        hovered = None
        if cam_pt is not None and self.state != PLAY:
            for i, b in enumerate(buttons):
                if b.rect.collidepoint(cam_pt):
                    hovered = i
        if hovered is not None:
            self.focus = hovered
            self.dwell += dt / DWELL_TIME
            if self.dwell >= 1.0:
                self.dwell = 0.0
                buttons[hovered].action()
                return
        else:
            self.dwell = 0.0
        for i, b in enumerate(self.buttons.get(self.state, [])):
            b.update(dt, i == self.focus)

    def _report_status(self, vstate) -> None:
        if vstate.status == self._last_status:
            return
        self._last_status = vstate.status
        if vstate.status in (TrackerStatus.NO_CAMERA, TrackerStatus.ERROR):
            self.toast(vstate.message + "  (keyboard still works)", config.DANGER, 5)
        elif vstate.status == TrackerStatus.TRACKING:
            self.toast("Marker detected - webcam control live", config.OK_GREEN)

    def _update_play(self, dt: float, cam_pt) -> None:
        s = self.session
        if self.ready > 0:
            self.ready -= dt
            if self.ready <= 0:
                s.spawning = True
        target = cam_pt
        if self.autopilot is not None:
            target = self.autopilot.target(s)
        events = s.update(dt, self.key_dir(), target)
        ship = s.ship
        if int(self.t * 60) % 2 == 0:
            self.particles.trail(ship.x, ship.y + 26, config.MAGENTA, vy=200)
        for ev in events:
            self._on_event(ev)
        if s.over:
            self.over_delay += dt
            if self.over_delay > 1.3:
                self.set_state(OVER)

    def _on_event(self, ev) -> None:
        if ev.kind == "collect":
            self.particles.burst(ev.x, ev.y, config.CYAN, 18, 220, 0.5, 3.5)
            self.texts.append(FloatingText(f"+{ev.value}", ev.x, ev.y - 10, config.CYAN))
            self.audio.play("collect")
        elif ev.kind == "core":
            self.particles.ring(ev.x, ev.y, config.GOLD)
            self.particles.burst(ev.x, ev.y, config.GOLD, 30, 300)
            self.texts.append(FloatingText(f"+{ev.value} SHIELD", ev.x, ev.y - 10, config.GOLD, 1.3))
            self.audio.play("core")
        elif ev.kind == "smash":
            self.particles.burst(ev.x, ev.y, config.VIOLET, 30, 320)
            self.texts.append(FloatingText(f"SMASH +{ev.value}", ev.x, ev.y, config.ELECTRIC_BLUE))
            self.shake.kick(6)
            self.audio.play("smash")
        elif ev.kind == "hit":
            self.particles.burst(ev.x, ev.y, config.DANGER, 50, 420, 0.9, 5)
            self.particles.ring(ev.x, ev.y, config.MAGENTA, 40, 400)
            self.shake.kick(16)
            self.flash = 0.6
            self.audio.play("hit")
        elif ev.kind == "levelup":
            self.banner = (f"LEVEL {ev.value}", 1.8)
            self.particles.ring(self.session.ship.x, self.session.ship.y, config.CYAN, 48, 500, 0.7)
            self.audio.play("levelup")
        elif ev.kind == "gameover":
            self.particles.burst(ev.x, ev.y, config.MAGENTA, 120, 600, 1.4, 6)
            self.particles.burst(ev.x, ev.y, config.CYAN, 60, 400, 1.2, 4)
            self.shake.kick(24)
            if ev.value > self.highscore:
                self.highscore = ev.value
                self.new_record = True
                save_highscore(ev.value)
            self.audio.play("gameover")

    # ------------------------------------------------------------------ draw
    def draw(self) -> None:
        world = self.world
        world.blit(self.background, (0, 0))
        self.stars.draw(world, self.t)
        if self.state in (PLAY, PAUSE, OVER):
            for e in self.session.entities:
                e.draw(world, self.t)
            self.particles.draw(world)
            if not self.session.over:
                self.session.ship.draw(world, self.t)
        else:
            self.particles.draw(world)
            self.menu_ship.draw(world, self.t)
        for ft in self.texts:
            a = int(255 * min(1.0, ft.life / ft.max_life * 1.5))
            draw_text(world, ft.text, 22, ft.colour, (ft.x, ft.y), bold=True, alpha=a)

        self.screen.fill((0, 0, 0))
        self.screen.blit(world, self.shake.offset())
        surf = self.screen
        if self.flash > 0:
            red = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            red.fill((255, 30, 80, int(110 * self.flash)))
            surf.blit(red, (0, 0))

        status = self.vstate.status if self.control == "webcam" else "KEYBOARD"
        if self.state in (PLAY, PAUSE):
            label = "WEBCAM CONTROL" if self.control == "webcam" else "KEYBOARD CONTROL"
            if self.autopilot:
                label = "AUTOPILOT DEMO"
            draw_hud(surf, self.session, label, status, self.t, self.fps)
            self._draw_play_overlays(surf)
        if self.state == MENU:
            self._draw_menu(surf, status)
        elif self.state == HELP:
            self._draw_help(surf)
        elif self.state == PAUSE:
            self._draw_pause(surf)
        elif self.state == OVER:
            self._draw_over(surf)

        if self.state != PLAY:
            for i, b in enumerate(self.buttons.get(self.state, [])):
                b.draw(surf, self.t, self.dwell if i == self.focus else 0.0)
        if self.show_diag:
            self.diag.draw(surf, self.vstate, self.vision_settings, self.t)
        self._draw_cursor(surf)
        self._draw_toasts(surf)
        if self.fade > 0:
            veil = pygame.Surface((self.w, self.h))
            veil.fill((4, 2, 16))
            veil.set_alpha(int(255 * self.fade))
            surf.blit(veil, (0, 0))
        pygame.display.flip()

    def _draw_cursor(self, surf) -> None:
        pt = self.webcam_point(self.vstate)
        if pt is None:
            return
        x, y = int(pt[0]), int(pt[1])
        if self.state == PLAY:
            r = 12 + 2 * math.sin(self.t * 6)
            pygame.draw.circle(surf, (60, 140, 120), (x, y), int(r), 1)
            return
        blit_glow(surf, (x, y), 30, (0, 120, 100))
        pygame.draw.circle(surf, config.OK_GREEN, (x, y), 14, 2)
        pygame.draw.circle(surf, config.WHITE, (x, y), 3)
        if self.dwell > 0:
            rect = pygame.Rect(x - 22, y - 22, 44, 44)
            pygame.draw.arc(surf, config.MAGENTA, rect, math.pi / 2,
                            math.pi / 2 + math.tau * self.dwell, 3)

    def _draw_toasts(self, surf) -> None:
        y = self.h - 40
        for text, col, life in reversed(self.toasts):
            a = int(255 * min(1.0, life * 2))
            img = draw_text(surf, text, 20, col, (self.w // 2, y), glow=False, alpha=a)
            y -= img.height + 8

    def _draw_play_overlays(self, surf) -> None:
        if self.ready > 0:
            n = math.ceil(self.ready / 0.55)
            label = "GET READY" if n > 2 else ("SET" if n == 2 else "GO!")
            scale = 1.0 + (self.ready % 0.55)
            draw_text(surf, label, int(64 * scale), config.CYAN, (self.w // 2, self.h * 0.4), bold=True)
        if self.banner:
            text, life = self.banner
            a = int(255 * min(1.0, life))
            draw_text(surf, text, 72, config.VIOLET, (self.w // 2, self.h * 0.38), bold=True, alpha=a)
            draw_text(surf, "SPEED UP", 24, config.MAGENTA, (self.w // 2, self.h * 0.38 + 56), alpha=a)
        if self.control == "webcam" and self.vstate.status in (TrackerStatus.SEARCHING,
                                                               TrackerStatus.CONNECTING):
            draw_text(surf, "SHOW YOUR MARKER TO THE CAMERA  -  or use arrow keys", 20,
                      config.GOLD, (self.w // 2, 84), alpha=int(160 + 90 * math.sin(self.t * 4)))

    def _draw_title(self, surf, y) -> None:
        pulse = 0.5 + 0.5 * math.sin(self.t * 2)
        blit_glow(surf, (self.w // 2, y), int(380 + 30 * pulse), (30, 10, 70))
        for i, (dx, col) in enumerate(((-3, config.MAGENTA), (3, config.CYAN))):
            draw_text(surf, "PIXEL QUEST", 112, col, (self.w // 2 + dx, y), bold=True, glow=False, alpha=110)
        draw_text(surf, "PIXEL QUEST", 112, config.WHITE, (self.w // 2, y), bold=True)

    def _draw_menu(self, surf, status) -> None:
        self._draw_title(surf, 150)
        draw_text(surf, "A REAL-TIME WEBCAM-CONTROLLED ARCADE GAME", 22, config.CYAN, (self.w // 2, 232))
        draw_text(surf, "Steer your ship with a coloured object  -  powered by OpenCV image processing",
                  18, config.DIM, (self.w // 2, 266), glow=False)
        draw_text(surf, f"HIGH SCORE  {self.highscore:,}", 20, config.GOLD, (self.w // 2, 326), bold=True)
        # control status card
        draw_panel(surf, (24, self.h - 120, 360, 96), config.VIOLET, alpha=150)
        draw_text(surf, "INPUT", 14, config.DIM, (40, self.h - 110), "topleft", glow=False)
        if self.control == "webcam":
            from .ui import STATUS_COLOURS
            col = STATUS_COLOURS.get(status, config.WHITE)
            draw_text(surf, f"WEBCAM: {status}", 22, col, (40, self.h - 90), "topleft", bold=True)
            draw_text(surf, self.vision_settings.hsv_range.describe(), 15, config.WHITE,
                      (40, self.h - 60), "topleft", glow=False)
        else:
            draw_text(surf, "KEYBOARD", 22, config.VIOLET, (40, self.h - 90), "topleft", bold=True)
            draw_text(surf, "Arrows / WASD to move  -  C to enable webcam", 15, config.WHITE,
                      (40, self.h - 60), "topleft", glow=False)
        draw_text(surf, "ENTER start  -  C control  -  TAB diagnostics  -  ESC quit", 15, config.DIM,
                  (self.w - 24, self.h - 24), "bottomright", glow=False)

    def _draw_help(self, surf) -> None:
        draw_text(surf, "HOW TO PLAY", 56, config.CYAN, (self.w // 2, 70), bold=True)
        draw_panel(surf, (self.w // 2 - 470, 120, 940, 480), config.CYAN, alpha=190)
        y = 150
        for text, col in HELP_LINES:
            if text:
                bold = col != config.WHITE
                draw_text(surf, text, 22 if bold else 19, col, (self.w // 2 - 440, y), "topleft",
                          glow=bold, bold=bold)
            y += 31 if text else 14

    def _draw_pause(self, surf) -> None:
        veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        veil.fill((4, 2, 16, 170))
        surf.blit(veil, (0, 0))
        draw_text(surf, "PAUSED", 80, config.CYAN, (self.w // 2, 220), bold=True)

    def _draw_over(self, surf) -> None:
        veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        veil.fill((8, 2, 20, 150))
        surf.blit(veil, (0, 0))
        draw_text(surf, "GAME OVER", 96, config.MAGENTA, (self.w // 2, 130), bold=True)
        s = self.session
        draw_panel(surf, (self.w // 2 - 260, 210, 520, 250), config.VIOLET, alpha=190)
        draw_text(surf, f"{s.score:,}", 64, config.CYAN, (self.w // 2, 262), bold=True)
        if self.new_record:
            col = config.GOLD if int(self.t * 4) % 2 else config.WHITE
            draw_text(surf, "NEW HIGH SCORE!", 24, col, (self.w // 2, 312), bold=True)
        else:
            draw_text(surf, f"BEST {self.highscore:,}", 22, config.GOLD, (self.w // 2, 312))
        stats = [("LEVEL", s.level), ("CRYSTALS", s.crystals), ("BEST STREAK", s.best_streak),
                 ("TIME", f"{int(s.elapsed)}s")]
        for i, (k, v) in enumerate(stats):
            x = self.w // 2 - 195 + i * 130
            draw_text(surf, k, 14, config.DIM, (x, 370), glow=False)
            draw_text(surf, str(v), 30, config.WHITE, (x, 405), bold=True)

    # ------------------------------------------------------------------ loop
    def run(self, max_frames: Optional[int] = None, screenshot: Optional[str] = None,
            shots: Optional[dict] = None) -> int:
        """Main loop. ``max_frames`` (with fixed dt) is used for headless smoke tests."""
        self.running = True
        self.vstate = self.tracker.snapshot()
        frame = 0
        fixed_dt = 1.0 / config.FPS if max_frames else None
        try:
            while self.running:
                ms = self.clock.tick(config.FPS if not max_frames else 0)
                dt = fixed_dt or min(ms / 1000.0, 0.1)
                self.fps = self.clock.get_fps() or (1.0 / dt if dt else 0)
                for ev in pygame.event.get():
                    self.handle_event(ev)
                self.update(dt)
                self.draw()
                frame += 1
                if shots and frame in shots:
                    pygame.image.save(self.screen, shots[frame])
                if max_frames and frame >= max_frames:
                    break
            if screenshot:
                pygame.image.save(self.screen, screenshot)
        finally:
            self.tracker.stop()
            pygame.quit()
        return frame
