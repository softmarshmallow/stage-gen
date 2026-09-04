// Whether an actor has noticed you, and what it does about having lost you.
//
// The one genuinely stateful thing in either arbitrator, and the one thing a
// pure auction cannot express: acquisition and retention are not symmetric. An
// actor that engages the moment a condition holds and disengages the moment it
// stops flickers on the boundary and, worse, abandons a chase wherever the
// boundary happened to catch it. So losing the engagement enters an explicit
// *returning* mode that persists until the actor is home, and it never falls
// through to an arbitrary patrol step at the territory edge.
//
// Three modes, two edges, no numbers. Every number — how near is near, how far
// is home — is the profile's, which is genre content; what is here is the
// hysteresis, which is not.

export type AwarenessMode = "idle" | "engaged" | "returning";

/** What the actor should be doing, once the hysteresis has had its say. */
export type AwarenessDirective = "engage" | "return" | "idle";

export interface AwarenessInput {
  /** Every condition for engaging, already evaluated by the profile. */
  readonly canEngage: boolean;
  /** The actor is somewhere it is not allowed to be, whatever it can see. */
  readonly homeReturnRequired: boolean;
  /** The actor has arrived where it belongs. */
  readonly atHome: boolean;
}

/**
 * Acquisition and retention with hysteresis.
 *
 * A class rather than a function because the mode is lifecycle-bound state that
 * a reset has to clear — the same reason the kernel's registries are classes —
 * and because two actors of the same archetype must not share it.
 */
export class Awareness {
  private currentMode: AwarenessMode = "idle";

  get mode(): AwarenessMode {
    return this.currentMode;
  }

  step(input: AwarenessInput): AwarenessDirective {
    if (input.canEngage) {
      this.currentMode = "engaged";
      return "engage";
    }
    // Having *been* engaged is what makes losing the target a return rather
    // than an idle: the actor is somewhere it walked to on purpose.
    if (this.currentMode === "engaged" || input.homeReturnRequired) {
      this.currentMode = "returning";
    }
    if (this.currentMode === "returning" && !input.atHome) return "return";
    this.currentMode = "idle";
    return "idle";
  }

  reset(): void {
    this.currentMode = "idle";
  }
}
