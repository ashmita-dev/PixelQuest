// Pixel Quest web - client-side image & video processing (no libraries).
//
// Port of src/vision.py. Pipeline per webcam frame:
//   mirrored 320x240 RGBA (canvas drawImage) -> 5x5 Gaussian blur -> RGB->HSV
//   -> HSV threshold (hue may wrap) -> opening + closing (5x5 ellipse)
//   -> 8-connected components -> largest blob >= MIN_AREA -> centroid (moments)
//   -> EMA smoothing -> frame-to-frame velocity (motion estimate)
// Diagnostics also compute grey-level frame differencing and a Sobel edge map.
// This is tracking / motion estimation only - no video compression or codec.
//
// Everything here is DOM-free so it runs under `node --test`.

export const PRESETS = {
  green: [[40, 80, 60], [85, 255, 255]],
  blue: [[95, 120, 60], [130, 255, 255]],
  red: [[170, 120, 70], [8, 255, 255]],
  yellow: [[20, 110, 110], [34, 255, 255]],
  orange: [[8, 150, 120], [20, 255, 255]],
  pink: [[140, 80, 90], [169, 255, 255]],
};

export const DEFAULTS = {
  width: 320, height: 240,      // processing resolution
  blur: true,                    // 5x5 Gaussian
  openIter: 1, closeIter: 2,     // morphology iterations (5x5 ellipse)
  minArea: 150,                  // px; smaller blobs rejected as noise
  smoothingAlpha: 0.35,
  lostHoldFrames: 8,
  motionSmoothing: 0.5,
  stillThreshold: 0.08,
  diffThreshold: 25,
  sobelThreshold: 120,
  sampleBox: 24,
};

export function makeRange(name) {
  const [lower, upper] = PRESETS[name];
  return { name, lower: [...lower], upper: [...upper] };
}

export const wrapsHue = (r) => r.lower[0] > r.upper[0];

export function describeRange(r) {
  return `${r.name}: H${r.lower[0]}-${r.upper[0]} S${r.lower[1]}-${r.upper[1]} V${r.lower[2]}-${r.upper[2]}`;
}

// ---------------------------------------------------------------- enhancement
const reflect101 = (i, n) => (i < 0 ? -i : i >= n ? 2 * n - 2 - i : i);

/** Separable 5x5 Gaussian ([1,4,6,4,1]/16, as cv2.GaussianBlur ksize 5). RGBA in, RGBA out.
 *  Integer arithmetic with rounding ((sum + 128) >> 8); borders use BORDER_REFLECT_101. */
export function gaussianBlur5(src, w, h) {
  const k = [1, 4, 6, 4, 1];
  const xi = new Int32Array(5 * w), yi = new Int32Array(5 * h);   // reflected neighbour indices
  for (let o = 0; o < 5; o++) {
    for (let x = 0; x < w; x++) xi[o * w + x] = reflect101(x + o - 2, w);
    for (let y = 0; y < h; y++) yi[o * h + y] = reflect101(y + o - 2, h);
  }
  const tmp = new Uint16Array(w * h * 3), out = new Uint8ClampedArray(src.length);
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      let r = 0, g = 0, b = 0;
      for (let o = 0; o < 5; o++) {
        const p = (row + xi[o * w + x]) << 2, wt = k[o];
        r += src[p] * wt; g += src[p + 1] * wt; b += src[p + 2] * wt;
      }
      const q = (row + x) * 3;
      tmp[q] = r; tmp[q + 1] = g; tmp[q + 2] = b;
    }
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let r = 0, g = 0, b = 0;
      for (let o = 0; o < 5; o++) {
        const q = (yi[o * h + y] * w + x) * 3, wt = k[o];
        r += tmp[q] * wt; g += tmp[q + 1] * wt; b += tmp[q + 2] * wt;
      }
      const p = (y * w + x) << 2;
      out[p] = (r + 128) >> 8; out[p + 1] = (g + 128) >> 8; out[p + 2] = (b + 128) >> 8; out[p + 3] = 255;
    }
  }
  return out;
}

// ---------------------------------------------------------------- colour
/** RGBA -> HSV in OpenCV 8-bit units (H 0-179, S/V 0-255). Returns Uint8Array(3*w*h). */
export function rgbaToHsv(src, w, h) {
  const n = w * h, hsv = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = src[i * 4], g = src[i * 4 + 1], b = src[i * 4 + 2];
    const v = Math.max(r, g, b), mn = Math.min(r, g, b), d = v - mn;
    let hue = 0;
    if (d > 0) {
      if (v === r) hue = (60 * (g - b)) / d;
      else if (v === g) hue = 120 + (60 * (b - r)) / d;
      else hue = 240 + (60 * (r - g)) / d;
      if (hue < 0) hue += 360;
    }
    let H = Math.round(hue / 2);
    if (H >= 180) H -= 180;
    hsv[i * 3] = H;
    hsv[i * 3 + 1] = v === 0 ? 0 : Math.round((255 * d) / v);
    hsv[i * 3 + 2] = v;
  }
  return hsv;
}

/** Grey level as cv2.COLOR_RGB2GRAY: 0.299R + 0.587G + 0.114B. */
export function rgbaToGray(src, w, h) {
  const n = w * h, g = new Uint8Array(n);
  for (let i = 0; i < n; i++) g[i] = Math.round(0.299 * src[i * 4] + 0.587 * src[i * 4 + 1] + 0.114 * src[i * 4 + 2]);
  return g;
}

// ---------------------------------------------------------------- segmentation
/** Binary mask (0/1) of pixels inside the HSV range; wrapped hue ORs two intervals. */
export function segmentHsv(hsv, w, h, range) {
  const [h0, s0, v0] = range.lower, [h1, s1, v1] = range.upper, wrap = h0 > h1;
  const n = w * h, mask = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const H = hsv[i * 3], S = hsv[i * 3 + 1], V = hsv[i * 3 + 2];
    const hueOk = wrap ? H >= h0 || H <= h1 : H >= h0 && H <= h1;
    mask[i] = hueOk && S >= s0 && S <= s1 && V >= v0 && V <= v1 ? 1 : 0;
  }
  return mask;
}

// ---------------------------------------------------------------- morphology
// 1-D running-window erosion/dilation (O(1) per pixel). Outside the image counts as foreground
// for erosion and background for dilation (OpenCV's default border values).
function passH(src, w, h, radius, erode) {
  const out = new Uint8Array(src.length);
  for (let y = 0; y < h; y++) {
    const base = y * w;
    let count = 0;                                   // foreground pixels in window [x-r, x+r]
    for (let j = 0; j < radius && j < w; j++) count += src[base + j];
    for (let x = 0; x < w; x++) {
      const add = x + radius, drop = x - radius - 1;
      if (add < w) count += src[base + add];
      if (drop >= 0) count -= src[base + drop];
      const inside = (add < w ? add : w - 1) - (x > radius ? x - radius : 0) + 1;
      out[base + x] = erode ? (count === inside ? 1 : 0) : (count > 0 ? 1 : 0);
    }
  }
  return out;
}

// Vertical pass swept row by row with one running count per column (cache friendly).
function passV(src, w, h, radius, erode) {
  const out = new Uint8Array(src.length), count = new Int32Array(w);
  for (let j = 0; j < radius && j < h; j++) for (let x = 0, b = j * w; x < w; x++) count[x] += src[b + x];
  for (let y = 0; y < h; y++) {
    const add = y + radius, drop = y - radius - 1;
    if (add < h) for (let x = 0, b = add * w; x < w; x++) count[x] += src[b + x];
    if (drop >= 0) for (let x = 0, b = drop * w; x < w; x++) count[x] -= src[b + x];
    const inside = (add < h ? add : h - 1) - (y > radius ? y - radius : 0) + 1, base = y * w;
    if (erode) for (let x = 0; x < w; x++) out[base + x] = count[x] === inside ? 1 : 0;
    else for (let x = 0; x < w; x++) out[base + x] = count[x] > 0 ? 1 : 0;
  }
  return out;
}

// cv2.getStructuringElement(MORPH_ELLIPSE, (5,5)) = (5 wide x 3 tall rect) U (1 wide x 5 tall line).
// Erosion by a union of elements = AND of erosions; dilation = OR of dilations.
function morph(mask, w, h, erode) {
  const rect = passV(passH(mask, w, h, 2, erode), w, h, 1, erode);
  const line = passV(mask, w, h, 2, erode);
  const out = new Uint8Array(mask.length);
  for (let i = 0; i < out.length; i++) out[i] = erode ? rect[i] & line[i] : rect[i] | line[i];
  return out;
}
export const erode = (m, w, h) => morph(m, w, h, true);
export const dilate = (m, w, h) => morph(m, w, h, false);

export function cleanMask(mask, w, h, openIter = DEFAULTS.openIter, closeIter = DEFAULTS.closeIter) {
  let m = mask;
  if (openIter > 0) { // opening: erode xN then dilate xN (as cv2.morphologyEx iterations)
    for (let i = 0; i < openIter; i++) m = erode(m, w, h);
    for (let i = 0; i < openIter; i++) m = dilate(m, w, h);
  }
  if (closeIter > 0) { // closing: dilate xN then erode xN
    for (let i = 0; i < closeIter; i++) m = dilate(m, w, h);
    for (let i = 0; i < closeIter; i++) m = erode(m, w, h);
  }
  return m;
}

// ---------------------------------------------------------------- regions
/** 8-connected components; returns the largest blob >= minArea with its pixel-moment centroid. */
export function findMarker(mask, w, h, minArea = DEFAULTS.minArea) {
  const labels = new Int32Array(w * h);
  const stack = new Int32Array(w * h);
  let next = 0, blobs = 0, rejected = 0, best = null;
  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || labels[start]) continue;
    next++; blobs++;
    let sp = 0, area = 0, sx = 0, sy = 0, x0 = w, y0 = h, x1 = -1, y1 = -1;
    stack[sp++] = start; labels[start] = next;
    while (sp) {
      const p = stack[--sp], x = p % w, y = (p - x) / w;
      area++; sx += x; sy += y;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      for (let dy = -1; dy <= 1; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w) continue;
          const q = ny * w + nx;
          if (mask[q] && !labels[q]) { labels[q] = next; stack[sp++] = q; }
        }
      }
    }
    if (area < minArea) { rejected++; continue; }
    if (!best || area > best.area) best = { area, x: sx / area, y: sy / area, bbox: [x0, y0, x1 - x0 + 1, y1 - y0 + 1] };
  }
  if (!best) return { found: false, x: 0, y: 0, area: 0, bbox: null, blobCount: blobs, rejectedSmall: rejected };
  return { found: true, ...best, blobCount: blobs, rejectedSmall: rejected };
}

// ---------------------------------------------------------------- temporal / demos
/** |I_t - I_(t-1)| > threshold. Returns { mask (0/1), energy (fraction changed) }. */
export function frameDifference(prev, gray, threshold = DEFAULTS.diffThreshold) {
  const mask = new Uint8Array(gray.length);
  if (!prev || prev.length !== gray.length) return { mask, energy: 0 };
  let changed = 0;
  for (let i = 0; i < gray.length; i++) if (Math.abs(gray[i] - prev[i]) > threshold) { mask[i] = 1; changed++; }
  return { mask, energy: changed / gray.length };
}

/** Sobel gradient magnitude thresholded into an edge map (diagnostic demo). */
export function sobelEdges(gray, w, h, threshold = DEFAULTS.sobelThreshold) {
  const out = new Uint8Array(w * h), t2 = threshold * threshold;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const p = y * w + x;
      const gx = -gray[p - w - 1] - 2 * gray[p - 1] - gray[p + w - 1] + gray[p - w + 1] + 2 * gray[p + 1] + gray[p + w + 1];
      const gy = -gray[p - w - 1] - 2 * gray[p - w] - gray[p - w + 1] + gray[p + w - 1] + 2 * gray[p + w] + gray[p + w + 1];
      out[p] = gx * gx + gy * gy > t2 ? 1 : 0;
    }
  }
  return out;
}

/** HSV range from a patch of the marker; hue centre is a circular mean (hue is an angle). */
export function rangeFromSample(hsv, w, h, box = DEFAULTS.sampleBox, hMargin = 8, sMargin = 50, vMargin = 60) {
  const half = box >> 1, cx = w >> 1, cy = h >> 1;
  const H = [], S = [], V = [];
  for (let y = cy - half; y < cy + half; y++) {
    for (let x = cx - half; x < cx + half; x++) {
      const i = (y * w + x) * 3;
      H.push(hsv[i]); S.push(hsv[i + 1]); V.push(hsv[i + 2]);
    }
  }
  let sn = 0, cs = 0;
  for (const v of H) { const a = (v * Math.PI) / 90; sn += Math.sin(a); cs += Math.cos(a); }
  const centre = ((((Math.atan2(sn, cs) * 90) / Math.PI) % 180) + 180) % 180;
  const dist = H.map((v) => Math.abs(((v - centre + 90) % 180 + 180) % 180 - 90));
  const spread = Math.min(40, percentile(dist, 90) + hMargin);
  const clamp = (v) => Math.max(40, Math.min(255, Math.round(v)));
  const mod = (v) => ((Math.round(v) % 180) + 180) % 180;
  return { name: "sampled", lower: [mod(centre - spread), clamp(percentile(S, 10) - sMargin), clamp(percentile(V, 10) - vMargin)],
           upper: [mod(centre + spread), 255, 255] };
}

function percentile(values, p) {
  const a = [...values].sort((x, y) => x - y);
  const k = ((a.length - 1) * p) / 100, f = Math.floor(k), c = Math.min(a.length - 1, f + 1);
  return a[f] + (a[c] - a[f]) * (k - f);
}

export class PositionSmoother {
  constructor(alpha = DEFAULTS.smoothingAlpha, holdFrames = DEFAULTS.lostHoldFrames) {
    this.alpha = Math.min(1, Math.max(0.01, alpha)); this.holdFrames = holdFrames; this.reset();
  }
  reset() { this.pos = null; this.missed = 0; }
  get holding() { return this.pos !== null && this.missed > 0; }
  update(point) {
    if (point) {
      const a = this.alpha;
      this.pos = this.pos ? [a * point[0] + (1 - a) * this.pos[0], a * point[1] + (1 - a) * this.pos[1]] : [...point];
      this.missed = 0;
    } else if (++this.missed > this.holdFrames) this.pos = null;
    return this.pos;
  }
}

export class MotionEstimator {
  constructor(smoothing = DEFAULTS.motionSmoothing, still = DEFAULTS.stillThreshold) {
    this.k = smoothing; this.still = still; this.prev = null; this.prevT = null;
    this.info = { dx: 0, dy: 0, vx: 0, vy: 0, speed: 0, direction: "--" };
  }
  update(point, t) {
    if (!point) { this.prev = this.prevT = null; return (this.info = { dx: 0, dy: 0, vx: 0, vy: 0, speed: 0, direction: "--" }); }
    if (!this.prev || t <= this.prevT) {
      this.prev = point; this.prevT = t;
      return (this.info = { dx: 0, dy: 0, vx: 0, vy: 0, speed: 0, direction: "STILL" });
    }
    const dt = t - this.prevT, dx = point[0] - this.prev[0], dy = point[1] - this.prev[1];
    const vx = this.k * (dx / dt) + (1 - this.k) * this.info.vx;
    const vy = this.k * (dy / dt) + (1 - this.k) * this.info.vy;
    const speed = Math.hypot(vx, vy);
    let direction = "STILL";
    if (speed >= this.still) {
      const parts = [];
      if (Math.abs(vy) > 0.4 * speed) parts.push(vy < 0 ? "UP" : "DOWN");
      if (Math.abs(vx) > 0.4 * speed) parts.push(vx < 0 ? "LEFT" : "RIGHT");
      direction = parts.join("-");
    }
    this.prev = point; this.prevT = t;
    return (this.info = { dx, dy, vx, vy, speed, direction });
  }
}

/** Full pipeline on one RGBA frame (already mirrored and scaled to w x h). */
export function processFrame(rgba, w, h, settings, prevGray = null) {
  const s = { ...DEFAULTS, ...settings };
  const frame = s.blur ? gaussianBlur5(rgba, w, h) : rgba;
  const hsv = rgbaToHsv(frame, w, h);
  const rawMask = segmentHsv(hsv, w, h, s.range);
  const mask = cleanMask(rawMask, w, h, s.openIter, s.closeIter);
  const detection = findMarker(mask, w, h, s.minArea);
  const gray = rgbaToGray(frame, w, h);
  const result = { frame, hsv, rawMask, mask, gray, detection,
                   point: detection.found ? [detection.x / w, detection.y / h] : null,
                   edges: null, motionMask: null, motionEnergy: 0 };
  if (s.extras) {
    result.edges = sobelEdges(gray, w, h, s.sobelThreshold);
    const diff = frameDifference(prevGray, gray, s.diffThreshold);
    result.motionMask = diff.mask; result.motionEnergy = diff.energy;
  }
  return result;
}
