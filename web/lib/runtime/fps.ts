// Lightweight FPS probe.
//
// Hooks into requestAnimationFrame to measure instantaneous FPS, rolling
// 1-second average, and per-window minimum across a sliding 30s window.
// Surfaces results on window.__sceneFps so headless verifiers can read.

export type FpsSnapshot = {
  /** Last per-frame instantaneous FPS. */
  fps: number;
  /** Rolling 1-second average. */
  avg1s: number;
  /** Minimum 1s-average seen across the most recent windowSec seconds. */
  minOverWindow: number;
  /** How many seconds of data are in the rolling window. */
  windowSec: number;
  /** Total frames since probe start. */
  frames: number;
};

export class FpsProbe {
  private windowSec: number;
  private buckets: number[] = []; // frames per second bucket
  private lastBucketAt = 0;
  private bucketFrames = 0;
  private lastFrameAt = 0;
  private snapshot: FpsSnapshot;
  private rafHandle: number | null = null;
  private startedAt = 0;

  constructor(windowSec: number = 30) {
    this.windowSec = windowSec;
    this.snapshot = {
      fps: 0,
      avg1s: 0,
      minOverWindow: 0,
      windowSec,
      frames: 0,
    };
  }

  start() {
    if (typeof window === "undefined") return;
    this.startedAt = performance.now();
    this.lastBucketAt = this.startedAt;
    this.lastFrameAt = this.startedAt;
    const tick = (t: number) => {
      const dt = t - this.lastFrameAt;
      this.lastFrameAt = t;
      this.snapshot.frames++;
      this.bucketFrames++;
      if (dt > 0) this.snapshot.fps = 1000 / dt;
      // Close 1-second buckets.
      while (t - this.lastBucketAt >= 1000) {
        this.buckets.push(this.bucketFrames);
        this.bucketFrames = 0;
        this.lastBucketAt += 1000;
        if (this.buckets.length > this.windowSec) this.buckets.shift();
        this.snapshot.avg1s = this.buckets[this.buckets.length - 1] ?? 0;
        this.snapshot.minOverWindow =
          this.buckets.length > 0 ? Math.min(...this.buckets) : 0;
      }
      // Surface to window for headless probes.
      if (typeof window !== "undefined") {
        (window as unknown as { __sceneFps?: FpsSnapshot }).__sceneFps = {
          ...this.snapshot,
        };
      }
      this.rafHandle = requestAnimationFrame(tick);
    };
    this.rafHandle = requestAnimationFrame(tick);
  }

  stop() {
    if (this.rafHandle != null && typeof window !== "undefined") {
      cancelAnimationFrame(this.rafHandle);
      this.rafHandle = null;
    }
  }
}
