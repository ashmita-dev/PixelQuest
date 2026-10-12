// Tests for the browser vision pipeline. Run: cd web && node --test
// Synthetic inputs only. The OpenCV cross-check uses fixtures exported from the
// desktop pipeline by web/scripts/export_fixtures.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  makeRange, rgbaToHsv, gaussianBlur5, segmentHsv, cleanMask, erode, dilate, findMarker,
  frameDifference, sobelEdges, rangeFromSample, PositionSmoother, MotionEstimator, processFrame, rgbaToGray,
} from "../public/js/vision.js";

const W = 320, H = 240;
const FIX = new URL("./fixtures/", import.meta.url);
const expected = JSON.parse(readFileSync(new URL("expected.json", FIX), "utf8"));
const b64 = (s) => new Uint8Array(Buffer.from(s, "base64"));

/** Synthetic RGBA frame: dark background with a filled disc of the given RGB colour. */
function disc(cx, cy, r, rgb, bg = [30, 30, 40]) {
  const a = new Uint8ClampedArray(W * H * 4);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const p = (y * W + x) * 4, inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r;
    const c = inside ? rgb : bg;
    a[p] = c[0]; a[p + 1] = c[1]; a[p + 2] = c[2]; a[p + 3] = 255;
  }
  return a;
}
const count = (m) => m.reduce((s, v) => s + v, 0);
const GREEN = [40, 210, 50];

test("RGB->HSV matches OpenCV conventions", () => {
  const px = (r, g, b) => Array.from(rgbaToHsv(new Uint8ClampedArray([r, g, b, 255]), 1, 1));
  assert.deepEqual(px(255, 0, 0), [0, 255, 255]);
  assert.deepEqual(px(0, 255, 0), [60, 255, 255]);
  assert.deepEqual(px(0, 0, 255), [120, 255, 255]);
  assert.deepEqual(px(128, 128, 128), [0, 0, 128]);
  assert.deepEqual(px(0, 0, 0), [0, 0, 0]);
});

test("segmentation isolates the marker disc", () => {
  const hsv = rgbaToHsv(disc(100, 80, 20, GREEN), W, H);
  const m = segmentHsv(hsv, W, H, makeRange("green"));
  assert.ok(Math.abs(count(m) - Math.PI * 400) < 0.1 * Math.PI * 400);
  assert.equal(m[80 * W + 100], 1);
  assert.equal(m[5 * W + 5], 0);
  assert.equal(count(segmentHsv(hsv, W, H, makeRange("blue"))), 0);
});

test("red range wraps around hue 0", () => {
  for (const rgb of [[220, 30, 20], [220, 20, 40]]) {
    const m = segmentHsv(rgbaToHsv(disc(160, 120, 25, rgb), W, H), W, H, makeRange("red"));
    assert.ok(count(m) > 1500, `red ${rgb}`);
  }
});

test("opening removes isolated pixels, closing fills holes", () => {
  const m = new Uint8Array(W * H);
  for (let y = 50; y < 90; y++) for (let x = 50; x < 90; x++) m[y * W + x] = 1;
  m[10 * W + 200] = 1; m[30 * W + 250] = 1;            // specks
  m[70 * W + 70] = 0; m[70 * W + 71] = 0;              // hole
  const c = cleanMask(m, W, H, 1, 2);
  assert.equal(c[10 * W + 200], 0);
  assert.equal(c[70 * W + 70], 1);
  assert.equal(c[55 * W + 55], 1);
});

test("erosion/dilation by the 5x5 ellipse match the kernel shape", () => {
  const m = new Uint8Array(W * H); m[100 * W + 100] = 1;
  const d = dilate(m, W, H);
  const shape = [];
  for (let y = -2; y <= 2; y++) shape.push([...Array(5)].map((_, i) => d[(100 + y) * W + 100 + i - 2]).join(""));
  assert.deepEqual(shape, ["00100", "11111", "11111", "11111", "00100"]); // cv2 MORPH_ELLIPSE 5x5
  assert.equal(count(erode(d, W, H)), 1);
});

test("findMarker: accurate centroid, largest blob, min-area rejection", () => {
  const m = segmentHsv(rgbaToHsv(disc(210, 150, 22, GREEN), W, H), W, H, makeRange("green"));
  for (let y = 5; y < 9; y++) for (let x = 5; x < 9; x++) m[y * W + x] = 1; // 16 px speck
  const d = findMarker(m, W, H, 100);
  assert.ok(d.found);
  assert.ok(Math.abs(d.x - 210) < 1 && Math.abs(d.y - 150) < 1);
  assert.equal(d.blobCount, 2); assert.equal(d.rejectedSmall, 1);
  assert.equal(findMarker(new Uint8Array(W * H), W, H).found, false);
});

test("Gaussian blur reduces noise", () => {
  const a = new Uint8ClampedArray(W * H * 4);
  let seed = 3; const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  for (let i = 0; i < a.length; i += 4) { const v = 60 + rnd() * 80; a[i] = a[i + 1] = a[i + 2] = v; a[i + 3] = 255; }
  const sd = (arr) => { let s = 0, s2 = 0, n = 0; for (let i = 0; i < arr.length; i += 4) { s += arr[i]; s2 += arr[i] ** 2; n++; } return Math.sqrt(s2 / n - (s / n) ** 2); };
  assert.ok(sd(gaussianBlur5(a, W, H)) < 0.6 * sd(a));
});

test("frame differencing and Sobel edges", () => {
  const g1 = rgbaToGray(disc(100, 120, 25, GREEN), W, H), g2 = rgbaToGray(disc(140, 120, 25, GREEN), W, H);
  assert.ok(frameDifference(g1, g2).energy > 0.01);
  assert.equal(frameDifference(g1, g1).energy, 0);
  const e = sobelEdges(g1, W, H);
  assert.equal(e[120 * W + 100], 0);
  assert.ok(count(e) > 100);
});

test("colour sampling calibrates to the sampled marker", () => {
  const hsv = rgbaToHsv(disc(160, 120, 30, [30, 120, 220]), W, H); // blue-ish at centre
  const r = rangeFromSample(hsv, W, H);
  const hue = hsv[(120 * W + 160) * 3];
  assert.ok(r.lower[0] < hue && hue < r.upper[0]);
  assert.ok(count(segmentHsv(hsv, W, H, r)) > 2000);
  const redHsv = rgbaToHsv(disc(160, 120, 30, [220, 20, 30]), W, H);
  const rr = rangeFromSample(redHsv, W, H);
  assert.ok(count(segmentHsv(redHsv, W, H, rr)) > 2000);
});

test("smoother holds then drops; motion estimator velocity and direction", () => {
  const s = new PositionSmoother(0.3, 2);
  s.update([0.5, 0.5]);
  assert.ok(s.update(null) && s.holding);
  s.update(null);
  assert.equal(s.update(null), null);
  const m = new MotionEstimator(1.0);
  m.update([0.2, 0.5], 0);
  let i = m.update([0.3, 0.5], 0.1);
  assert.ok(Math.abs(i.vx - 1) < 1e-9); assert.equal(i.direction, "RIGHT");
  assert.equal(m.update([0.3, 0.4], 0.2).direction, "UP");
  assert.equal(m.update(null, 0.3).direction, "--");
});

// ------------------------------------------------------------------ OpenCV cross-check
for (const fx of expected) {
  test(`matches OpenCV desktop pipeline on synthetic fixture ${fx.name}`, () => {
    const rgba = new Uint8ClampedArray(readFileSync(new URL(`${fx.name}.rgba`, FIX)));
    const range = makeRange(fx.preset);
    // 1. blur + HSV within +/-2 levels of OpenCV on >= 99% of pixels (hue compared circularly)
    const hsv = rgbaToHsv(gaussianBlur5(rgba, W, H), W, H), ref = b64(fx.hsv_blurred_b64);
    let close = 0;
    for (let i = 0; i < W * H; i++) {
      const dh = Math.abs(hsv[i * 3] - ref[i * 3]), hueD = Math.min(dh, 180 - dh);
      if (hueD <= 2 && Math.abs(hsv[i * 3 + 1] - ref[i * 3 + 1]) <= 2 && Math.abs(hsv[i * 3 + 2] - ref[i * 3 + 2]) <= 2) close++;
    }
    assert.ok(close / (W * H) >= 0.99, `HSV agreement ${(close / (W * H) * 100).toFixed(2)}%`);
    // 2. morphology must be EXACT given OpenCV's own raw mask
    const raw = b64(fx.raw_mask_b64), refClean = b64(fx.clean_mask_b64), mine = cleanMask(raw, W, H);
    let diff = 0; for (let i = 0; i < W * H; i++) diff += mine[i] !== refClean[i];
    assert.equal(diff, 0, "opening+closing differs from cv2.morphologyEx");
    // 3. end-to-end detection agrees with OpenCV (centroid within 1 px)
    const res = processFrame(rgba, W, H, { range });
    assert.equal(res.detection.found, fx.found);
    if (fx.found) {
      assert.ok(Math.hypot(res.detection.x - fx.x, res.detection.y - fx.y) < 1.0,
        `centroid (${res.detection.x.toFixed(2)},${res.detection.y.toFixed(2)}) vs OpenCV (${fx.x.toFixed(2)},${fx.y.toFixed(2)})`);
      assert.ok(Math.abs(res.detection.area - fx.area) / fx.area < 0.1, "area within 10% of cv2.contourArea");
    }
  });
}
