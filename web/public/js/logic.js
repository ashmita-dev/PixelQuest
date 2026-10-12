// Pixel Quest web - game rules (port of src/config.py, player.py, entities.py, session.py).
// DOM-free so it can be unit-tested with node. Rendering lives in render.js.

export const C = {
  W: 1280, H: 720,
  CYAN: [0, 240, 255], ELECTRIC_BLUE: [40, 120, 255], VIOLET: [150, 80, 255], MAGENTA: [255, 50, 200],
  GOLD: [255, 210, 80], WHITE: [235, 240, 255], DIM: [120, 130, 170], DANGER: [255, 70, 110], OK_GREEN: [80, 255, 170],
  START_LIVES: 3, SHIP_RADIUS: 16, SHIP_KEY_ACCEL: 3600, SHIP_KEY_MAX_SPEED: 620, SHIP_KEY_DAMPING: 7,
  SHIP_FOLLOW_RATE: 12, INVULN_TIME: 2, SHIELD_TIME: 6, LEVEL_DURATION: 25, MAX_LEVEL: 12,
  CRYSTAL_POINTS: 10, CORE_POINTS: 50, SHIELD_SMASH_POINTS: 25, COMBO_STEP: 5, MAX_MULTIPLIER: 5,
  PLAY_MARGIN: 40, CONTROL_MARGIN: 0.12,
};

/** Small seedable PRNG (mulberry32) so runs can be reproduced in tests. */
export function makeRng(seed = Date.now()) {
  let a = seed >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return { next, uniform: (lo, hi) => lo + (hi - lo) * next(), int: (lo, hi) => lo + Math.floor(next() * (hi - lo + 1)) };
}

// ------------------------------------------------------------------ ship
export class Ship {
  constructor(x, y, bounds) {
    Object.assign(this, { x, y, vx: 0, vy: 0, bounds, radius: C.SHIP_RADIUS, invuln: 0, shield: 0, tilt: 0 });
  }
  /** Keyboard input accelerates; a webcam/pointer target pulls; keys win when held. */
  update(dt, keyDir, target) {
    let [kx, ky] = keyDir, nx, ny;
    if (kx || ky) {
      const mag = Math.hypot(kx, ky); kx /= mag; ky /= mag;
      this.vx += kx * C.SHIP_KEY_ACCEL * dt; this.vy += ky * C.SHIP_KEY_ACCEL * dt;
      const sp = Math.hypot(this.vx, this.vy);
      if (sp > C.SHIP_KEY_MAX_SPEED) { this.vx *= C.SHIP_KEY_MAX_SPEED / sp; this.vy *= C.SHIP_KEY_MAX_SPEED / sp; }
      nx = this.x + this.vx * dt; ny = this.y + this.vy * dt;
    } else if (target) {
      const k = 1 - Math.exp(-C.SHIP_FOLLOW_RATE * dt);  // frame-rate independent easing
      nx = this.x + (target[0] - this.x) * k; ny = this.y + (target[1] - this.y) * k;
      if (dt > 0) { this.vx = (nx - this.x) / dt; this.vy = (ny - this.y) / dt; }
    } else {
      const decay = Math.exp(-C.SHIP_KEY_DAMPING * dt);
      this.vx *= decay; this.vy *= decay;
      nx = this.x + this.vx * dt; ny = this.y + this.vy * dt;
    }
    const b = this.bounds;
    this.x = Math.min(Math.max(nx, b.left), b.right);
    this.y = Math.min(Math.max(ny, b.top), b.bottom);
    if (this.x === b.left || this.x === b.right) this.vx = 0;
    if (this.y === b.top || this.y === b.bottom) this.vy = 0;
    const tt = Math.max(-1, Math.min(1, this.vx / 600));
    this.tilt += (tt - this.tilt) * Math.min(1, dt * 10);
    this.invuln = Math.max(0, this.invuln - dt);
    this.shield = Math.max(0, this.shield - dt);
  }
}

// ------------------------------------------------------------------ entities
export class Entity {
  constructor(kind, x, y, vx = 0, vy = 120, radius = 12) {
    Object.assign(this, { kind, x, y, vx, vy, radius, alive: true, age: 0 });
  }
  update(dt) { this.age += dt; this.x += this.vx * dt; this.y += this.vy * dt; }
  offscreen(w, h) { const r = this.radius * 2; return this.y - r > h || this.x < -r * 3 || this.x > w + r * 3; }
  collides(x, y, r) { return Math.hypot(this.x - x, this.y - y) < this.radius + r; }
}
export const crystal = (x, y, vx = 0, vy = 120) => Object.assign(new Entity("crystal", x, y, vx, vy, 14), { points: C.CRYSTAL_POINTS });
export const core = (x, y, vx = 0, vy = 150) => Object.assign(new Entity("core", x, y, vx, vy, 16), { points: C.CORE_POINTS });

export class Asteroid extends Entity {
  constructor(x, y, vx = 0, vy = 150, radius = null, rng = makeRng(1)) {
    super("asteroid", x, y, vx, vy, radius ?? rng.uniform(18, 38));
    this.spin = rng.uniform(-2, 2); this.angle = rng.uniform(0, Math.PI * 2);
    const n = rng.int(8, 11);
    this.shape = [...Array(n)].map((_, i) => [(Math.PI * 2 * i) / n, rng.uniform(0.75, 1.15)]);
  }
  update(dt) { super.update(dt); this.angle += this.spin * dt; }
}

export class Drone extends Entity {
  constructor(x, y, vy = 170, amplitude = 140, freq = 1.6, phase = 0) {
    super("drone", x, y, 0, vy, 16);
    Object.assign(this, { baseX: x, amplitude, freq, phase });
  }
  update(dt) {
    this.age += dt; this.y += this.vy * dt;
    this.x = this.baseX + Math.sin(this.age * this.freq * Math.PI + this.phase) * this.amplitude;
  }
}

// ------------------------------------------------------------------ session
export class GameSession {
  constructor({ width = C.W, height = C.H, seed = undefined, spawning = true } = {}) {
    this.w = width; this.h = height;
    this.rng = makeRng(seed ?? Math.floor(Math.random() * 2 ** 31));
    const m = C.PLAY_MARGIN;
    this.bounds = { left: m, top: m + 40, right: width - m, bottom: height - m, get width() { return this.right - this.left; }, get height() { return this.bottom - this.top; } };
    this.ship = new Ship(width / 2, height * 0.78, this.bounds);
    this.entities = [];
    Object.assign(this, { spawning, scoreFloat: 0, lives: C.START_LIVES, level: 1, elapsed: 0, streak: 0,
                          bestStreak: 0, crystals: 0, over: false, tCrystal: 0.5, tHazard: 1.2, tCore: 12, tDrone: 6 });
  }
  get score() { return Math.floor(this.scoreFloat); }
  get multiplier() { return Math.min(C.MAX_MULTIPLIER, 1 + Math.floor(this.streak / C.COMBO_STEP)); }
  get speedFactor() { return 1 + 0.12 * (this.level - 1); }
  get hazardInterval() { return Math.max(0.32, 1.25 - 0.09 * (this.level - 1)); }

  spawn() {
    const r = this.rng, b = this.bounds, sf = this.speedFactor, x = r.uniform(b.left + 20, b.right - 20);
    if (this.tCrystal <= 0) { this.entities.push(crystal(x, -20, r.uniform(-20, 20), r.uniform(130, 190) * sf)); this.tCrystal = r.uniform(0.55, 1.0); }
    if (this.tHazard <= 0) {
      this.entities.push(new Asteroid(r.uniform(b.left, b.right), -50, r.uniform(-40, 40), r.uniform(140, 220) * sf, null, r));
      this.tHazard = this.hazardInterval * r.uniform(0.7, 1.3);
    }
    if (this.tCore <= 0) { this.entities.push(core(x, -20, 0, 150 * sf)); this.tCore = r.uniform(13, 20); }
    if (this.level >= 3 && this.tDrone <= 0) {
      this.entities.push(new Drone(r.uniform(b.left + 160, b.right - 160), -30, 160 * sf, r.uniform(80, 160), r.uniform(1, 2), r.uniform(0, 6.28)));
      this.tDrone = Math.max(2.5, 8 - 0.5 * this.level) * r.uniform(0.8, 1.2);
    }
  }

  /** Advance the game; returns events {kind,x,y,value,colour} for effects/sound. */
  update(dt, keyDir = [0, 0], target = null) {
    const events = [];
    if (this.over) return events;
    dt = Math.min(dt, 0.05);
    this.elapsed += dt;
    const lvl = Math.min(C.MAX_LEVEL, 1 + Math.floor(this.elapsed / C.LEVEL_DURATION));
    if (lvl > this.level) { this.level = lvl; events.push({ kind: "levelup", x: this.w / 2, y: this.h / 2, value: lvl, colour: C.CYAN }); }
    this.scoreFloat += dt * this.level;
    if (this.spawning) { this.tCrystal -= dt; this.tHazard -= dt; this.tCore -= dt; this.tDrone -= dt; this.spawn(); }
    this.ship.update(dt, keyDir, target);
    for (const e of this.entities) e.update(dt);
    events.push(...this.checkCollisions());
    this.entities = this.entities.filter((e) => e.alive && !e.offscreen(this.w, this.h));
    return events;
  }

  checkCollisions() {
    const ev = [], s = this.ship;
    for (const e of this.entities) {
      if (!e.alive || !e.collides(s.x, s.y, s.radius)) continue;
      if (e.kind === "crystal") {
        e.alive = false; this.streak++; this.crystals++; this.bestStreak = Math.max(this.bestStreak, this.streak);
        const pts = e.points * this.multiplier; this.scoreFloat += pts;
        ev.push({ kind: "collect", x: e.x, y: e.y, value: pts, colour: C.CYAN });
      } else if (e.kind === "core") {
        e.alive = false; this.scoreFloat += e.points; s.shield = C.SHIELD_TIME;
        ev.push({ kind: "core", x: e.x, y: e.y, value: e.points, colour: C.GOLD });
      } else if (s.shield > 0) {
        e.alive = false; this.scoreFloat += C.SHIELD_SMASH_POINTS;
        ev.push({ kind: "smash", x: e.x, y: e.y, value: C.SHIELD_SMASH_POINTS, colour: C.VIOLET });
      } else if (s.invuln <= 0) {
        e.alive = false; this.lives--; this.streak = 0; s.invuln = C.INVULN_TIME;
        ev.push({ kind: "hit", x: s.x, y: s.y, value: this.lives, colour: C.DANGER });
        if (this.lives <= 0) { this.over = true; ev.push({ kind: "gameover", x: s.x, y: s.y, value: this.score, colour: C.DANGER }); break; }
      }
    }
    return ev;
  }
}

/** Map a normalised tracked centre (0..1) onto the play area, ignoring the outer camera border. */
export function mapToPlayArea(point, bounds, margin = C.CONTROL_MARGIN) {
  if (!point) return null;
  const u = Math.min(1, Math.max(0, (point[0] - margin) / (1 - 2 * margin)));
  const v = Math.min(1, Math.max(0, (point[1] - margin) / (1 - 2 * margin)));
  return [bounds.left + u * bounds.width, bounds.top + v * bounds.height];
}

/** Demo bot used only by the automated browser test (?autopilot=1). */
export function autopilotTarget(session) {
  const s = session.ship;
  let best = null, bestD = Infinity;
  for (const e of session.entities) if ((e.kind === "crystal" || e.kind === "core") && e.y < s.y) {
    const d = Math.hypot(e.x - s.x, e.y - s.y); if (d < bestD) { best = e; bestD = d; }
  }
  let [tx, ty] = best ? [best.x, best.y + 60] : [session.w / 2, session.h * 0.75];
  for (const e of session.entities) if (e.kind === "asteroid" || e.kind === "drone") {
    const dx = s.x - e.x, dy = s.y - e.y, d = Math.hypot(dx, dy) || 1;
    if (d < 150) { tx += (dx / d) * 180; ty += (dy / d) * 90; }
  }
  return [tx, Math.max(session.h * 0.45, ty)];
}
