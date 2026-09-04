// The scorekeeper, out of the run loop at last.
//
// It was in `run-loop.ts` because both were true of one system: the thing that
// decided a run was over also decided what a token was worth. They are not one
// question. "What ended the run" belongs to the lifecycle and "what a token was
// worth" belongs here, and the split is what lets a genre take one without the
// other — the cinematic platformer in the plan's target table wants the session
// and refuses the score.
//
// The chain is the trail's instrument: consecutive collected pickups earn a
// multiplier, and ONE missed pickup breaks it, so leaving the token line has a
// visible price. That is what makes the ground-token forfeiture of a jump
// measurable rather than invisible.

import type { GameSystem } from "@/lib/kernel/systems";
import type { RunnerWorld } from "./world";

/** What one collected pickup is worth before the chain multiplier. */
export const PICKUP_SCORE = 10;

/** Chain lengths at which the multiplier steps up; ×4 is the cap. */
export const CHAIN_MULTIPLIER_STEPS: readonly number[] = [5, 15, 30];

export function chainMultiplier(chain: number): number {
  let multiplier = 1;
  for (const step of CHAIN_MULTIPLIER_STEPS) {
    if (chain >= step) multiplier += 1;
  }
  return multiplier;
}

/** What defeating one boss is worth. Feel, like every other score constant. */
export const BOSS_DEFEAT_SCORE = 500;

export interface ScoreState {
  total: number;
  /** Consecutive pickups collected without a miss; the multiplier's input. */
  chain: number;
  /** Score multiplier earned by the current chain; 1 with no chain. */
  multiplier: number;
}

export function createScoreState(): ScoreState {
  return { total: 0, chain: 0, multiplier: 1 };
}

export function createScoreSystem(): GameSystem<RunnerWorld> {
  return {
    id: "score/run",
    contractVersion: "score-system-v1",
    // Feedback read of `run`, undeclared and written down here: the phase this
    // frame's collections are scored under is the phase they were collected
    // in, which is last frame's, because `session/run` decides this frame's
    // phase *after* this system has run — the explicit `after` edge on the
    // session says so. It is also what preserves the old single system's
    // behaviour exactly: it scored the frame and only then asked whether the
    // frame had ended the run.
    reads: ["obstacles"],
    writes: [],
    owns: ["score"],
    consumes: ["boss-defeated"],
    update(world) {
      if (world.run.phase !== "running") return;
      const score = world.score;
      // A miss breaks the chain before this frame's collections extend it,
      // so a frame carrying both starts the new chain at its collections.
      if (world.obstacles.missedThisFrame > 0) {
        score.chain = 0;
      }
      score.chain += world.obstacles.collectedThisFrame.length;
      score.multiplier = chainMultiplier(score.chain);
      score.total +=
        world.obstacles.collectedThisFrame.length * PICKUP_SCORE * score.multiplier;
      // A defeated boss pays a flat reward rather than one scaled by the
      // chain: the fight is not a pickup line, and a player who spent the
      // encounter dodging should not be paid less for winning it.
      score.total += world.events.ofType("boss-defeated").length * BOSS_DEFEAT_SCORE;
    },
    reset(world) {
      world.score = createScoreState();
    },
  };
}
