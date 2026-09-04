// Semantic state → strip, and the line availability is not allowed to cross.
//
// State selection was welded three ways: the player's if-chain, the mob's
// locomotion restart, and the scene's single-idle NPC path. They are not one
// state machine and pretending otherwise would be the `boss` family mistake in
// miniature — what a player does and what a wandering creature does are
// different rules. What they *do* share is the step after the rule: given the
// state the rules chose and what artwork actually arrived, pick the strip.
//
// That step is where the defect lives. When a controller asks "did this package
// ship a death strip?" and answers by changing what the body *does*, an art
// decision has become a game decision, and two packages of the same game play
// differently. So the rule and the substitution are separated here: a genre's
// rules choose a state knowing nothing about availability, and `selectMotion`
// then walks a declared fallback chain to something that can be drawn. A
// substitution is reported rather than hidden, so a caller that wants to know
// it happened can, and no caller has to.

export interface MotionSelection {
  /** The state the genre's rules chose, whatever is drawable. */
  readonly state: string;
  /** The state actually drawn, after the fallback chain. */
  readonly drawn: string | null;
  /** Whether the drawn state is not the chosen one. */
  readonly substituted: boolean;
}

/**
 * Choose the strip for a state, substituting only where the genre said it may.
 *
 * The chain is per state and declared up front, which is the point: a genre
 * that wants a defeated body to lie in its idle pose when no terminal strip
 * shipped says so once, in one table, instead of each site asking
 * `textures.exists` and drawing its own conclusion.
 *
 * A state with no chain and no artwork returns `drawn: null` — nothing to draw
 * is an answer, and the caller holding whatever pose it already had is the
 * right behaviour far more often than an exception is.
 */
export function selectMotion(input: Readonly<{
  state: string;
  available: (state: string) => boolean;
  fallbacks?: Readonly<Record<string, readonly string[]>>;
}>): MotionSelection {
  const chain = [input.state, ...(input.fallbacks?.[input.state] ?? [])];
  for (const candidate of chain) {
    if (input.available(candidate)) {
      return Object.freeze({
        state: input.state,
        drawn: candidate,
        substituted: candidate !== input.state,
      });
    }
  }
  return Object.freeze({ state: input.state, drawn: null, substituted: false });
}

/**
 * Whether a sustained state's animation has to be started again.
 *
 * A finite strip — an attack, a flinch — stops on its last frame and stays
 * there, so an actor returning to a sustained state has to be told to play
 * again. The rule is "the sustained animation is not the one running, or it is
 * the one running and it has stopped", and it is one rule for any actor with
 * looping states rather than a mob-specific recovery.
 */
export function motionNeedsRestart(input: Readonly<{
  /** Whether the state the actor is now in is a sustained one. */
  sustained: boolean;
  currentAnimationKey: string | null;
  sustainedAnimationKey: string;
  isPlaying: boolean;
}>): boolean {
  if (!input.sustained) return false;
  return (
    input.currentAnimationKey !== input.sustainedAnimationKey || !input.isPlaying
  );
}

/** Which way an actor's artwork was painted. */
export type MotionFacing = "left" | "right";

/**
 * Whether a sprite has to be mirrored to face where the actor is facing.
 *
 * One line, and it is here because it was written five times with the source
 * direction implicit every time. Making the painted direction a parameter is
 * what lets a package whose strips face left ship without every call site
 * inverting by hand — and what stops the next one from guessing.
 */
export function mirrorFor(facing: MotionFacing, painted: MotionFacing = "right"): boolean {
  return facing !== painted;
}
