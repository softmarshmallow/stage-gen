// The run lifecycle: running → dead → restart, and the one scorekeeper.
//
// This system is the single writer of the run phase, the score, and the
// pickup chain, so "what ended the run" and "what a token was worth" each
// have exactly one author. The chain is the trail's instrument: consecutive
// collected pickups earn a multiplier, and ONE missed pickup breaks it — so
// leaving the token line has a visible price, which is what makes the
// ground-token forfeiture of a jump measurable rather than invisible.
//
// A restart resets the world in place under a fresh seed drawn from the dying
// run's RNG — deterministic given the original seed, different from the run
// just played. Replaying the same seed is a deliberate act through the boot
// handle, not an input gesture.

import { resetRunnerWorld, type Rng, type RunnerWorld } from "./world";
import type { GameSystem } from "./systems";

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

/** Draw the next run's seed from the current run's RNG stream. */
export function nextRunSeed(rng: Rng): number {
  return Math.floor(rng() * 0x100000000) >>> 0;
}

export function createRunLoopSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/run-loop",
    contractVersion: "run-loop-system-v2",
    reads: ["intent", "avatar", "obstacles"],
    writes: ["run"],
    update(world) {
      const run = world.run;
      if (run.phase === "running") {
        // A miss breaks the chain before this frame's collections extend it,
        // so a frame carrying both starts the new chain at its collections.
        if (world.obstacles.missedThisFrame > 0) {
          run.chain = 0;
        }
        run.chain += world.obstacles.collectedThisFrame.length;
        run.multiplier = chainMultiplier(run.chain);
        run.score +=
          world.obstacles.collectedThisFrame.length * PICKUP_SCORE * run.multiplier;
        if (world.avatar.deathCause !== null) {
          run.phase = "dead";
          run.cause = world.avatar.deathCause;
        } else if (world.obstacles.hazardContact) {
          run.phase = "dead";
          run.cause = "hazard";
        }
        return;
      }
      // Dead: the next jump or action request starts a fresh run. The edge
      // that caused the death was consumed by its own frame, so this is
      // always a new, deliberate press.
      if (world.intent.action || world.intent.jump) {
        resetRunnerWorld(world, nextRunSeed(run.rng));
      }
    },
  };
}
