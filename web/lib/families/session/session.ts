// The `session` family: what a run is, and where the next one's seed comes from.
//
// The runner had all of this inside `run-loop.ts`, welded to a scorer: a phase
// machine, a lineage rule ("draw the next run's seed from the dying run's
// stream"), and the score of a token line, in one system with one slice. The
// platformer has none of it — it models defeat as a flag on a scene and calls
// the panel directly.
//
// They are the same three facts. A run is in one of three states — waiting to
// begin, running, over — the transitions between them are the only place a
// restart may happen, and each run's seed is drawn from the previous run's
// stream so that a session is reproducible from the seed the first run was
// born with. What ends a run and what asks for another are genre questions,
// answered by predicates the host binds; the machine is not.
//
// Two things the family deliberately does *not* own. It does not own the
// score: a scorer is a different family with a different slice, and the moment
// the two share one the question "what ended the run" and the question "what a
// token was worth" have one author again. And it does not own the phase
// *vocabulary*: the runner says intro/running/dead and a platformer says
// something else, so the names are the genre's and only the roles are shared.

import type { Rng } from "@/lib/kernel/rng";
import type { GameSystem, ResetScope } from "@/lib/kernel/systems";

/** The three roles a genre's own phase names are bound to. */
export interface SessionPhases<P extends string> {
  /** Held before the run begins — the runner's cut-in, a title card. */
  readonly starting: P;
  readonly running: P;
  /** Over, and waiting to be asked for another. */
  readonly ended: P;
}

export interface SessionState<P extends string, R extends string = string> {
  phase: P;
  /** The seed this run was born from. */
  seed: number;
  /**
   * Which run of this session this is; zero for the first.
   *
   * The lineage made visible. A report that says "run 3 of seed 0x5eed1234"
   * names a run exactly, which a bare seed cannot once a session has
   * restarted — every run after the first has a seed nobody typed.
   */
  runIndex: number;
  /** What ended the run, in the genre's own vocabulary; null while it runs. */
  endedBy: R | null;
}

/** Draw the next run's seed from the current run's stream. */
export function nextSessionSeed(rng: Rng): number {
  return Math.floor(rng() * 0x100000000) >>> 0;
}

export interface SessionBinding<W, P extends string, R extends string> {
  /** Where the session lives on this world. */
  readonly slice: keyof W & string;
  /** This genre's names for the three roles. */
  readonly phases: SessionPhases<P>;
  readonly id?: string;
  readonly contractVersion?: string;
  readonly reads?: readonly (keyof W & string)[];
  readonly writes?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
  readonly emits?: readonly string[];
  readonly consumes?: readonly string[];
  readonly consumesDeferred?: readonly string[];
  /** True on the frame the held start lets go. */
  begins(world: W): boolean;
  /** Why the run ended this frame, or null. */
  ended(world: W): R | null;
  /** True while another run is being asked for. */
  restarts(world: W): boolean;
  /** The stream the next seed is drawn from. */
  stream(world: W): Rng;
  /** Say so, in the genre's own occurrences. Optional: a genre may say nothing. */
  onStarted?(world: W): void;
  onEnded?(world: W, cause: R): void;
  /** The restart was asked for; the composition's own reset performs it. */
  onRestartAsked?(world: W, seed: number): void;
  /**
   * Perform the restart here, on the frame it is asked for, instead of leaving
   * it to the composition's reset.
   *
   * Two genres, two shapes. A runner restarts by resetting the whole
   * composition — eleven slices, an emptied queue, a frame boundary — so the
   * ask is an occurrence and the reset is the composition's. A genre whose
   * "restart" is a map entry has no composition to reset: the world is rebuilt
   * by the same transition a portal uses, at the end of the frame, and the
   * session simply goes back to running. Saying which of the two a binding is
   * beats pretending the second one is the first.
   */
  readonly restartsInPlace?: boolean;
  /** Rebuild the run. Called by the composition's reset, never mid-tick. */
  restart(world: W, seed: number, scope: ResetScope): void;
}

export const SESSION_SYSTEM_ID = "session/run";

/**
 * The lifecycle system: three states, and the one place a seed is drawn.
 *
 * The restart is asked for here and performed by the composition, which is the
 * shape step 1 established: this system emits the genre's restart occurrence,
 * the composition names it in `resetOn`, the frame finishes, and the reset runs
 * as a declared frame boundary rather than eleven slices rewritten mid-tick
 * under the systems still to run.
 */
export function createSessionSystem<W extends object, P extends string, R extends string>(
  binding: SessionBinding<W, P, R>,
): GameSystem<W, never> {
  const { slice, phases } = binding;
  // The seed the next run starts from, drawn from the dying run's stream at
  // the moment the restart is asked for. Held here rather than on the world
  // because it belongs to no run: between the ask and the reset there is none.
  let pendingSeed: number | null = null;
  const state = (world: W): SessionState<P, R> =>
    (world as Record<string, unknown>)[slice] as SessionState<P, R>;
  return {
    id: binding.id ?? SESSION_SYSTEM_ID,
    contractVersion: binding.contractVersion ?? "session-system-v1",
    reads: binding.reads ?? [],
    writes: binding.writes ?? [],
    owns: [slice],
    ...(binding.emits ? { emits: binding.emits as never } : {}),
    ...(binding.consumes ? { consumes: binding.consumes as never } : {}),
    ...(binding.consumesDeferred ? { consumesDeferred: binding.consumesDeferred as never } : {}),
    ...(binding.after ? { after: binding.after } : {}),
    update(world) {
      const session = state(world);
      if (session.phase === phases.starting) {
        if (binding.begins(world)) {
          session.phase = phases.running;
          binding.onStarted?.(world);
        }
        return;
      }
      if (session.phase === phases.running) {
        const cause = binding.ended(world);
        if (cause !== null) {
          session.phase = phases.ended;
          session.endedBy = cause;
          binding.onEnded?.(world, cause);
        }
        return;
      }
      // Over. The next request starts another run, from a seed this run's own
      // stream produced — deterministic given the seed the session began with,
      // and different from the run just played.
      if (!binding.restarts(world)) return;
      const seed = nextSessionSeed(binding.stream(world));
      binding.onRestartAsked?.(world, seed);
      if (!binding.restartsInPlace) {
        pendingSeed = seed;
        return;
      }
      const runIndex = session.runIndex + 1;
      binding.restart(world, seed, "run");
      const restarted = state(world);
      restarted.phase = phases.running;
      restarted.seed = seed;
      restarted.runIndex = runIndex;
      restarted.endedBy = null;
    },
    reset(world, scope) {
      const session = state(world);
      const seed = pendingSeed ?? nextSessionSeed(binding.stream(world));
      pendingSeed = null;
      const runIndex = scope === "session" ? 0 : session.runIndex + 1;
      binding.restart(world, seed, scope);
      const after = state(world);
      after.seed = seed;
      after.runIndex = runIndex;
      after.endedBy = null;
    },
  };
}
