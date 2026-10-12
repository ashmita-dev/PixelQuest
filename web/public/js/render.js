// Pixel Quest web - drawing: background, starfield, particles, glow, ship, entities, UI.
import { C, makeRng } from "./logic.js";

export const FONT = '"Bahnschrift", "Barlow Semi Condensed", "Segoe UI", system-ui, sans-serif';
export const rgb = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const TAU = Math.PI * 2;

// ------------------------------------------------------------------ glow sprites
const glowCache = new Map();
function glowSprite(radius, colour) {
  radius = Math.max(2, Math.round(radius));
  colour = colour.map((v) => Math.max(0, Math.min(255, Math.round(v))));
  const key = `${radius}|${colour}`;
  let c = glowCache.get(key);
  if (!c) {
    c = document.createElement("canvas");
    c.width = c.height = radius * 2;
    const g = c.getContext("2d"), grad = g.createRadialGradient(radius, radius, 0, radius, radius, radius);
    grad.addColorStop(0, rgb(colour, 1)); grad.addColorStop(0.35, rgb(colour, 0.35)); grad.addColorStop(1, rgb(colour, 0));
    g.fillStyle = grad; g.fillRect(0, 0, radius * 2, radius * 2);
    if (glowCache.size > 600) glowCache.clear();
    glowCache.set(key, c);
  }
  return c;
}
/** Additive radial glow (like effects.blit_glow). */
export function glow(ctx, x, y, radius, colour, alpha = 1) {
  const s = glowSprite(radius, colour);
  ctx.save(); ctx.globalCompositeOperation = "lighter"; ctx.globalAlpha = alpha;
  ctx.drawImage(s, x - s.width / 2, y - s.height / 2); ctx.restore();
}

// ------------------------------------------------------------------ background + stars
export function makeBackground(w, h) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d"), grad = g.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgb(6,4,20)"); grad.addColorStop(1, "rgb(14,6,38)");
  g.fillStyle = grad; g.fillRect(0, 0, w, h);
  const r = makeRng(3);
  for (let i = 0; i < 6; i++) {
    const col = [[60, 16, 120], [16, 40, 120], [80, 12, 80]][r.int(0, 2)];
    const s = glowSprite(r.int(180, 360), col);
    g.globalCompositeOperation = "lighter"; g.globalAlpha = 0.35;
    g.drawImage(s, r.int(0, w) - s.width / 2, r.int(0, h) - s.height / 2);
  }
  return c;
}

export class Starfield {
  constructor(w, h) {
    this.w = w; this.h = h; this.offsetX = 0; this.stars = [];
    const r = makeRng(11);
    for (const [count, speed, size, bright] of [[90, 18, 1, 90], [60, 45, 1, 160], [28, 110, 2, 235]]) {
      for (let i = 0; i < count; i++) {
        const tint = [[1, 1, 1], [0.7, 0.9, 1], [0.9, 0.75, 1]][r.int(0, 2)];
        this.stars.push({ x: r.uniform(0, w), y: r.uniform(0, h), speed, size, col: tint.map((t) => Math.round(bright * t)), phase: r.uniform(0, TAU) });
      }
    }
  }
  update(dt, mult = 1, drift = 0) {
    this.offsetX = drift;
    for (const s of this.stars) { s.y += s.speed * mult * dt; if (s.y > this.h) { s.y -= this.h; s.x = Math.random() * this.w; } }
  }
  draw(ctx, t) {
    for (const s of this.stars) {
      const px = (((s.x - this.offsetX * s.speed * 0.15) % this.w) + this.w) % this.w;
      if (s.size > 1) {
        const tw = 0.75 + 0.25 * Math.sin(t * 3 + s.phase);
        ctx.fillStyle = rgb(s.col.map((v) => v * tw));
        ctx.beginPath(); ctx.arc(px, s.y, s.size, 0, TAU); ctx.fill();
        ctx.strokeStyle = rgb(s.col, 0.33); ctx.beginPath(); ctx.moveTo(px, s.y); ctx.lineTo(px, s.y - s.speed * 0.08); ctx.stroke();
      } else { ctx.fillStyle = rgb(s.col); ctx.fillRect(px, s.y, 1, 1); }
    }
  }
}

// ------------------------------------------------------------------ particles
export class Particles {
  constructor() { this.list = []; }
  add(x, y, vx, vy, life, size, colour, drag = 2.5) {
    this.list.push({ x, y, vx, vy, life, max: life, size, colour, drag });
    if (this.list.length > 900) this.list.splice(0, this.list.length - 900);
  }
  burst(x, y, colour, count = 24, speed = 260, life = 0.7, size = 4) {
    for (let i = 0; i < count; i++) {
      const a = Math.random() * TAU, v = (0.25 + Math.random() * 0.75) * speed;
      this.add(x, y, Math.cos(a) * v, Math.sin(a) * v, (0.5 + Math.random() * 0.5) * life, (0.5 + Math.random() * 0.5) * size, colour);
    }
  }
  ring(x, y, colour, count = 32, speed = 320, life = 0.5) {
    for (let i = 0; i < count; i++) { const a = (TAU * i) / count; this.add(x, y, Math.cos(a) * speed, Math.sin(a) * speed, life, 3, colour, 1.5); }
  }
  trail(x, y, colour, vy = 160) { this.add(x + (Math.random() * 6 - 3), y, Math.random() * 50 - 25, vy + Math.random() * 60, 0.35, 3, colour, 1); }
  update(dt) {
    this.list = this.list.filter((p) => (p.life -= dt) > 0);
    for (const p of this.list) { const d = Math.max(0, 1 - p.drag * dt); p.vx *= d; p.vy *= d; p.x += p.vx * dt; p.y += p.vy * dt; }
  }
  draw(ctx) {
    for (const p of this.list) {
      const f = p.life / p.max, r = Math.max(1, p.size * (0.4 + 0.6 * f));
      glow(ctx, p.x, p.y, r * 3, p.colour, f);
      ctx.fillStyle = rgb(p.colour.map((c) => Math.min(255, c + 60)), f);
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, TAU); ctx.fill();
    }
  }
  clear() { this.list = []; }
}

// ------------------------------------------------------------------ ship + entities
function poly(ctx, pts, fill, stroke, width = 2) {
  ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.stroke(); }
}

export function drawShip(ctx, s, t) {
  if (s.invuln > 0 && Math.floor(t * 16) % 2 === 0) return;
  const { x, y } = s, lean = s.tilt * 6;
  const flame = 18 + 8 * Math.sin(t * 40) + Math.max(0, -s.vy) * 0.02;
  glow(ctx, x, y + 22, 26 + flame * 0.4, [255, 60, 180], 0.9);
  poly(ctx, [[x - 6, y + 14], [x + 6, y + 14], [x, y + 14 + flame]], "rgb(255,120,220)");
  poly(ctx, [[x - 3, y + 14], [x + 3, y + 14], [x, y + 14 + flame * 0.5]], "rgb(255,240,255)");
  glow(ctx, x, y, 56, [0, 120, 160], 0.8);
  const hull = [[x + lean * 0.3, y - 30], [x + 10, y - 6], [x + 26 - lean, y + 14], [x + 9, y + 10], [x, y + 16],
                [x - 9, y + 10], [x - 26 - lean, y + 14], [x - 10, y - 6]];
  poly(ctx, hull, "rgb(16,30,60)", rgb(C.CYAN));
  ctx.strokeStyle = rgb(C.MAGENTA); ctx.lineWidth = 2; ctx.beginPath();
  ctx.moveTo(x - 10, y - 2); ctx.lineTo(x - 22 - lean, y + 12); ctx.moveTo(x + 10, y - 2); ctx.lineTo(x + 22 - lean, y + 12); ctx.stroke();
  poly(ctx, [[x + lean * 0.3, y - 20], [x + 5, y - 4], [x, y + 2], [x - 5, y - 4]], "rgb(120,220,255)", rgb(C.WHITE), 1);
  if (s.shield > 0) {
    const fade = s.shield > 1.5 ? 1 : 0.5 + 0.5 * Math.sin(t * 30), r = 38 + 3 * Math.sin(t * 6);
    glow(ctx, x, y, r * 1.6, [40, 90, 200], 0.7 * fade);
    ctx.strokeStyle = rgb(C.ELECTRIC_BLUE, fade); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.stroke();
    ctx.fillStyle = rgb(C.CYAN);
    for (let i = 0; i < 6; i++) { const a = t * 2 + (i * TAU) / 6; ctx.beginPath(); ctx.arc(x + Math.cos(a) * r, y + Math.sin(a) * r, 2, 0, TAU); ctx.fill(); }
  }
}

export function drawEntity(ctx, e) {
  const { x, age } = e;
  if (e.kind === "crystal") {
    const y = e.y + Math.sin(age * 4) * 3, s = 12 + Math.sin(age * 6) * 1.5, w = Math.abs(Math.cos(age * 2.2)) * 0.6 + 0.4;
    glow(ctx, x, y, 34, [0, 140, 170], 0.9);
    poly(ctx, [[x, y - s * 1.3], [x + s * w, y], [x, y + s * 1.3], [x - s * w, y]], "rgb(20,90,120)", rgb(C.CYAN));
    ctx.strokeStyle = rgb(C.WHITE); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, y - s * 1.3); ctx.lineTo(x, y + s * 1.3); ctx.stroke();
  } else if (e.kind === "core") {
    const pulse = 0.5 + 0.5 * Math.sin(age * 8);
    glow(ctx, x, e.y, 44 + 8 * pulse, [150, 110, 20], 1);
    const pts = [...Array(10)].map((_, i) => { const r = i % 2 ? 8 : 17, a = age * 1.5 + (i * Math.PI) / 5; return [x + Math.cos(a) * r, e.y + Math.sin(a) * r]; });
    poly(ctx, pts, "rgb(120,80,10)", rgb(C.GOLD));
    ctx.fillStyle = rgb(C.WHITE); ctx.beginPath(); ctx.arc(x, e.y, 4, 0, TAU); ctx.fill();
  } else if (e.kind === "asteroid") {
    glow(ctx, x, e.y, e.radius * 2, [70, 20, 110], 0.8);
    poly(ctx, e.shape.map(([a, k]) => [x + Math.cos(a + e.angle) * e.radius * k, e.y + Math.sin(a + e.angle) * e.radius * k]), "rgb(30,14,50)", rgb(C.VIOLET));
    ctx.strokeStyle = "rgb(90,40,150)"; ctx.lineWidth = 1; ctx.beginPath();
    ctx.arc(x + Math.cos(e.angle) * e.radius * 0.3, e.y + Math.sin(e.angle) * e.radius * 0.3, Math.max(2, e.radius * 0.22), 0, TAU); ctx.stroke();
  } else if (e.kind === "drone") {
    glow(ctx, x, e.y, 40, [150, 20, 110], 1);
    ctx.strokeStyle = rgb(C.MAGENTA); ctx.lineWidth = 2; ctx.beginPath();
    for (let i = 0; i < 3; i++) { const a = age * 5 + (i * TAU) / 3; ctx.moveTo(x, e.y); ctx.lineTo(x + Math.cos(a) * 20, e.y + Math.sin(a) * 20); }
    ctx.stroke();
    ctx.fillStyle = "rgb(50,10,40)"; ctx.beginPath(); ctx.arc(x, e.y, 11, 0, TAU); ctx.fill(); ctx.stroke();
    const eye = 0.5 + 0.5 * Math.sin(age * 12);
    ctx.fillStyle = `rgb(255,${Math.round(80 + 150 * eye)},200)`; ctx.beginPath(); ctx.arc(x, e.y, 4, 0, TAU); ctx.fill();
  }
}

// ------------------------------------------------------------------ text + UI
/** Glowing text. anchor: "center" | "left" | "right"; baseline middle. */
export function text(ctx, str, size, colour, x, y, { anchor = "center", glowOn = true, bold = false, alpha = 1 } = {}) {
  ctx.save();
  ctx.font = `${bold ? 700 : 500} ${size}px ${FONT}`;
  ctx.textAlign = anchor; ctx.textBaseline = "middle"; ctx.globalAlpha = alpha;
  if (glowOn) { ctx.shadowColor = rgb(colour, 0.9); ctx.shadowBlur = Math.max(8, size * 0.45); }
  ctx.fillStyle = rgb(colour); ctx.fillText(str, x, y);
  if (glowOn) { ctx.shadowBlur = 0; ctx.fillText(str, x, y); }
  ctx.restore();
}

export function panel(ctx, x, y, w, h, border = C.CYAN, alpha = 0.67, radius = 14) {
  ctx.save(); ctx.beginPath(); ctx.roundRect(x, y, w, h, radius);
  ctx.fillStyle = `rgba(8,10,30,${alpha})`; ctx.fill();
  ctx.strokeStyle = rgb(border, 0.86); ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
}

export class Button {
  constructor(label, cx, cy, colour = C.CYAN, action = () => {}, { w = 320, h = 62, dwell = true } = {}) {
    // dwell=false: cannot be pressed by hovering the webcam marker (only key/click)
    Object.assign(this, { label, colour, action, dwell, hover: 0, rect: { x: cx - w / 2, y: cy - h / 2, w, h } });
  }
  contains(px, py) { const r = this.rect; return px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h; }
  update(dt, focused) { this.hover += ((focused ? 1 : 0) - this.hover) * Math.min(1, dt * 12); }
  draw(ctx, t, dwell = 0) {
    const h = this.hover, g = 8 * h, r = { x: this.rect.x - g / 2, y: this.rect.y - g / 4, w: this.rect.w + g, h: this.rect.h + g / 2 };
    if (h > 0.05) glow(ctx, r.x + r.w / 2, r.y + r.h / 2, r.w * 0.55, this.colour.map((c) => c * 0.25), h);
    ctx.save(); ctx.beginPath(); ctx.roundRect(r.x, r.y, r.w, r.h, 12);
    ctx.fillStyle = rgb(this.colour.map((c) => c * 0.25), (60 + 90 * h) / 255); ctx.fill();
    ctx.strokeStyle = rgb(this.colour); ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
    if (h > 0.05) {
      const sx = r.x + ((t * 260) % (r.w + 60)) - 30;
      ctx.strokeStyle = rgb(this.colour.map((c) => Math.min(255, c + 60))); ctx.lineWidth = 2; ctx.beginPath();
      ctx.moveTo(Math.max(r.x + 6, sx), r.y + r.h - 5); ctx.lineTo(Math.min(r.x + r.w - 6, sx + 40), r.y + r.h - 5); ctx.stroke();
    }
    if (dwell > 0) { ctx.fillStyle = rgb(C.MAGENTA); ctx.fillRect(r.x + 6, r.y + r.h - 9, (r.w - 12) * Math.min(1, dwell), 4); }
    text(ctx, this.label, 28, h > 0.5 ? C.WHITE : this.colour, r.x + r.w / 2, r.y + r.h / 2 + 1, { bold: true });
  }
}

export function heart(ctx, x, y, colour, filled) {
  ctx.beginPath();
  for (let i = 0; i <= 24; i++) {
    const a = (TAU * i) / 24, hx = 16 * Math.sin(a) ** 3, hy = -(13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a));
    i ? ctx.lineTo(x + hx * 0.7, y + hy * 0.7) : ctx.moveTo(x + hx * 0.7, y + hy * 0.7);
  }
  if (filled) { glow(ctx, x, y, 22, colour.map((c) => c / 3)); ctx.fillStyle = rgb(colour); ctx.fill(); }
  ctx.strokeStyle = rgb(colour); ctx.lineWidth = 2; ctx.stroke();
}

export const STATUS_COLOURS = {
  TRACKING: C.OK_GREEN, HOLDING: C.GOLD, SEARCHING: C.GOLD, CONNECTING: C.ELECTRIC_BLUE, "ASKING PERMISSION": C.ELECTRIC_BLUE,
  "NO CAMERA": C.DANGER, DENIED: C.DANGER, ERROR: C.DANGER, KEYBOARD: C.VIOLET, OFF: C.DIM,
};

export function hud(ctx, session, label, status, t, fps) {
  const w = C.W;
  ctx.fillStyle = "rgba(6,6,24,0.67)"; ctx.fillRect(0, 0, w, 58);
  ctx.fillStyle = rgb(C.CYAN, 0.55); ctx.fillRect(0, 57, w, 1);
  text(ctx, "SCORE", 16, C.DIM, 24, 18, { anchor: "left", glowOn: false });
  text(ctx, session.score.toLocaleString("en-US"), 32, C.CYAN, 22, 40, { anchor: "left", bold: true });
  for (let i = 0; i < C.START_LIVES; i++) heart(ctx, 250 + i * 34, 30, i < session.lives ? C.MAGENTA : [70, 40, 80], i < session.lives);
  text(ctx, `LEVEL ${session.level}`, 26, C.VIOLET, w / 2, 29, { bold: true });
  if (session.multiplier > 1) text(ctx, `x${session.multiplier} COMBO`, 20, C.GOLD.map((c) => c * (0.7 + 0.3 * Math.sin(t * 8))), w / 2 + 150, 29, { bold: true });
  if (session.ship.shield > 0) text(ctx, `SHIELD ${session.ship.shield.toFixed(1)}s`, 18, C.ELECTRIC_BLUE, w / 2 - 170, 29, { bold: true });
  const sc = STATUS_COLOURS[status] || C.DIM;
  text(ctx, label, 16, C.DIM, w - 20, 16, { anchor: "right", glowOn: false });
  ctx.fillStyle = rgb(sc); ctx.beginPath(); ctx.arc(w - 210, 39, 6, 0, TAU); ctx.fill();
  glow(ctx, w - 210, 39, 16, sc.map((c) => c / 2));
  text(ctx, status, 20, sc, w - 20, 39, { anchor: "right", bold: true });
  if (fps > 0) text(ctx, `${Math.round(fps)} FPS`, 14, [80, 90, 130], w - 20, C.H - 12, { anchor: "right", glowOn: false });
}
