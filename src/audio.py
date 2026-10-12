"""Tiny procedural sound effects generated with NumPy (no audio files needed).

Audio is optional: if no output device exists, every call becomes a no-op.
"""

from __future__ import annotations

import numpy as np
import pygame


class Audio:
    def __init__(self, enabled: bool = True):
        self.enabled = False
        self.muted = False
        self.sounds = {}
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            self.rate, _, self.channels = pygame.mixer.get_init()
            self._build()
            self.enabled = True
        except (pygame.error, ValueError, TypeError):
            self.enabled = False

    def _tone(self, freqs, dur, volume=0.3, wave="sine", decay=6.0):
        n = int(self.rate * dur)
        t = np.arange(n) / self.rate
        f = np.interp(t, np.linspace(0, dur, len(freqs)), freqs)
        phase = np.cumsum(2 * np.pi * f / self.rate)
        if wave == "square":
            sig = np.sign(np.sin(phase)) * 0.5
        elif wave == "noise":
            sig = np.random.default_rng(1).uniform(-1, 1, n)
        else:
            sig = np.sin(phase)
        env = np.exp(-decay * t) * np.minimum(1.0, t * 400)
        data = (sig * env * volume * 32767).astype(np.int16)
        if self.channels == 2:
            data = np.column_stack([data, data])
        return pygame.sndarray.make_sound(np.ascontiguousarray(data))

    def _build(self):
        self.sounds = {
            "collect": self._tone([880, 1320], 0.12, 0.22, decay=18),
            "core": self._tone([440, 660, 990, 1320], 0.45, 0.25, "square", decay=5),
            "hit": self._tone([220, 60], 0.45, 0.35, "noise", decay=7),
            "smash": self._tone([300, 120], 0.25, 0.25, "square", decay=10),
            "levelup": self._tone([523, 659, 784, 1046], 0.6, 0.22, "square", decay=3),
            "select": self._tone([660, 990], 0.08, 0.18, decay=25),
            "gameover": self._tone([440, 330, 220, 110], 1.0, 0.25, "square", decay=2.5),
        }

    def play(self, name: str) -> None:
        if self.enabled and not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted
