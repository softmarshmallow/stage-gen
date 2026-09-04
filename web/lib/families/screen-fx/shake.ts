// Camera shake: a decaying, seeded nudge, and the rule for adding several up.
//
// It was a private method on a Phaser scene that mutated `camera.scrollX`
// directly, which is why every parallax layer inherited it without declaring
// anything — a family cannot own an effect whose only expression is a write
// into somebody else's field. The arithmetic here is pure and returns an
// *offset*: what a host does with it is the host's business, and the step this
// lands in leaves the platformer applying it exactly where it did. Making the
// offset a declared `camera` input rather than a scroll mutation is the camera
// family's move, in the next step, and it is cheap precisely because the
// number is already a value rather than a side effect.
//
// Deterministic and clock-free by construction: the phase is a hash of the
// source's seed and the elapsed time is passed in, so a fixed-step replay
// produces identical frames and a reduced-motion viewer is served by a caller
// that simply does not raise a source.

export interface ShakeProfile {
  /** Peak horizontal amplitude, in pixels. */
  readonly amplitudePx: number;
  /** How long one source shakes for, in ms. */
  readonly durationMs: number;
  /** How long one step of the pattern holds, in ms — the shake's frame rate. */
  readonly stepMs: number;
  /** The pattern walked, one entry per step, scaled by the decay. */
  readonly pattern: readonly number[];
  /** Vertical amplitude as a fraction of horizontal, and two steps out of phase. */
  readonly verticalFraction: number;
}

/**
 * The profile a kill shakes at.
 *
 * 130ms is about four frames at 30Hz: long enough to register as weight,
 * short enough that a busy fight does not turn into a permanent tremor. The
 * clamp on the sum is what actually guarantees the second half of that.
 */
export const KILL_SHAKE_PROFILE: ShakeProfile = Object.freeze({
  amplitudePx: 4,
  durationMs: 130,
  stepMs: 16,
  pattern: Object.freeze([1, -0.8, 0.55, -0.35, 0.2, 0]),
  verticalFraction: 0.6,
});

export type ShakeOffset = Readonly<{ x: number; y: number }>;

export const NO_SHAKE: ShakeOffset = Object.freeze({ x: 0, y: 0 });

/** One thing currently shaking the view. */
export interface ShakeSource {
  /** Which pattern phase this source starts at; any integer. */
  readonly seed: number;
  /** How long it has been shaking. */
  readonly elapsedMs: number;
  /** Which way the blow was going, so the nudge reads as a direction. */
  readonly dirSign: number;
  /** Emphasis: a critical shakes harder than an ordinary kill. */
  readonly scale: number;
}

/** The offset one source contributes this frame; zero once it has run out. */
export function sampleShake(source: ShakeSource, profile: ShakeProfile): ShakeOffset {
  const { elapsedMs } = source;
  if (elapsedMs >= profile.durationMs) return NO_SHAKE;
  const step = Math.floor(elapsedMs / profile.stepMs);
  const phase = Math.abs(Math.trunc(source.seed)) % profile.pattern.length;
  const decay = 1 - elapsedMs / profile.durationMs;
  const amplitude = profile.amplitudePx * source.scale * decay;
  return Object.freeze({
    x: profile.pattern[(phase + step) % profile.pattern.length] * amplitude * source.dirSign,
    y:
      profile.pattern[(phase + step + 2) % profile.pattern.length] *
      amplitude *
      profile.verticalFraction,
  });
}

/**
 * Every live source summed and clamped.
 *
 * The clamp is the part that is not obvious and is not optional: shakes add,
 * and three kills in one frame would otherwise throw the view further than any
 * single one ever could — a bound the player reads as the camera breaking
 * rather than as three kills.
 */
export function sumShake(samples: Iterable<ShakeOffset>, boundPx: number): ShakeOffset {
  let x = 0;
  let y = 0;
  for (const sample of samples) {
    x += sample.x;
    y += sample.y;
  }
  return Object.freeze({
    x: Math.max(-boundPx, Math.min(boundPx, x)),
    y: Math.max(-boundPx, Math.min(boundPx, y)),
  });
}
