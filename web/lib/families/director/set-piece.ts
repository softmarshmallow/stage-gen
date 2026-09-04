// The `director` family: a set-piece, as trigger, phase, outcome and swaps.
//
// The framing example this whole plan opens with lands here. Bellweather
// authors `[[boss_encounters]] page_eater_gate` at the `castle_gate` anchor, on
// `chronicle_unbound`, with `respawn_policy = "quest_reset_only"`. Iron Petal
// authors `[encounter] barrage_boss_v1` over an arena chunk with thrust
// locomotion. The naive ruling is a `boss` family, and it is wrong because
// everything "boss" already has a home: huge is `[scale.ranks]`, high HP is a
// `vitals` gauge, attacks-you is `combat` and `projectiles`, how-it-fights is
// an `actor-ai` profile. What neither game has is the thing they *authored and
// the runtime dropped*: the platformer resolved its encounter to an ordinary
// mob at 91% of the map and threw the anchor, the track and the respawn policy
// away.
//
// So the family is the set-piece and not the monster. Four things, and a genre
// answers each of them with its own vocabulary:
//
//   - the TRIGGER: a datum in the caller's own units, reached by a body. The
//     runner arms at a column ahead on the track; the platformer arms at a map
//     anchor's x. Both are "has this body got there yet".
//   - the PHASE: a name and the time it was entered. The phase *vocabulary* is
//     the genre's, because "arena_pending" is a fact about a streamed track and
//     nothing else has one.
//   - the OUTCOME: what the set-piece ended as. Also a genre vocabulary —
//     `defeated`/`exhausted` against `won`/`left`.
//   - the SWAPS: what the set-piece changes about the run while it is on, and
//     puts back when it is over. Locomotion in one genre, the soundtrack pool
//     in the other, and the whole point is that neither has to remember to put
//     it back by hand.

/** Where a set-piece is, and what it ended as. The names are the genre's. */
export interface DirectorPhaseState<Phase extends string, Outcome extends string> {
  phase: Phase;
  /** Simulation time the phase was entered on, or null before the first tick of it. */
  phaseStartedAt: number | null;
  outcome: Outcome | null;
}

/** Enter a phase, stamping when. One line, and it is the one both genres wrote by hand. */
export function enterPhase<Phase extends string, Outcome extends string>(
  state: DirectorPhaseState<Phase, Outcome>,
  phase: Phase,
  now: number,
): void {
  state.phase = phase;
  state.phaseStartedAt = now;
}

/**
 * How long the current phase has been running, or null before its first tick.
 *
 * Both genres pace something off this and both computed it inline.
 */
export function phaseElapsed<Phase extends string, Outcome extends string>(
  state: DirectorPhaseState<Phase, Outcome>,
  now: number,
): number | null {
  return state.phaseStartedAt === null ? null : now - state.phaseStartedAt;
}

/**
 * A set-piece armed at a datum, fired when a body reaches it.
 *
 * Units are the caller's and the family never learns them: a column on an
 * endless track and a pixel x on an authored map are the same statement about
 * one axis. What is *not* a parameter is the direction — a set-piece is reached
 * by advancing — because both genres advance and a trigger that could fire
 * backwards would fire on the way out of an arena as well as into it.
 */
export interface SpatialTrigger {
  readonly at: number;
}

export function armAt(at: number): SpatialTrigger {
  if (!Number.isFinite(at)) throw new Error("a set-piece must be armed at a finite datum");
  return Object.freeze({ at });
}

export function triggerReached(trigger: SpatialTrigger, position: number): boolean {
  return position >= trigger.at;
}

/**
 * Whether a set-piece comes back.
 *
 * `recurring` is the runner's endless track: the fight is a rhythm and the next
 * one is armed an interval further on. `once` is the platformer's authored
 * `respawn_policy = "quest_reset_only"` — a gate is a place in a story, and the
 * story does not un-happen because the player walked back through the map.
 */
export type DirectorRecurrence = "recurring" | "once";
