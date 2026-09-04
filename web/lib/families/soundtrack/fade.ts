// Fades: the gain along one, and the machine that walks a sequence of them.
//
// The runner's half of the family. A transition is authored as an action with a
// fade time and a curve, and a duck is three fades in a row (down, hold, back),
// so the machine is a queue of steps advanced on a frame scheduler rather than
// a single interpolation — and a new transition cancels the one in flight,
// which is the whole of "one fade at a time".
//
// The curves are Web Audio's own ramp shapes, so a fade written here and a fade
// written on a gain node sound the same; an exponential ramp cannot pass
// through zero, hence the floor.

/** Web Audio's exponential-ramp floor: a geometric fade cannot pass through zero. */
const EXPONENTIAL_FLOOR = 0.0001;

export type FadeCurve = "linear" | "exponential";

export interface FadeStep {
  readonly to: number;
  readonly seconds: number;
  readonly curve: FadeCurve;
}

/** The gain at `progress` (0..1) along a fade, as Web Audio's ramps define the shapes. */
export function fadeGain(from: number, to: number, progress: number, curve: FadeCurve): number {
  const clamped = Math.max(0, Math.min(1, progress));
  if (curve === "linear") return from + (to - from) * clamped;
  const start = Math.max(from, EXPONENTIAL_FLOOR);
  const end = Math.max(to, EXPONENTIAL_FLOOR);
  return start * (end / start) ** clamped;
}

export interface FadeRunnerPorts {
  /** Frame scheduler; returns the cancel. */
  readonly schedule: (callback: () => void) => () => void;
  /** Monotonic milliseconds. */
  readonly now: () => number;
  /** The gain being faded, or null when there is nothing to fade. */
  readonly gain: () => number | null;
  readonly setGain: (value: number) => void;
}

/**
 * One fade at a time, over a sequence of steps.
 *
 * Lifecycle-bound state — the steps left, when the current one started, and the
 * gain it started from — so it is a class: a fade outlives the call that asked
 * for it and has to be cancellable by the next one.
 */
export class FadeRunner {
  private steps: FadeStep[] = [];
  private stepStart = 0;
  private stepFrom = 0;
  private settled: (() => void) | undefined;
  private cancelTick: (() => void) | undefined;

  constructor(private readonly ports: FadeRunnerPorts) {}

  /** Stop whatever is fading; the gain stays wherever it had reached. */
  cancel(): void {
    this.cancelTick?.();
    this.cancelTick = undefined;
    this.steps = [];
    this.settled = undefined;
  }

  /** Cancel the fade in flight and walk `next`, calling `onSettled` at the end. */
  run(next: readonly FadeStep[], onSettled?: () => void): void {
    this.cancel();
    const gain = this.ports.gain();
    if (gain === null) return;
    this.steps = [...next];
    this.stepStart = this.ports.now();
    this.stepFrom = gain;
    this.settled = onSettled;
    this.tick();
  }

  private readonly tick = (): void => {
    this.cancelTick = undefined;
    const gain = this.ports.gain();
    if (gain === null) {
      this.steps = [];
      return;
    }
    while (this.steps.length > 0) {
      const step = this.steps[0];
      const elapsed = (this.ports.now() - this.stepStart) / 1_000;
      const progress = step.seconds <= 0 ? 1 : Math.min(1, elapsed / step.seconds);
      const value =
        progress >= 1 ? step.to : fadeGain(this.stepFrom, step.to, progress, step.curve);
      this.ports.setGain(value);
      if (progress < 1) {
        this.cancelTick = this.ports.schedule(this.tick);
        return;
      }
      this.steps.shift();
      this.stepStart = this.ports.now();
      this.stepFrom = this.ports.gain() ?? value;
    }
    const done = this.settled;
    this.settled = undefined;
    done?.();
  };
}
