// The run lifecycle: running → dead → restart.
//
// This system is the single writer of the run phase and the score, so "what
// ended the run" has exactly one author. A restart resets the world in place
// under a fresh seed drawn from the dying run's RNG — deterministic given the
// original seed, different from the run just played. Replaying the same seed
// is a deliberate act through the boot handle, not an input gesture.

import { resetRunnerWorld, type Rng, type RunnerWorld } from "./world";
import type { GameSystem } from "./systems";

/** What one collected pickup is worth. Scoring is runtime-owned in v1. */
export const PICKUP_SCORE = 10;

/** Draw the next run's seed from the current run's RNG stream. */
export function nextRunSeed(rng: Rng): number {
  return Math.floor(rng() * 0x100000000) >>> 0;
}

export function createRunLoopSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/run-loop",
    contractVersion: "run-loop-system-v1",
    reads: ["intent", "avatar", "obstacles"],
    writes: ["run"],
    update(world) {
      const run = world.run;
      if (run.phase === "running") {
        run.score += world.obstacles.collectedThisFrame.length * PICKUP_SCORE;
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
