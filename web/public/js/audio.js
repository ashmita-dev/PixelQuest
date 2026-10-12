// Procedural sound effects with the Web Audio API (port of src/audio.py). No audio files.
const SOUNDS = {
  collect: { f: [880, 1320], dur: 0.12, vol: 0.18, wave: "sine" },
  core: { f: [440, 660, 990, 1320], dur: 0.45, vol: 0.12, wave: "square" },
  hit: { f: [220, 60], dur: 0.45, vol: 0.35, wave: "noise" },
  smash: { f: [300, 120], dur: 0.25, vol: 0.12, wave: "square" },
  levelup: { f: [523, 659, 784, 1046], dur: 0.6, vol: 0.1, wave: "square" },
  select: { f: [660, 990], dur: 0.08, vol: 0.12, wave: "sine" },
  gameover: { f: [440, 330, 220, 110], dur: 1.0, vol: 0.12, wave: "square" },
};

export class Audio {
  constructor() { this.ctx = null; this.muted = false; }
  /** Browsers only allow audio after a user gesture, so call this from a key/click handler. */
  unlock() {
    if (this.ctx) { if (this.ctx.state === "suspended") this.ctx.resume(); return; }
    try { this.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch { this.ctx = null; }
  }
  toggleMute() { this.muted = !this.muted; return this.muted; }
  play(name) {
    const s = SOUNDS[name], ctx = this.ctx;
    if (!s || !ctx || this.muted || ctx.state !== "running") return;
    const t0 = ctx.currentTime, gain = ctx.createGain();
    gain.gain.setValueAtTime(s.vol, t0);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + s.dur);
    gain.connect(ctx.destination);
    let src;
    if (s.wave === "noise") {
      const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * s.dur), ctx.sampleRate), d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      src = ctx.createBufferSource(); src.buffer = buf;
      const lp = ctx.createBiquadFilter(); lp.type = "lowpass";
      lp.frequency.setValueAtTime(s.f[0] * 8, t0); lp.frequency.exponentialRampToValueAtTime(s.f[1] * 4, t0 + s.dur);
      src.connect(lp); lp.connect(gain);
    } else {
      src = ctx.createOscillator(); src.type = s.wave;
      src.frequency.setValueAtTime(s.f[0], t0);
      s.f.slice(1).forEach((f, i) => src.frequency.linearRampToValueAtTime(f, t0 + (s.dur * (i + 1)) / (s.f.length - 1)));
      src.connect(gain);
    }
    src.start(t0); src.stop(t0 + s.dur + 0.02);
  }
}
