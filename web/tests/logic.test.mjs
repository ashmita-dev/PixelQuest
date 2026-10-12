// Game-rule tests for the web port (mirrors tests/test_session.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { Asteroid, C, Drone, GameSession, core, crystal, mapToPlayArea } from "../public/js/logic.js";

const session = () => new GameSession({ seed: 1, spawning: false });
const place = (s, e) => { e.x = s.ship.x; e.y = s.ship.y; e.vx = e.vy = 0; s.entities.push(e); return e; };
const kinds = (ev) => ev.map((e) => e.kind);

test("collecting a crystal scores, builds streak and is removed", () => {
  const s = session(); place(s, crystal(0, 0));
  assert.deepEqual(kinds(s.checkCollisions()), ["collect"]);
  assert.equal(s.score, C.CRYSTAL_POINTS); assert.equal(s.streak, 1);
  s.update(0); assert.equal(s.entities.length, 0);
});

test("combo multiplier grows every COMBO_STEP crystals", () => {
  const s = session();
  for (let i = 0; i < C.COMBO_STEP; i++) { place(s, crystal(0, 0)); s.checkCollisions(); }
  assert.equal(s.multiplier, 2);
  place(s, crystal(0, 0));
  assert.equal(s.checkCollisions()[0].value, C.CRYSTAL_POINTS * 2);
});

test("hit costs a life, resets streak, grants invulnerability", () => {
  const s = session(); s.streak = 7; place(s, new Asteroid(0, 0, 0, 0, 20));
  assert.deepEqual(kinds(s.checkCollisions()), ["hit"]);
  assert.equal(s.lives, C.START_LIVES - 1); assert.equal(s.streak, 0);
  place(s, new Asteroid(0, 0, 0, 0, 20));
  assert.deepEqual(s.checkCollisions(), []);
});

test("game over after the last life; session freezes", () => {
  const s = session(); let ev = [];
  for (let i = 0; i < C.START_LIVES; i++) { s.ship.invuln = 0; place(s, new Drone(0, 0)); ev = s.checkCollisions(); }
  assert.ok(s.over && kinds(ev).includes("gameover"));
  assert.deepEqual(s.update(0.1), []);
});

test("power core shield smashes hazards", () => {
  const s = session(); place(s, core(0, 0));
  assert.deepEqual(kinds(s.checkCollisions()), ["core"]);
  place(s, new Asteroid(0, 0, 0, 0, 20));
  assert.deepEqual(kinds(s.checkCollisions()), ["smash"]);
  assert.equal(s.lives, C.START_LIVES);
  assert.equal(s.score, C.CORE_POINTS + C.SHIELD_SMASH_POINTS);
});

test("level progression and spawning", () => {
  const s = new GameSession({ seed: 3 }); const ev = [];
  for (let i = 0; i < C.LEVEL_DURATION / 0.05 + 2; i++) ev.push(...s.update(0.05));
  assert.ok(s.level >= 2 && kinds(ev).includes("levelup"));
  assert.ok(s.speedFactor > 1);
  const t = new GameSession({ seed: 3 });
  for (let i = 0; i < 120; i++) t.update(1 / 60);
  assert.ok(t.entities.some((e) => e.kind === "crystal") && t.entities.some((e) => e.kind === "asteroid"));
});

test("keyboard moves and clamps; webcam target pulls; keys override target", () => {
  const s = session(), x0 = s.ship.x;
  for (let i = 0; i < 10; i++) s.update(1 / 60, [1, 0]);
  assert.ok(s.ship.x > x0);
  for (let i = 0; i < 600; i++) s.update(1 / 60, [1, -1]);
  assert.equal(s.ship.x, s.bounds.right); assert.equal(s.ship.y, s.bounds.top);
  const target = [s.bounds.left + 50, s.bounds.top + 50];
  for (let i = 0; i < 120; i++) s.update(1 / 60, [0, 0], target);
  assert.ok(Math.abs(s.ship.x - target[0]) < 2);
  for (let i = 0; i < 30; i++) s.update(1 / 60, [1, 0], target);
  assert.ok(s.ship.x > target[0] + 50);
});

test("normalised camera point maps into play area with margin", () => {
  const b = session().bounds;
  assert.deepEqual(mapToPlayArea([0, 0], b), [b.left, b.top]);
  assert.deepEqual(mapToPlayArea([1, 1], b), [b.right, b.bottom]);
  assert.equal(mapToPlayArea(null, b), null);
});
