// The runner's instantiation of the `score` family: a token line with a chain.
//
// Step 3 took the scorekeeper out of the run loop because "what ended the run"
// and "what a token was worth" are two questions with two authors. This step
// takes the last thing that was only ever this genre's by accident: the
// arithmetic. `10`, `500`, the ladder at 5/15/30, "a miss breaks the chain
// before this frame's collections extend it" — none of it is about running, and
// all of it was written here because nothing else had a score.
//
// What stays here is exactly what is the runner's: which occurrences count
// (a collected pickup, a defeated boss), which of them chain (the pickup line
// and not the fight), and the numbers themselves. The numbers stay compiled in
// rather than authored, and rule 7 is why: a number belongs in the pipeline's
// table iff an offline refusal reads it, and nothing offline refuses on what a
// token is worth. A genre that *does* author one — the wave variant — is
// answered from its `[score]` block by the same family and the same system.

import {
  chainMultiplier as chainMultiplierUnder,
  createScoreState as createFamilyScoreState,
  createScoreSystem as createFamilyScoreSystem,
  type ScoreParams,
  type ScoreState,
} from "@/lib/families/score";
import type { GameSystem } from "@/lib/kernel/systems";
import type { RunnerWorld } from "./world";

/** What one collected pickup is worth before the chain multiplier. */
export const PICKUP_SCORE = 10;

/** Chain lengths at which the multiplier steps up; ×4 is the cap. */
export const CHAIN_MULTIPLIER_STEPS: readonly number[] = [5, 15, 30];

export function chainMultiplier(chain: number): number {
  return chainMultiplierUnder(chain, CHAIN_MULTIPLIER_STEPS);
}

/** What defeating one boss is worth. Feel, like every other score constant. */
export const BOSS_DEFEAT_SCORE = 500;

/** The two things this genre scores. Opaque to the family, which never learns either. */
export type RunnerScoreKind = "collected" | "boss-defeated";

/**
 * The runner's award table.
 *
 * The chain is the trail's instrument: consecutive collected pickups earn a
 * multiplier and ONE missed pickup breaks it, so leaving the token line has a
 * visible price — which is what makes the ground-token forfeiture of a jump
 * measurable rather than invisible. A defeated boss pays flat rather than
 * chained: the fight is not a pickup line, and a player who spent the encounter
 * dodging should not be paid less for winning it.
 */
export const RUNNER_SCORE_PARAMS: ScoreParams<RunnerScoreKind> = Object.freeze({
  awards: Object.freeze({ collected: PICKUP_SCORE, "boss-defeated": BOSS_DEFEAT_SCORE }),
  chain: Object.freeze({ steps: CHAIN_MULTIPLIER_STEPS, extendedBy: ["collected"] as const }),
});

export type { ScoreState };

export function createScoreState(): ScoreState {
  return createFamilyScoreState();
}

export function createScoreSystem(): GameSystem<RunnerWorld> {
  return createFamilyScoreSystem<RunnerWorld, RunnerScoreKind>({
    slice: "score",
    params: RUNNER_SCORE_PARAMS,
    // Feedback read of `run`, undeclared and written down here: the phase this
    // frame's collections are scored under is the phase they were collected
    // in, which is last frame's, because `session/run` decides this frame's
    // phase *after* this system has run — the explicit `after` edge on the
    // session says so. It is also what preserves the old single system's
    // behaviour exactly: it scored the frame and only then asked whether the
    // frame had ended the run.
    reads: ["obstacles"],
    consumes: ["boss-defeated"],
    scoring: (world) => world.run.phase === "running",
    chainBroken: (world) => world.obstacles.missedThisFrame > 0,
    counts: (world) => ({
      collected: world.obstacles.collectedThisFrame.length,
      "boss-defeated": world.events.ofType("boss-defeated").length,
    }),
  }) as GameSystem<RunnerWorld>;
}
