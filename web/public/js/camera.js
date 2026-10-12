// Webcam acquisition + per-frame processing in the browser (port of VisionTracker).
import { DEFAULTS, MotionEstimator, PositionSmoother, makeRange, processFrame, rangeFromSample } from "./vision.js";

export const STATUS = {
  OFF: "OFF", ASKING: "ASKING PERMISSION", TRACKING: "TRACKING", HOLDING: "HOLDING", SEARCHING: "SEARCHING",
  NO_CAMERA: "NO CAMERA", DENIED: "DENIED", ERROR: "ERROR",
};

/** Human-readable explanation of a getUserMedia failure. */
export function describeCameraError(err) {
  const name = err && err.name;
  if (name === "NotAllowedError" || name === "SecurityError")
    return [STATUS.DENIED, "Camera permission denied - click the camera icon in the address bar to allow it"];
  if (name === "NotFoundError" || name === "OverconstrainedError") return [STATUS.NO_CAMERA, "No webcam found"];
  if (name === "NotReadableError" || name === "AbortError") return [STATUS.ERROR, "Camera is busy - close other apps using it"];
  if (name === "InsecureContext") return [STATUS.ERROR, "Webcam needs HTTPS (or localhost)"];
  return [STATUS.ERROR, `Camera error: ${(err && err.message) || name || "unknown"}`];
}

export class CameraTracker {
  constructor() {
    this.w = DEFAULTS.width; this.h = DEFAULTS.height;
    this.video = document.createElement("video");
    this.video.muted = true; this.video.playsInline = true; this.video.setAttribute("playsinline", "");
    this.canvas = document.createElement("canvas"); this.canvas.width = this.w; this.canvas.height = this.h;
    this.g = this.canvas.getContext("2d", { willReadFrequently: true });
    this.range = loadRange() || makeRange("green");
    this.extras = false;
    this.smoother = new PositionSmoother(); this.motion = new MotionEstimator();
    this.status = STATUS.OFF; this.message = ""; this.position = null; this.result = null;
    this.frameId = 0; this.fps = 0; this.procMs = 0; this.stream = null;
    this._lastTime = -1; this._lastStamp = 0; this._prevGray = null; this._sample = false; this.lastSample = null;
    this.worker = undefined; this._busy = false; this._jobId = 0; this._captureT = 0; this.motionInfo = this.motion.info;
  }

  get running() { return !!this.stream; }

  async start() {
    if (this.stream) return true;
    if (!window.isSecureContext) { [this.status, this.message] = describeCameraError({ name: "InsecureContext" }); return false; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      [this.status, this.message] = [STATUS.NO_CAMERA, "This browser has no webcam API"]; return false;
    }
    this.status = STATUS.ASKING; this.message = "Allow camera access in the browser prompt";
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false });
      this.video.srcObject = this.stream;
      await this.video.play();
      for (const track of this.stream.getVideoTracks()) track.addEventListener("ended", () => this._fail(STATUS.ERROR, "Camera disconnected"));
      this.status = STATUS.SEARCHING; this.message = "Show the coloured marker";
      this.smoother.reset();
      this._startWorker();
      return true;
    } catch (err) {
      this.stop();
      [this.status, this.message] = describeCameraError(err);
      return false;
    }
  }

  _fail(status, message) { this.stop(); this.status = status; this.message = message; }

  stop() {
    if (this.stream) for (const t of this.stream.getTracks()) t.stop();
    this.stream = null; this.video.srcObject = null; this.position = null; this.result = null; this._busy = false;
    this.status = STATUS.OFF; this.message = "Webcam off";
  }

  setRange(range) { this.range = range; this.smoother.reset(); }
  requestSample() { this._sample = true; }

  /** Call every animation frame. Grabs a new video frame when the worker is idle. */
  poll() {
    const v = this.video;
    if (!this.stream || this._busy || v.readyState < 2 || v.currentTime === this._lastTime) return false;
    this._lastTime = v.currentTime;
    this.g.save(); this.g.translate(this.w, 0); this.g.scale(-1, 1);       // mirror
    this.g.drawImage(v, 0, 0, this.w, this.h);                               // downscale to 320x240
    this.g.restore();
    const rgba = this.g.getImageData(0, 0, this.w, this.h).data;
    const job = { id: ++this._jobId, rgba: rgba.buffer, w: this.w, h: this.h, range: this.range, extras: this.extras, sample: this._sample };
    this._sample = false;
    this._captureT = performance.now() / 1000;
    if (this.worker) { this._busy = true; this.worker.postMessage(job, [job.rgba]); }
    else this._onResult(this._processLocally(job));
    return true;
  }

  _startWorker() {
    if (this.worker !== undefined) return;
    try {
      this.worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
      this.worker.onmessage = (e) => { this._busy = false; this._onResult(e.data); };
      this.worker.onerror = () => { this.worker.terminate(); this.worker = null; this._busy = false; }; // fall back to main thread
    } catch { this.worker = null; }
  }

  _processLocally(job) { // main-thread fallback when module workers are unavailable
    const t0 = performance.now();
    const res = processFrame(new Uint8ClampedArray(job.rgba), job.w, job.h, { range: job.range, extras: job.extras }, this._prevGray);
    this._prevGray = res.gray;
    return { ...res, procMs: performance.now() - t0, sampled: job.sample ? rangeFromSample(res.hsv, job.w, job.h) : null };
  }

  _onResult(res) {
    if (!this.stream) return;
    if (res.sampled) { this.lastSample = res.sampled; this.setRange(res.sampled); saveRange(res.sampled); }
    this.position = this.smoother.update(res.point);
    this.motionInfo = this.motion.update(this.position, this._captureT);
    this.status = res.detection.found ? STATUS.TRACKING : this.position ? STATUS.HOLDING : STATUS.SEARCHING;
    this.message = { TRACKING: "Marker locked", HOLDING: "Marker lost - holding", SEARCHING: "Show the coloured marker" }[this.status];
    const now = performance.now();
    if (this._lastStamp) { const inst = 1000 / (now - this._lastStamp); this.fps = this.fps ? 0.9 * this.fps + 0.1 * inst : inst; }
    this._lastStamp = now;
    this.procMs = res.procMs; this.result = res; this.frameId++;
  }
}

function loadRange() {
  try { const r = JSON.parse(localStorage.getItem("pq.hsv")); return r && r.lower && r.upper ? r : null; } catch { return null; }
}
function saveRange(r) { try { localStorage.setItem("pq.hsv", JSON.stringify(r)); } catch { /* storage unavailable */ } }
