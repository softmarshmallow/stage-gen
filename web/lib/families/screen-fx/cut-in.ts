// The cut-in choreography, as arithmetic: time in, transforms out.
//
// A cut-in is a rip sweeping in, a portrait sliding in behind the rip's mask
// with overshoot, a backdrop that keeps moving, lettering that lands, a hold,
// and a tear-away. Every one of those is a transform on a separate part, and
// every number here is consumer-owned: only the feel depends on it, so no
// refusal does. Nothing in this module knows Phaser, a genre, or a world —
// it is the same register as `sideview-runner/presentation.ts`: a pure
// function of elapsed time that a fixed-step replay reproduces exactly.

export const CUT_IN_CHOREOGRAPHY_NAMES = ["tear_reveal_v1"] as const;
export type CutInChoreographyName = (typeof CUT_IN_CHOREOGRAPHY_NAMES)[number];

/** Every beat of one choreography, in milliseconds from the moment it starts. */
export interface CutInChoreography {
  readonly name: CutInChoreographyName;
  /** The rip sweeps in from off-screen right over this window. */
  readonly ripInEndMs: number;
  /** The portrait slides in behind the mask over this window, with overshoot. */
  readonly bustInStartMs: number;
  readonly bustInEndMs: number;
  /** The lettering banner slams in from the right over this window. */
  readonly bannerInStartMs: number;
  readonly bannerInEndMs: number;
  /** The game frame under the overlay dims from here. */
  readonly dimFromMs: number;
  /** When a consumer may resume its simulation: the tear-away begins. */
  readonly releaseMs: number;
  /** The overlay is gone. */
  readonly durationMs: number;
  /** Backdrop stripe drift, in stripe periods per second. */
  readonly stripeDriftPerSecond: number;
}

export const CUT_IN_CHOREOGRAPHIES: Readonly<
  Record<CutInChoreographyName, CutInChoreography>
> = Object.freeze({
  tear_reveal_v1: Object.freeze({
    name: "tear_reveal_v1",
    ripInEndMs: 180,
    bustInStartMs: 100,
    bustInEndMs: 400,
    bannerInStartMs: 300,
    bannerInEndMs: 480,
    dimFromMs: 600,
    releaseMs: 1600,
    durationMs: 1900,
    stripeDriftPerSecond: 4.4,
  }),
});

/** The scale the rip arrives at before settling to 1. */
export const RIP_ENTRY_SCALE = 1.12;
/** How far left of centre the portrait starts, as a fraction of the frame width. */
export const BUST_ENTRY_OFFSET = -0.3;
/** The portrait's entry scale relative to its settled size. */
export const BUST_ENTRY_SCALE = 1.25;
/** The slow push-in over the hold, relative to the settled size. */
export const BUST_HOLD_PUSH = 0.04;
/** How dark the game frame goes under the overlay. */
export const CUT_IN_DIM = 0.35;

/** One frame of the choreography: the transforms a view applies, and two marks. */
export interface CutInFrame {
  /** Rip group offset from its resting place, in view widths; 1 is fully off right. */
  readonly ripX: number;
  readonly ripScale: number;
  /** Portrait offset from the frame's centre, in frame widths. */
  readonly bustDx: number;
  /** Portrait scale relative to its settled size. */
  readonly bustScale: number;
  /** Stripe drift, in stripe periods; the view wraps it. */
  readonly stripePhase: number;
  /** Banner offset from its resting place, in view widths. */
  readonly bannerX: number;
  /** Opacity of the dimming scrim over the game frame. */
  readonly dim: number;
  /** The consumer may resume its simulation. */
  readonly released: boolean;
  /** The overlay is gone. */
  readonly finished: boolean;
}

function segment(t: number, start: number, end: number): number {
  return Math.min(1, Math.max(0, (t - start) / (end - start)));
}

function easeOutCubic(x: number): number {
  return 1 - (1 - x) ** 3;
}

function easeInCubic(x: number): number {
  return x ** 3;
}

function easeOutBack(x: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
}

/** The choreography at `elapsedMs`. Throws on a non-finite or negative clock. */
export function cutInFrame(elapsedMs: number, choreography: CutInChoreography): CutInFrame {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
    throw new Error(`cut-in elapsed time must be a non-negative finite number, got ${elapsedMs}`);
  }
  const entry = easeOutCubic(segment(elapsedMs, 0, choreography.ripInEndMs));
  const exit = easeInCubic(segment(elapsedMs, choreography.releaseMs, choreography.durationMs));
  const bustIn = segment(elapsedMs, choreography.bustInStartMs, choreography.bustInEndMs);
  const hold = segment(elapsedMs, choreography.bustInEndMs, choreography.releaseMs);
  const bannerIn = easeOutCubic(
    segment(elapsedMs, choreography.bannerInStartMs, choreography.bannerInEndMs),
  );
  return Object.freeze({
    ripX: (1 - entry) - exit * 1.15,
    ripScale: RIP_ENTRY_SCALE - (RIP_ENTRY_SCALE - 1) * entry,
    bustDx: BUST_ENTRY_OFFSET * (1 - easeOutBack(bustIn)),
    bustScale:
      (BUST_ENTRY_SCALE - (BUST_ENTRY_SCALE - 1) * easeOutCubic(bustIn)) *
      (1 + BUST_HOLD_PUSH * hold),
    stripePhase: (elapsedMs / 1000) * choreography.stripeDriftPerSecond,
    bannerX: (1 - bannerIn) * 0.55 - exit * 1.15,
    dim: elapsedMs >= choreography.dimFromMs ? CUT_IN_DIM : 0,
    released: elapsedMs >= choreography.releaseMs,
    finished: elapsedMs >= choreography.durationMs,
  });
}
