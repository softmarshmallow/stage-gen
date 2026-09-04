// The `vitals` family: what a contact costs, and what happens after it.
//
// "What a contact costs" was written twice. The runner has a consequence per
// source, a gauge, a refractory window and a recovery; the platformer has the
// same window, the same blink, the same absorb-while-immune rule and the same
// arithmetic, spelled out again in the second half of `combat.ts` under other
// names — `PlayerHealthState` is `Gauge` with four fields renamed.
//
// The objection to one family is that "health is an RPG thing and vitals is an
// arcade thing". It does not survive contact with the code: the runner's own
// primitive was extracted *from* the platformer's bar, both genres immunise
// for nine hundred milliseconds and blink at seventy-five, and `docs` already
// calls hit points, mana, stamina and fuel one model. What differs between
// them is not the model, it is the *table*: which occurrences can hurt, and
// what each of them means for this package.
//
// So sources are opaque strings — the family never learns what a `pit` is —
// consequences are a table the package authors, and putting a survivor back
// somewhere legal is a port the space family answers, because "where is there
// solid ground ahead of here" is a question about the world and not about a
// gauge.

import { drain, isRefractory, refractoryBlinkAlpha, type Gauge } from "@/lib/kernel/gauge";

/** What one source means for this package. */
export type Consequence = "end_run_v1" | "drain_v1" | "drain_and_recover_v1";

export const CONSEQUENCES: readonly Consequence[] = Object.freeze([
  "end_run_v1",
  "drain_v1",
  "drain_and_recover_v1",
]);

/**
 * How a body behaves after a hit connects.
 *
 * The four numbers both genres had, and had the same values for. The window is
 * the one that matters: contact is continuous — a hazard the avatar is
 * standing inside, a creature standing inside the player — so without it a
 * single clip empties a three-point gauge before the player's hand leaves the
 * key. The rest is feel, and feel is consumer-owned by the same rule the
 * runner's own file states: a number belongs to the manifest iff a refusal
 * depends on it.
 */
export interface HurtProfile {
  /** Points one contact spends. */
  readonly drainAmount: number;
  /** Immunity after a contact, in ms. */
  readonly refractoryMs: number;
  /** One bright/dim phase while the window is open, in ms. */
  readonly blinkIntervalMs: number;
  /** Dim phase opacity: trackable in play, unmistakable as immunity. */
  readonly blinkAlpha: number;
}

/**
 * The profile both genres arrived at independently.
 *
 * 900ms is comfortably longer than any authored hazard's crossing at the
 * runner's base speed and longer than a creature's strike cadence in the
 * platformer, so one prop, or one mob, can only ever cost one point.
 */
export const CONTACT_HURT_PROFILE: HurtProfile = Object.freeze({
  drainAmount: 1,
  refractoryMs: 900,
  blinkIntervalMs: 75,
  blinkAlpha: 0.35,
});

export interface VitalsSlice<R> {
  /** Null exactly when no consequence drains — a one-hit-kill package. */
  gauge: Gauge | null;
  /**
   * The clock, in milliseconds, the gauge was last evaluated against.
   *
   * A fixed step counts in seconds while a window counts in milliseconds, and
   * presentation must blink against exactly the clock the window was written
   * from. So the conversion happens once, here, and everything that needs the
   * time reads this rather than converting again.
   */
  clockMs: number;
  /**
   * Where a survivor is to be put down, applied by the body's own author next
   * frame.
   *
   * Not written straight onto the body, and the sealer is what proved that
   * cannot work: the body emits the occurrence, so a vitals system that wrote
   * it back would have to run both before and after it. A one-frame feedback
   * hand-off is the honest shape.
   */
  pendingRecovery: R | null;
  /** Set on the frame a drain connected, for a cue and a bar flash. */
  hurtThisFrame: boolean;
  /** Set on the frame the gauge emptied, so a lifecycle ends the run once. */
  depletedThisFrame: boolean;
}

/** What one resolved source amounts to. The host says it in its own vocabulary. */
export type VitalsVerdict<S extends string> =
  | { readonly kind: "drained"; readonly source: S; readonly remaining: number }
  | { readonly kind: "absorbed"; readonly source: S }
  | { readonly kind: "ended"; readonly source: S };

export interface ResolveVitalsArgs<S extends string, R> {
  readonly vitals: VitalsSlice<R>;
  /** This frame's sources, in the order they happened. */
  readonly sources: readonly S[];
  /** What each source means for this package. */
  readonly consequences: Readonly<Partial<Record<S, Consequence | null>>>;
  readonly profile: HurtProfile;
  /**
   * Where to put a survivor down, or null when there is nowhere.
   *
   * The `RecoveryPolicy` port. The space family answers it — "the first solid
   * surface at or after here" is a question about the world — and a genre
   * without one passes a policy that always answers null, which turns a
   * forgiving consequence into a terminal one rather than into a silent
   * teleport.
   */
  recover(source: S): R | null;
}

/**
 * Turn this frame's sources into what they cost.
 *
 * One frame can carry several — clipping a prop on the way into a pit is
 * ordinary play. They are resolved in the order they happened, and the
 * refractory window makes all but the first absorbed, so a compound accident
 * costs one point rather than three. The first verdict that ends the run is
 * the last verdict: nothing after it is resolved, because there is no longer
 * anything to resolve it against.
 */
export function resolveVitals<S extends string, R>(
  args: ResolveVitalsArgs<S, R>,
): readonly VitalsVerdict<S>[] {
  const { vitals, consequences, profile } = args;
  const verdicts: VitalsVerdict<S>[] = [];
  for (const source of args.sources) {
    const consequence = consequences[source];

    // A missing answer must still not forgive the hit. The contract pairs an
    // answer with the occurrence that can deliver it, so this is unreachable
    // for a well-formed package — and silently surviving would be the worst
    // possible way to find out that it is not.
    if (consequence === undefined || consequence === null || consequence === "end_run_v1") {
      verdicts.push({ kind: "ended", source });
      return verdicts;
    }

    const gauge = vitals.gauge;
    if (gauge === null) {
      // A package whose consequences all end the run has no gauge, and the
      // contract refuses this combination — but a draining consequence
      // reaching a missing gauge must still not silently forgive the hit.
      verdicts.push({ kind: "ended", source });
      return verdicts;
    }

    const change = drain(gauge, profile.drainAmount, vitals.clockMs, profile.refractoryMs);
    if (!change.connected) {
      verdicts.push({ kind: "absorbed", source });
      continue;
    }
    vitals.gauge = change.gauge;
    vitals.hurtThisFrame = true;
    verdicts.push({ kind: "drained", source, remaining: change.after });

    if (consequence === "drain_and_recover_v1") {
      const somewhere = args.recover(source);
      if (somewhere === null) {
        // A forgiving package should not become an unplayable one on a
        // malformed world: with nowhere to stand, the run ends instead.
        verdicts.push({ kind: "ended", source });
        return verdicts;
      }
      vitals.pendingRecovery = somewhere;
    }

    if (change.depleted) {
      vitals.depletedThisFrame = true;
      verdicts.push({ kind: "ended", source });
      return verdicts;
    }
  }
  return verdicts;
}

/** Whether the body is inside its post-contact immunity window. */
export function bodyIsImmune<R>(vitals: VitalsSlice<R>): boolean {
  return vitals.gauge !== null && isRefractory(vitals.gauge, vitals.clockMs);
}

/** Sprite opacity for this frame: the shared blink, at this profile's cadence. */
export function bodyBlinkAlpha<R>(vitals: VitalsSlice<R>, profile: HurtProfile): number {
  if (vitals.gauge === null) return 1;
  return refractoryBlinkAlpha(
    vitals.gauge,
    vitals.clockMs,
    profile.blinkIntervalMs,
    profile.blinkAlpha,
  );
}

/** A fixed step counts seconds; a gauge counts milliseconds. Converted once. */
export function vitalsClockMs(simulationNowSeconds: number): number {
  return simulationNowSeconds * 1000;
}
