// Pixel Quest web - application: state machine, input, rendering loop, webcam integration.
// Port of src/game.py.
import { C, GameSession, Ship, autopilotTarget, mapToPlayArea } from "./logic.js";
import { Button, FONT, Particles, STATUS_COLOURS, Starfield, drawEntity, drawShip, glow, hud, makeBackground, panel, rgb, text } from "./render.js";
import { Audio } from "./audio.js";
import { CameraTracker, STATUS } from "./camera.js";
import { PRESETS, describeRange, makeRange } from "./vision.js";

const MENU = "menu", PLAY = "play", PAUSE = "pause", OVER = "over", HELP = "help";
const DWELL_TIME = 1.4;
const TAU = Math.PI * 2;
const params = new URLSearchParams(location.search);

const HELP_LINES = [
  ["WEBCAM CONTROL", C.CYAN],
  ["Click ENABLE WEBCAM and allow camera access. Hold a brightly coloured object (default: GREEN).", C.WHITE],
  ["Move it left/right/up/down - the ship follows its centre. Hover it over a button to press it.", C.WHITE],
  ["Press TAB for live vision diagnostics. Different marker? Hold it in the white box and press K.", C.WHITE],
  ["", C.WHITE],
  ["KEYBOARD / MOUSE / TOUCH", C.MAGENTA],
  ["Arrow keys / WASD move  -  P or ESC pause  -  R restart  -  M menu  -  H next colour preset", C.WHITE],
  ["Or press and drag on the game with a mouse or finger.  C webcam on/off  -  N mute  -  F fullscreen", C.WHITE],
  ["", C.WHITE],
  ["GAMEPLAY", C.GOLD],
  ["Collect cyan crystals (+10). Every 5 in a row raises the combo multiplier.", C.WHITE],
  ["Gold power cores give +50 and a shield that smashes hazards.", C.WHITE],
  ["Avoid asteroids and magenta drones. You have 3 lives. Speed rises every 25 s.", C.WHITE],
];

function loadHighscore() { try { return parseInt(localStorage.getItem("pq.best") || "0", 10) || 0; } catch { return 0; } }
function saveHighscore(v) { try { localStorage.setItem("pq.best", String(v)); } catch { /* storage unavailable */ } }

class App {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.w = C.W; this.h = C.H;
    this.background = makeBackground(this.w, this.h);
    this.stars = new Starfield(this.w, this.h);
    this.particles = new Particles();
    this.audio = new Audio();
    this.cam = new CameraTracker();
    if (params.get("marker") in PRESETS) this.cam.setRange(makeRange(params.get("marker")));
    this.presets = Object.keys(PRESETS);
    Object.assign(this, { t: 0, fps: 0, flash: 0, shake: 0, fade: 1, banner: null, texts: [], toasts: [], ready: 0,
                          overDelay: 0, newRecord: false, highscore: loadHighscore(), showDiag: params.has("diag"),
                          focus: 0, dwell: 0, state: MENU, keys: new Set(), pointer: null, pointerDown: false,
                          autopilot: params.has("autopilot"), seed: params.has("seed") ? +params.get("seed") : undefined,
                          lastStatus: null, pendingSample: 0, diagFrame: -1, diagView: "edges" });
    this.cam.extras = this.showDiag;
    this.session = new GameSession({ seed: this.seed });
    this.menuShip = new Ship(this.w / 2, this.h * 0.5, { left: 0, top: 0, right: this.w, bottom: this.h });
    this.tileCanvas = document.createElement("canvas"); this.tileCanvas.width = 320; this.tileCanvas.height = 240;
    this.tileCtx = this.tileCanvas.getContext("2d");
    this.tiles = [];
    this.buildButtons();
    this.bindInput();
    if (params.has("webcam")) this.toggleWebcam();
  }

  // ---------------------------------------------------------------- buttons / actions
  buildButtons() {
    const cx = this.w / 2;
    this.buttons = {
      [MENU]: [
        new Button("START GAME", cx, 400, C.CYAN, () => this.startGame()),
        // hovering the marker must not switch the webcam off; fullscreen needs a real click/key (browser rule)
        new Button(this.webcamLabel(), cx, 478, C.VIOLET, () => this.toggleWebcam(), { dwell: false }),
        new Button("HOW TO PLAY", cx, 556, C.ELECTRIC_BLUE, () => this.setState(HELP)),
        new Button("FULLSCREEN", cx, 634, C.MAGENTA, () => this.toggleFullscreen(), { dwell: false }),
      ],
      [PAUSE]: [
        new Button("RESUME", cx, 330, C.CYAN, () => this.setState(PLAY)),
        new Button("RESTART", cx, 408, C.VIOLET, () => this.startGame()),
        new Button("MAIN MENU", cx, 486, C.MAGENTA, () => this.setState(MENU)),
      ],
      [OVER]: [
        new Button("PLAY AGAIN", cx, 520, C.CYAN, () => this.startGame()),
        new Button("MAIN MENU", cx, 598, C.MAGENTA, () => this.setState(MENU)),
      ],
      [HELP]: [new Button("BACK", cx, 650, C.CYAN, () => this.setState(MENU))],
    };
  }
  webcamLabel() { return this.cam.running ? "WEBCAM: ON" : "ENABLE WEBCAM"; }

  setState(s) {
    if (s === this.state) return;
    this.state = s; this.focus = 0; this.dwell = 0; this.fade = 0.6; this.audio.play("select");
  }
  startGame() {
    this.session = new GameSession({ seed: this.seed });
    this.session.spawning = false; this.ready = 1.6;
    this.particles.clear(); this.texts = []; this.newRecord = false; this.overDelay = 0; this.banner = null;
    this.state = null; this.setState(PLAY);
  }
  async toggleWebcam() {
    if (this.cam.running) { this.cam.stop(); this.toast("Webcam off - keyboard / pointer control", C.VIOLET); }
    else {
      this.toast("Requesting camera access...", C.CYAN);
      const ok = await this.cam.start();
      if (!ok) this.toast(`${this.cam.message}. Keyboard still works.`, C.DANGER, 6);
    }
    this.buttons[MENU][1].label = this.webcamLabel();
  }
  toggleFullscreen() {
    const el = document.documentElement;
    try { document.fullscreenElement ? document.exitFullscreen() : el.requestFullscreen(); } catch { /* not allowed */ }
  }
  toggleDiag() { this.showDiag = !this.showDiag; this.cam.extras = this.showDiag; }
  cyclePreset() {
    const cur = this.cam.range.name, i = (this.presets.indexOf(cur) + 1) % this.presets.length;
    this.cam.setRange(makeRange(this.presets[i]));
    this.toast(`Marker preset: ${this.presets[i].toUpperCase()}`, C.CYAN);
  }
  sampleColour() {
    if (!this.cam.running || !this.cam.result) { this.toast("Enable the webcam first to sample a colour", C.DANGER); return; }
    this.cam.requestSample(); this.pendingSample = 0.3;
  }
  toast(msg, colour = C.WHITE, life = 2.8) { this.toasts = this.toasts.filter((t) => t.msg !== msg).slice(-2); this.toasts.push({ msg, colour, life }); }

  // ---------------------------------------------------------------- input
  toCanvas(e) {
    const r = this.canvas.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * this.w, ((e.clientY - r.top) / r.height) * this.h];
  }
  bindInput() {
    addEventListener("keydown", (e) => {
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " ", "Tab"].includes(e.key)) e.preventDefault();
      this.audio.unlock();
      if (!e.repeat) this.onKey(e.key.length === 1 ? e.key.toLowerCase() : e.key);
      this.keys.add(e.key.length === 1 ? e.key.toLowerCase() : e.key);
    });
    addEventListener("keyup", (e) => this.keys.delete(e.key.length === 1 ? e.key.toLowerCase() : e.key));
    addEventListener("blur", () => { this.keys.clear(); if (this.state === PLAY) this.setState(PAUSE); });
    const c = this.canvas;
    c.addEventListener("pointermove", (e) => {
      this.pointer = this.toCanvas(e);
      (this.buttons[this.state] || []).forEach((b, i) => { if (b.contains(...this.pointer)) this.focus = i; });
    });
    c.addEventListener("pointerdown", (e) => {
      this.audio.unlock(); c.setPointerCapture(e.pointerId);
      this.pointer = this.toCanvas(e); this.pointerDown = true;
      for (const b of this.buttons[this.state] || []) if (b.contains(...this.pointer)) { b.action(); return; }
    });
    const up = () => { this.pointerDown = false; };
    c.addEventListener("pointerup", up); c.addEventListener("pointercancel", up);
    document.addEventListener("visibilitychange", () => { if (document.hidden && this.state === PLAY) this.setState(PAUSE); });
  }
  onKey(k) {
    if (k === "Tab") this.toggleDiag();
    else if (k === "f") this.toggleFullscreen();
    else if (k === "n") this.toast(this.audio.toggleMute() ? "Sound off" : "Sound on");
    else if (k === "c" && this.state !== PLAY) this.toggleWebcam();
    else if (k === "h") this.cyclePreset();
    else if (k === "k") this.sampleColour();
    else if (k === "v") { this.diagView = this.diagView === "edges" ? "motion" : "edges"; this.diagFrame = -1; }
    const st = this.state;
    if (st === PLAY) {
      if (k === "p" || k === "Escape") this.setState(PAUSE);
      else if (k === "r") this.startGame();
      else if (k === "m") this.setState(MENU);
      return;
    }
    if (st === PAUSE && (k === "p" || k === "Escape")) return this.setState(PLAY);
    if ((st === PAUSE || st === OVER) && k === "r") return this.startGame();
    if ((st === PAUSE || st === OVER || st === HELP) && k === "m") return this.setState(MENU);
    if (st === HELP && k === "Escape") return this.setState(MENU);
    const bs = this.buttons[st] || [];
    if (!bs.length) return;
    if (k === "ArrowUp" || k === "w") { this.focus = (this.focus - 1 + bs.length) % bs.length; this.audio.play("select"); }
    else if (k === "ArrowDown" || k === "s") { this.focus = (this.focus + 1) % bs.length; this.audio.play("select"); }
    else if (k === "Enter" || k === " ") bs[this.focus].action();
  }
  keyDir() {
    const k = this.keys, d = (a, b) => (k.has(a) || k.has(b) ? 1 : 0);
    return [d("ArrowRight", "d") - d("ArrowLeft", "a"), d("ArrowDown", "s") - d("ArrowUp", "w")];
  }
  webcamPoint() { return this.cam.running ? mapToPlayArea(this.cam.position, this.session.bounds) : null; }

  // ---------------------------------------------------------------- update
  update(dt) {
    this.t += dt;
    this.cam.poll();
    if (this.cam.status !== this.lastStatus) {
      this.lastStatus = this.cam.status;
      if (this.cam.status === STATUS.TRACKING) this.toast("Marker detected - webcam control live", C.OK_GREEN);
    }
    if (this.pendingSample > 0 && (this.pendingSample -= dt) <= 0 && this.cam.lastSample)
      this.toast(`Calibrated & saved ${describeRange(this.cam.lastSample)}`, C.OK_GREEN, 4);
    const camPt = this.webcamPoint();
    let speed = 1;
    if (this.state === PLAY) { speed = this.session.speedFactor * 1.6; this.updatePlay(dt, camPt); }
    else if (this.state === MENU || this.state === HELP) {
      const m = this.menuShip;
      m.x = this.w / 2 + Math.sin(this.t * 0.8) * 340; m.y = this.h * 0.5 + Math.sin(this.t * 1.6) * 20; m.tilt = Math.cos(this.t * 0.8) * 0.8;
      if (Math.floor(this.t * 60) % 2 === 0) this.particles.trail(m.x, m.y + 26, C.MAGENTA);
    }
    this.stars.update(dt, speed, this.state === PLAY ? (this.session.ship.x - this.w / 2) * 0.3 : 0);
    this.particles.update(dt);
    this.shake = Math.max(0, this.shake - 40 * dt); this.flash = Math.max(0, this.flash - dt * 2.5); this.fade = Math.max(0, this.fade - dt * 2.5);
    this.texts = this.texts.filter((f) => ((f.y -= 50 * dt), (f.life -= dt) > 0));
    this.toasts = this.toasts.filter((t) => (t.life -= dt) > 0);
    if (this.banner && (this.banner.life -= dt) <= 0) this.banner = null;

    const bs = this.buttons[this.state] || [];
    let hovered = -1;
    if (camPt && this.state !== PLAY) bs.forEach((b, i) => { if (b.dwell && b.contains(...camPt)) hovered = i; });
    if (hovered >= 0) {
      this.focus = hovered; this.dwell += dt / DWELL_TIME;
      if (this.dwell >= 1) { this.dwell = 0; bs[hovered].action(); return; }
    } else this.dwell = 0;
    bs.forEach((b, i) => b.update(dt, i === this.focus));
  }

  updatePlay(dt, camPt) {
    const s = this.session;
    if (this.ready > 0 && (this.ready -= dt) <= 0) s.spawning = true;
    let target = camPt;
    if (this.pointerDown && this.pointer) target = [this.pointer[0], this.pointer[1] - 40]; // keep ship visible above finger
    if (this.autopilot) target = autopilotTarget(s);
    const events = s.update(dt, this.keyDir(), target);
    if (Math.floor(this.t * 60) % 2 === 0) this.particles.trail(s.ship.x, s.ship.y + 26, C.MAGENTA, 200);
    for (const ev of events) this.onEvent(ev);
    if (s.over && (this.overDelay += dt) > 1.3) this.setState(OVER);
  }

  onEvent(ev) {
    const P = this.particles, T = (msg, col, life = 0.9) => this.texts.push({ msg, x: ev.x, y: ev.y - 10, colour: col, life, max: life });
    if (ev.kind === "collect") { P.burst(ev.x, ev.y, C.CYAN, 18, 220, 0.5, 3.5); T(`+${ev.value}`, C.CYAN); this.audio.play("collect"); }
    else if (ev.kind === "core") { P.ring(ev.x, ev.y, C.GOLD); P.burst(ev.x, ev.y, C.GOLD, 30, 300); T(`+${ev.value} SHIELD`, C.GOLD, 1.3); this.audio.play("core"); }
    else if (ev.kind === "smash") { P.burst(ev.x, ev.y, C.VIOLET, 30, 320); T(`SMASH +${ev.value}`, C.ELECTRIC_BLUE); this.shake = Math.max(this.shake, 6); this.audio.play("smash"); }
    else if (ev.kind === "hit") {
      P.burst(ev.x, ev.y, C.DANGER, 50, 420, 0.9, 5); P.ring(ev.x, ev.y, C.MAGENTA, 40, 400);
      this.shake = Math.max(this.shake, 16); this.flash = 0.6; this.audio.play("hit");
      if (navigator.vibrate) navigator.vibrate(120);
    } else if (ev.kind === "levelup") {
      this.banner = { msg: `LEVEL ${ev.value}`, life: 1.8 };
      P.ring(this.session.ship.x, this.session.ship.y, C.CYAN, 48, 500, 0.7); this.audio.play("levelup");
    } else if (ev.kind === "gameover") {
      P.burst(ev.x, ev.y, C.MAGENTA, 120, 600, 1.4, 6); P.burst(ev.x, ev.y, C.CYAN, 60, 400, 1.2, 4);
      this.shake = Math.max(this.shake, 24);
      if (ev.value > this.highscore) { this.highscore = ev.value; this.newRecord = true; saveHighscore(ev.value); }
      this.audio.play("gameover");
    }
  }

  // ---------------------------------------------------------------- draw
  draw() {
    const ctx = this.ctx, st = this.state;
    ctx.save();
    if (this.shake > 0) ctx.translate((Math.random() * 2 - 1) * this.shake, (Math.random() * 2 - 1) * this.shake);
    ctx.drawImage(this.background, 0, 0);
    this.stars.draw(ctx, this.t);
    if (st === PLAY || st === PAUSE || st === OVER) {
      for (const e of this.session.entities) drawEntity(ctx, e);
      this.particles.draw(ctx);
      if (!this.session.over) drawShip(ctx, this.session.ship, this.t);
    } else { this.particles.draw(ctx); drawShip(ctx, this.menuShip, this.t); }
    for (const f of this.texts) text(ctx, f.msg, 22, f.colour, f.x, f.y, { bold: true, alpha: Math.min(1, (f.life / f.max) * 1.5) });
    ctx.restore();
    if (this.flash > 0) { ctx.fillStyle = `rgba(255,30,80,${0.43 * this.flash})`; ctx.fillRect(0, 0, this.w, this.h); }

    const status = this.cam.running ? this.cam.status : (this.cam.status === STATUS.OFF ? "KEYBOARD" : this.cam.status);
    if (st === PLAY || st === PAUSE) {
      hud(ctx, this.session, this.autopilot ? "AUTOPILOT DEMO" : this.cam.running ? "WEBCAM CONTROL" : "KEYBOARD / POINTER", status, this.t, this.fps);
      this.drawPlayOverlays(ctx);
    }
    if (st === MENU) this.drawMenu(ctx, status);
    else if (st === HELP) this.drawHelp(ctx);
    else if (st === PAUSE) { ctx.fillStyle = "rgba(4,2,16,0.67)"; ctx.fillRect(0, 0, this.w, this.h); text(ctx, "PAUSED", 80, C.CYAN, this.w / 2, 220, { bold: true }); }
    else if (st === OVER) this.drawOver(ctx);
    if (st !== PLAY) (this.buttons[st] || []).forEach((b, i) => b.draw(ctx, this.t, i === this.focus ? this.dwell : 0));
    if (this.showDiag) this.drawDiagnostics(ctx);
    this.drawCursor(ctx);
    this.drawToasts(ctx);
    if (this.fade > 0) { ctx.fillStyle = `rgba(4,2,16,${this.fade})`; ctx.fillRect(0, 0, this.w, this.h); }
  }

  drawPlayOverlays(ctx) {
    if (this.ready > 0) {
      const n = Math.ceil(this.ready / 0.55), label = n > 2 ? "GET READY" : n === 2 ? "SET" : "GO!";
      text(ctx, label, Math.round(64 * (1 + (this.ready % 0.55))), C.CYAN, this.w / 2, this.h * 0.4, { bold: true });
    }
    if (this.banner) {
      const a = Math.min(1, this.banner.life);
      text(ctx, this.banner.msg, 72, C.VIOLET, this.w / 2, this.h * 0.38, { bold: true, alpha: a });
      text(ctx, "SPEED UP", 24, C.MAGENTA, this.w / 2, this.h * 0.38 + 56, { alpha: a });
    }
    if (this.cam.running && this.cam.status === STATUS.SEARCHING)
      text(ctx, "SHOW YOUR MARKER TO THE CAMERA  -  or use arrow keys", 20, C.GOLD, this.w / 2, 84, { alpha: (160 + 90 * Math.sin(this.t * 4)) / 255 });
  }

  drawTitle(ctx, y) {
    const pulse = 0.5 + 0.5 * Math.sin(this.t * 2);
    glow(ctx, this.w / 2, y, 380 + 30 * pulse, [30, 10, 70]);
    text(ctx, "PIXEL QUEST", 112, C.MAGENTA, this.w / 2 - 3, y, { bold: true, glowOn: false, alpha: 0.43 });
    text(ctx, "PIXEL QUEST", 112, C.CYAN, this.w / 2 + 3, y, { bold: true, glowOn: false, alpha: 0.43 });
    text(ctx, "PIXEL QUEST", 112, C.WHITE, this.w / 2, y, { bold: true });
  }

  drawMenu(ctx, status) {
    this.drawTitle(ctx, 150);
    text(ctx, "A REAL-TIME WEBCAM-CONTROLLED ARCADE GAME", 22, C.CYAN, this.w / 2, 232);
    text(ctx, "Steer your ship with a coloured object  -  image processing runs locally in your browser", 18, C.DIM, this.w / 2, 266, { glowOn: false });
    text(ctx, `HIGH SCORE  ${this.highscore.toLocaleString("en-US")}`, 20, C.GOLD, this.w / 2, 326, { bold: true });
    panel(ctx, 24, this.h - 120, 360, 96, C.VIOLET, 0.6);
    text(ctx, "INPUT", 14, C.DIM, 40, this.h - 102, { anchor: "left", glowOn: false });
    const col = STATUS_COLOURS[status] || C.WHITE;
    if (this.cam.running) {
      text(ctx, `WEBCAM: ${status}`, 22, col, 40, this.h - 78, { anchor: "left", bold: true });
      text(ctx, describeRange(this.cam.range), 15, C.WHITE, 40, this.h - 48, { anchor: "left", glowOn: false });
    } else {
      text(ctx, status === "KEYBOARD" ? "KEYBOARD / POINTER" : `WEBCAM: ${status}`, 22, status === "KEYBOARD" ? C.VIOLET : col, 40, this.h - 78, { anchor: "left", bold: true });
      text(ctx, "Arrows / WASD or drag  -  C to enable webcam", 15, C.WHITE, 40, this.h - 48, { anchor: "left", glowOn: false });
    }
    text(ctx, "ENTER start  -  C webcam  -  TAB diagnostics  -  F fullscreen", 15, C.DIM, this.w - 24, this.h - 30, { anchor: "right", glowOn: false });
  }

  drawHelp(ctx) {
    text(ctx, "HOW TO PLAY", 56, C.CYAN, this.w / 2, 80, { bold: true });
    panel(ctx, this.w / 2 - 520, 120, 1040, 480, C.CYAN, 0.75);
    let y = 160;
    for (const [s, col] of HELP_LINES) {
      if (s) { const head = col !== C.WHITE; text(ctx, s, head ? 22 : 18, col, this.w / 2 - 490, y, { anchor: "left", glowOn: head, bold: head }); }
      y += s ? 31 : 14;
    }
  }

  drawOver(ctx) {
    ctx.fillStyle = "rgba(8,2,20,0.6)"; ctx.fillRect(0, 0, this.w, this.h);
    text(ctx, "GAME OVER", 96, C.MAGENTA, this.w / 2, 130, { bold: true });
    const s = this.session;
    panel(ctx, this.w / 2 - 260, 210, 520, 250, C.VIOLET, 0.75);
    text(ctx, s.score.toLocaleString("en-US"), 64, C.CYAN, this.w / 2, 262, { bold: true });
    if (this.newRecord) text(ctx, "NEW HIGH SCORE!", 24, Math.floor(this.t * 4) % 2 ? C.GOLD : C.WHITE, this.w / 2, 312, { bold: true });
    else text(ctx, `BEST ${this.highscore.toLocaleString("en-US")}`, 22, C.GOLD, this.w / 2, 312);
    [["LEVEL", s.level], ["CRYSTALS", s.crystals], ["BEST STREAK", s.bestStreak], ["TIME", `${Math.floor(s.elapsed)}s`]].forEach(([k, v], i) => {
      const x = this.w / 2 - 195 + i * 130;
      text(ctx, k, 14, C.DIM, x, 370, { glowOn: false }); text(ctx, String(v), 30, C.WHITE, x, 405, { bold: true });
    });
  }

  drawCursor(ctx) {
    const pt = this.webcamPoint();
    if (!pt) return;
    const [x, y] = pt;
    if (this.state === PLAY) { ctx.strokeStyle = "rgb(60,140,120)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, 12 + 2 * Math.sin(this.t * 6), 0, TAU); ctx.stroke(); return; }
    glow(ctx, x, y, 30, [0, 120, 100]);
    ctx.strokeStyle = rgb(C.OK_GREEN); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 14, 0, TAU); ctx.stroke();
    ctx.fillStyle = rgb(C.WHITE); ctx.beginPath(); ctx.arc(x, y, 3, 0, TAU); ctx.fill();
    if (this.dwell > 0) { ctx.strokeStyle = rgb(C.MAGENTA); ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x, y, 22, -Math.PI / 2, -Math.PI / 2 + TAU * this.dwell); ctx.stroke(); }
  }

  drawToasts(ctx) {
    let y = this.state === PLAY ? 118 : 30;   // below the HUD in play, above the big titles elsewhere
    ctx.font = `500 20px ${FONT}`;
    for (const t of this.toasts) {
      const a = Math.min(1, t.life * 2), tw = ctx.measureText(t.msg).width;
      ctx.fillStyle = `rgba(6,6,24,${0.7 * a})`; ctx.beginPath(); ctx.roundRect(this.w / 2 - tw / 2 - 14, y - 16, tw + 28, 32, 8); ctx.fill();
      text(ctx, t.msg, 20, t.colour, this.w / 2, y, { glowOn: false, alpha: a });
      ctx.font = `500 20px ${FONT}`;
      y += 42;
    }
  }

  // ---------------------------------------------------------------- diagnostics
  buildTiles() {
    const r = this.cam.result, w = 320, h = 240, n = w * h;
    const toTile = (fill) => {
      const img = this.tileCtx.createImageData(w, h); fill(img.data);
      const c = document.createElement("canvas"); c.width = w; c.height = h; c.getContext("2d").putImageData(img, 0, 0); return c;
    };
    const maskTile = (m, col) => toTile((d) => { for (let i = 0; i < n; i++) { const on = m[i]; d[i * 4] = on ? col[0] : 0; d[i * 4 + 1] = on ? col[1] : 0; d[i * 4 + 2] = on ? col[2] : 0; d[i * 4 + 3] = 255; } });
    const cam = toTile((d) => d.set(r.frame));
    const tiles = [["CAMERA + TRACK", cam], ["HSV THRESHOLD", maskTile(r.rawMask, [0, 240, 255])], ["MORPHOLOGY (OPEN+CLOSE)", maskTile(r.mask, [80, 255, 120])]];
    if (this.diagView === "motion" && r.motionMask) tiles.push(["FRAME DIFFERENCE", maskTile(r.motionMask, [200, 80, 255])]);
    else if (r.edges) tiles.push(["SOBEL EDGES (DEMO)", maskTile(r.edges, [120, 200, 255])]);
    else tiles.push(["EXTRAS OFF", maskTile(new Uint8Array(n), [0, 0, 0])]);
    this.tiles = tiles;
  }

  drawDiagnostics(ctx) {
    const TW = 232, TH = 174, pad = 10, pw = TW * 2 + pad * 3, ph = TH * 2 + pad * 3 + 30 + 150, x0 = this.w - pw - 12, y0 = 66;
    panel(ctx, x0, y0, pw, ph, C.VIOLET, 0.84);
    text(ctx, "VISION DIAGNOSTICS", 18, C.VIOLET, x0 + pad, y0 + 18, { anchor: "left", bold: true });
    const cam = this.cam;
    if (!cam.result || !cam.result.frame) {
      text(ctx, cam.running ? "Waiting for frames..." : "Webcam off - press C or ENABLE WEBCAM", 20, C.DIM, x0 + pw / 2, y0 + ph / 2, { glowOn: false });
      return;
    }
    if (cam.frameId !== this.diagFrame) { this.buildTiles(); this.diagFrame = cam.frameId; }
    const sx = TW / 320, sy = TH / 240;
    this.tiles.forEach(([name, img], i) => {
      const tx = x0 + pad + (i % 2) * (TW + pad), ty = y0 + 34 + Math.floor(i / 2) * (TH + pad);
      ctx.imageSmoothingEnabled = false; ctx.drawImage(img, tx, ty, TW, TH); ctx.imageSmoothingEnabled = true;
      ctx.strokeStyle = "rgb(60,60,110)"; ctx.lineWidth = 1; ctx.strokeRect(tx, ty, TW, TH);
      ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.fillRect(tx, ty, TW, 18);
      text(ctx, name, 13, C.WHITE, tx + 5, ty + 10, { anchor: "left", glowOn: false });
      if (i === 0) { // overlays on the camera tile
        const d = cam.result.detection, half = 12;
        ctx.strokeStyle = "white"; ctx.strokeRect(tx + (160 - half) * sx, ty + (120 - half) * sy, 2 * half * sx, 2 * half * sy);
        if (d.found) {
          const [bx, by, bw, bh] = d.bbox;
          ctx.strokeStyle = "rgb(0,240,255)"; ctx.strokeRect(tx + bx * sx, ty + by * sy, bw * sx, bh * sy);
          ctx.strokeStyle = "rgb(255,50,200)"; ctx.lineWidth = 2; ctx.beginPath();
          ctx.moveTo(tx + d.x * sx - 8, ty + d.y * sy); ctx.lineTo(tx + d.x * sx + 8, ty + d.y * sy);
          ctx.moveTo(tx + d.x * sx, ty + d.y * sy - 8); ctx.lineTo(tx + d.x * sx, ty + d.y * sy + 8); ctx.stroke();
        }
        if (cam.position) {
          const px = tx + cam.position[0] * TW, py = ty + cam.position[1] * TH, m = cam.motionInfo;
          ctx.strokeStyle = rgb(C.OK_GREEN); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(px, py, 6, 0, TAU); ctx.stroke();
          ctx.strokeStyle = "rgb(255,200,0)"; ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + m.vx * TW * 0.25, py + m.vy * TH * 0.25); ctx.stroke();
        }
      }
    });
    const d = cam.result.detection, m = cam.motionInfo || {}, pos = cam.position;
    const lines = [
      [`Status: ${cam.status}`, STATUS_COLOURS[cam.status] || C.WHITE],
      [`Range ${describeRange(cam.range)}`, C.CYAN],
      [`Blobs ${d.blobCount} (rejected<150px: ${d.rejectedSmall})   area ${d.area}px`, C.WHITE],
      [pos ? `Centre (${pos[0].toFixed(3)}, ${pos[1].toFixed(3)})  d=(${m.dx >= 0 ? "+" : ""}${m.dx.toFixed(3)}, ${m.dy >= 0 ? "+" : ""}${m.dy.toFixed(3)})/frame` : "Centre  --", C.WHITE],
      [`Velocity (${(m.vx || 0).toFixed(2)}, ${(m.vy || 0).toFixed(2)})/s  speed ${(m.speed || 0).toFixed(2)}  ${m.direction || "--"}`, C.GOLD],
      [`Frame-diff motion ${(cam.result.motionEnergy * 100).toFixed(1)}%   cam ${Math.round(cam.fps)} fps   proc ${cam.procMs.toFixed(1)} ms`, C.WHITE],
      ["K sample colour in box   H next preset   V edges/diff   TAB hide", C.DIM],
    ];
    let ly = y0 + 34 + 2 * (TH + pad) + 14;
    for (const [s, col] of lines) { text(ctx, s, 15, col, x0 + pad + 2, ly, { anchor: "left", glowOn: false }); ly += 20; }
  }
}

// ---------------------------------------------------------------- boot
const canvas = document.getElementById("game");
const fit = () => {
  const s = Math.min(innerWidth / C.W, innerHeight / C.H);
  canvas.style.width = `${Math.floor(C.W * s)}px`; canvas.style.height = `${Math.floor(C.H * s)}px`;
};
addEventListener("resize", fit); fit();

const start = () => {
  const app = new App(canvas);
  window.__pq = app; // exposed for the automated browser test
  let last = performance.now();
  const loop = (now) => {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (dt > 0) app.fps = app.fps ? 0.95 * app.fps + 0.05 / dt : 1 / dt;
    app.update(dt); app.draw();
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
  document.getElementById("loading")?.remove();
};
// wait (briefly) for the web font so the first frames don't flash a fallback face
Promise.race([document.fonts?.ready ?? Promise.resolve(), new Promise((r) => setTimeout(r, 1500))]).then(start);
