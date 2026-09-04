// The runner's binding of the `session` family: what a run is here.
//
// This file is what is left of `run-loop.ts` once the scorer moved out. The
// three roles are bound to this genre's own phase names — a run waits in
// `intro` while the stage's moment plays, `running` is running, and `dead` is
// over and waiting to be asked for another — and the four predicates are the
// only genre knowledge the machine needs: what lets the start go, what ended
// the run, what asks for the next one, and which stream the next seed comes
// from.
//
// The restart is asked for, never performed here. This binding emits
// `run-restarted`; the composition names that occurrence in `resetOn`, lets
// the frame finish, and then runs the reset. It used to rewrite eleven slices
// in the middle of its own update, with six systems still to run on a world
// that had just been replaced under them.

import {
  createSessionSystem,
  nextSessionSeed,
  type SessionPhases,
  type SessionState,
} from "@/lib/families/session/session";
import { parseSessionBlock, type SessionBlockView } from "@/lib/families/session/manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { GameSystem } from "@/lib/kernel/systems";
import { RUNNER_BLOCKS, type RunnerDamageSource } from "./contract";
import { resetRunnerWorld, type RunnerWorld, type RunPhase } from "./world";

/**
 * The block this genre's session depends on.
 *
 * The machine is code; the vocabulary `endedBy` carries is not. `hazard`,
 * `pit`, `crush` and `shot` are ways to end a run because
 * `[gameplay].consequences` answers for each of them, so `gameplay` is the
 * block, and a producer that moves it gets a refusal naming it.
 */
export const RUNNER_SESSION_BLOCK = Object.freeze({
  block: "gameplay",
  version: RUNNER_BLOCKS.gameplay,
});

/** Gate the runner's session block. Refuses by naming `gameplay`. */
export function parseRunnerSessionBlock(blocks: BlockTable): SessionBlockView {
  return parseSessionBlock(blocks, RUNNER_SESSION_BLOCK);
}

/** This genre's names for the three roles. */
export const RUNNER_SESSION_PHASES: SessionPhases<RunPhase> = Object.freeze({
  starting: "intro",
  running: "running",
  ended: "dead",
});

/** The lifecycle's own occurrence: this run is over and another was asked for. */
export type SessionEvent = {
  readonly type: "run-restarted";
  readonly seed: number;
};

/** Draw the next run's seed from the current run's RNG stream. */
export const nextRunSeed = nextSessionSeed;

export type RunnerSessionState = SessionState<RunPhase, RunnerDamageSource>;

export function createSessionSystemForRunner(): GameSystem<RunnerWorld> {
  return createSessionSystem<RunnerWorld, RunPhase, RunnerDamageSource>({
    slice: "run",
    phases: RUNNER_SESSION_PHASES,
    // `intent` is the only slice this reads, and it is read for one thing: the
    // press that asks for another run. The scorer took `obstacles` with it,
    // and the `avatar` read the old declaration carried was never performed —
    // the death pose became the avatar's own to write in step 1 and the read
    // outlived it.
    reads: ["intent"],
    emits: ["run-restarted"],
    consumes: ["run-ended", "fx-released"],
    // The frame's collections are scored under the phase they were collected
    // in. The old single system did that by scoring first and asking whether
    // the run had ended second; with two systems the same fact is an edge.
    after: ["score/run"],
    // The overlay owns the clock: the run begins the frame the rip starts
    // tearing away, which is what `fx-released` says. Only the stage's own
    // moment starts the run; a boss cut-in plays over a run already going.
    begins: (world) =>
      world.events.ofType("fx-released").some((event) => event.moment === "stage_start"),
    // This system no longer decides what a contact means; it ends runs. Which
    // occurrences are survivable is the package's answer, resolved by
    // `runner/vitals`, and what arrives here is the verdict.
    ended: (world) => world.events.ofType("run-ended")[0]?.source ?? null,
    // The edge that caused the death was consumed by its own frame, so this is
    // always a new, deliberate press.
    restarts: (world) => world.intent.action || world.intent.jump,
    stream: (world) => world.run.rng,
    onRestartAsked: (world, seed) => world.events.emit({ type: "run-restarted", seed }),
    // A session replays the boot, cut-in and all; a run picks up the seed the
    // ask drew.
    restart: (world, seed, scope) =>
      resetRunnerWorld(world, seed, { intro: scope === "session" }),
  }) as GameSystem<RunnerWorld>;
}
