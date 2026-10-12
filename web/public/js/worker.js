// Vision worker: runs the segmentation pipeline off the main thread
// (the browser equivalent of the desktop VisionTracker background thread).
import { processFrame, rangeFromSample } from "./vision.js";

let prevGray = null;

self.onmessage = (e) => {
  const { id, rgba, w, h, range, extras, sample } = e.data;
  const t0 = performance.now();
  const res = processFrame(new Uint8ClampedArray(rgba), w, h, { range, extras }, prevGray);
  prevGray = res.gray;
  const sampled = sample ? rangeFromSample(res.hsv, w, h) : null;
  const msg = { id, point: res.point, detection: res.detection, motionEnergy: res.motionEnergy,
                procMs: performance.now() - t0, sampled, frame: null, rawMask: null, mask: null, edges: null, motionMask: null };
  const transfer = [];
  if (extras) { // images only needed for the diagnostics view
    for (const k of ["frame", "rawMask", "mask", "edges", "motionMask"]) {
      if (res[k]) { msg[k] = res[k]; transfer.push(res[k].buffer); }
    }
  }
  self.postMessage(msg, transfer);
};
