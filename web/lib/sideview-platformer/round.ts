// The platformer's binding of `score`, `timers`, `session` and the `hud` port:
// the four systems a timed round is, and nothing else.
//
// Every one of them is quiet for the two packages that ship today, and quiet in
// rule 6's sense rather than absent: the systems are in the roster, their
// parameters are empty, and each returns at its first line. Bellweather authors
// no `[score]` and no `[timers]`, so its score has no awards, its countdown has
// no entries, its session never ends and its readout draws nothing — and the two
// replay goldens are byte-identical across the addition, which is the strongest
// available statement that "a family with no block runs quiet" is a rule the
// code keeps rather than a sentence in a document.
//
// Three things worth writing down here rather than in a commit message.
//
// **The score reads the transcript.** This genre has no event queue: what a
// frame did is the scene's `GameplayTranscriptEvent` list, which is the record
// the replay golden already hashes. So the scorer declares a read of
// `transcript` and the sealer puts it after every system that writes one — the
// controller, the shot pool, the collector, the gate and the waves — which is
// exactly the position "score the frame once everything that could score has
// happened" needs, derived rather than typed out.
//
// **The session is finally instantiated here.** Step 3 extracted the `session`
// family and deliberately did NOT seal it into this genre, because the
// platformer's defeat is buried mid-way through `updatePlayer` and every
// arrangement that pulls it out moves frames the golden could not observe. That
// is still true and this does not touch it: the defeat stays where it is. What
// this session owns is the *round*, whose end is a countdown reaching zero —
// a lifecycle the genre did not have at all, so there is nothing to move.
//
// **The readout takes the family's port.** Step 6 recorded, as a scope
// statement, that none of the platformer's four readouts could: "this genre has
// no world to hand one — the scene still holds the state". The score and the
// countdown are the first two slices of this genre's world that are real
// storage rather than a name, so the first `HudReadout<PlatformerFrameWorld>`
// in this genre is here, over them.

import {
  createScoreSystem,
  scoreIsShown,
  scoreParamsFromBlock,
  type ScoreParams,
} from "@/lib/families/score";
import {
  createTimersSystem,
  shownTimer,
  timerParamsFromBlock,
  type TimerParams,
  type TimersState,
} from "@/lib/families/timers";
import { createSessionSystem, type SessionPhases } from "@/lib/families/session/session";
import { silentReadout, type HudReadout } from "@/lib/families/hud";
import { parseScoreBlock } from "@/lib/families/score";
import { parseTimersBlock } from "@/lib/families/timers";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { PreparedRuntimeManifest, ScoreEvent } from "@/lib/manifest/prepared-manifest";
import type { PlatformerFrameSteps, PlatformerFrameSystem, PlatformerFrameWorld } from "./frame-roster";

/**
 * The two blocks a round is authored in, both of them the families' own and
 * both optional.
 *
 * Optional in the strong sense the gate already supports: a package that
 * publishes no entry for them is not refused, it is a package with no round.
 * A package that publishes one at a version this build does not read is refused
 * by name, from the family that could not go on.
 */
export const PLATFORMER_SCORE_BLOCK = Object.freeze({
  block: "score",
  version: PREPARED_RUNTIME_BLOCKS.score,
  optional: true,
});

export const PLATFORMER_TIMERS_BLOCK = Object.freeze({
  block: "timers",
  version: PREPARED_RUNTIME_BLOCKS.timers,
  optional: true,
});

/** Gate the score block. Refuses by naming `score`. */
export function parsePlatformerScoreBlock(blocks: BlockTable) {
  return parseScoreBlock(blocks, PLATFORMER_SCORE_BLOCK);
}

/** Gate the timers block. Refuses by naming `timers`. */
export function parsePlatformerTimersBlock(blocks: BlockTable) {
  return parseTimersBlock(blocks, PLATFORMER_TIMERS_BLOCK);
}

/** This genre's phase vocabulary for a round. Three roles, three names. */
export const PLATFORMER_SESSION_PHASES: SessionPhases<PlatformerRoundPhase> = Object.freeze({
  starting: "starting",
  running: "running",
  ended: "ended",
});

export type PlatformerRoundPhase = "starting" | "running" | "ended";

/**
 * What ended a round, in this genre's own vocabulary.
 *
 * One member, because one thing can end a round: a countdown reached zero. A
 * defeat does not — this genre answers a defeat with a prompt and a respawn,
 * which is `checkpoints`, and a round that ended every time the player died
 * would be a different game.
 */
export type PlatformerRoundEnd = "timer";

/** Everything a round is parameterized by, read out of the package once. */
export interface RoundParams {
  /** The authored award table, or null for a package that authors no score. */
  readonly score: ScoreParams<ScoreEvent> | null;
  /** Whether the total is drawn. */
  readonly scoreShown: boolean;
  /** The authored countdowns; empty for a package that authors none. */
  readonly timers: readonly TimerParams[];
}

export const NO_ROUND: RoundParams = Object.freeze({
  score: null,
  scoreShown: false,
  timers: Object.freeze([]),
});

/**
 * Read the two optional blocks as one round.
 *
 * The chain is null and that is a ruling rather than an omission: the authored
 * vocabulary has no word for a chain, and a multiplier this genre invented on
 * the package's behalf would be a rule the author could neither see nor turn
 * off. The runner keeps its chain because the runner's chain is the runner's.
 */
export function platformerRoundParams(manifest: PreparedRuntimeManifest): RoundParams {
  return Object.freeze({
    score: scoreParamsFromBlock(manifest.score),
    scoreShown: scoreIsShown(manifest.score),
    timers: timerParamsFromBlock(manifest.timers),
  });
}

/**
 * Whether this package authored a round at all.
 *
 * Asked by content and not by identity: `platformerRoundParams` builds a fresh
 * record every time, so `params === NO_ROUND` is false for a package that
 * authored nothing, and a scene that asked that question would publish a round
 * for a game that has none. Which is exactly the defect this predicate was
 * written to fix, caught by the two shipped goldens moving.
 */
export function hasRound(params: RoundParams): boolean {
  return params.score !== null || params.timers.length > 0;
}

/** What a round readout is handed. Slices, never the world — the family's rule. */
export interface RoundReadout {
  /** The score total, or null when the package draws none. */
  readonly total: number | null;
  /** Milliseconds left on the drawn countdown, or null when there is none. */
  readonly remainingMs: number | null;
  readonly phase: PlatformerRoundPhase;
}

/** The clock a readout shows, as minutes and seconds, rounded up while it runs. */
export function formatRoundClock(remainingMs: number): string {
  const seconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

/** The score a readout shows. */
export function formatRoundScore(total: number): string {
  return `✦ ${Math.max(0, Math.floor(total))}`;
}

/** What the readout is handed this frame, or null when there is nothing to draw. */
export function roundReadout(
  world: PlatformerFrameWorld,
  params: RoundParams,
): RoundReadout | null {
  if (!hasRound(params)) return null;
  const shown = shownTimer(world.timers, params.timers);
  return Object.freeze({
    total: params.scoreShown ? world.score.total : null,
    remainingMs: shown === null ? null : shown.remainingMs,
    phase: world.session.phase,
  });
}

/**
 * The scorer, over the four occurrences the authored vocabulary names.
 *
 * `boss_defeated` is the gate's outcome rather than the creature's death,
 * because a set-piece is what makes a boss a boss: the same creature standing
 * on the road outside a gate is a mob, and the transcript says which it was.
 */
export function createPlatformerScoreSystem(
  steps: PlatformerFrameSteps,
  params: RoundParams,
): PlatformerFrameSystem {
  return createScoreSystem<PlatformerFrameWorld, ScoreEvent>({
    slice: "score",
    params: params.score ?? { awards: {}, chain: null },
    // `transcript` is this frame's record of what happened, and every system
    // that could score writes one; the sealer is what puts this last among
    // them. `hold` because a held frame scores nothing.
    reads: ["hold", "transcript", "session"],
    scoring: (world) =>
      params.score !== null && !world.hold && world.session.phase === "running",
    counts: () => steps.scoredThisFrame(),
    onChanged: (_world, award, state) => steps.scoreChanged(award.delta, state.total),
  });
}

/** The countdown, on the simulation clock rather than the frame clock. */
export function createPlatformerTimersSystem(params: RoundParams): PlatformerFrameSystem {
  return createTimersSystem<PlatformerFrameWorld>({
    slice: "timers",
    params: params.timers,
    // The clock family's answer, which is zero under a conversation or a blow —
    // so a hold stops the clock the player is racing rather than burning it.
    reads: ["clock", "hold"],
    simulationDt: (world) => world.clock.simulationDt,
    counting: (world) => world.session.phase === "running",
  });
}

/**
 * The round's lifecycle: running until a countdown reaches zero.
 *
 * `begins` is unconditional because a round has no held start here — the map is
 * already up by the time the frame ticks — and `restarts` is never asked for,
 * because answering a finished round is `checkpoints`' business and not this
 * one's. The restart is performed in place and does nothing, which is the
 * honest form of "this genre has no composition to reset".
 */
export function createPlatformerSessionSystem(steps: PlatformerFrameSteps): PlatformerFrameSystem {
  return createSessionSystem<PlatformerFrameWorld, PlatformerRoundPhase, PlatformerRoundEnd>({
    slice: "session",
    phases: PLATFORMER_SESSION_PHASES,
    reads: ["timers"],
    writes: ["transcript"],
    begins: () => true,
    ended: (world) =>
      world.timers.entries.some((entry) => entry.expired) ? "timer" : null,
    restarts: () => false,
    restartsInPlace: true,
    stream: () => () => 0,
    restart: () => {},
    onEnded: (_world, cause) => steps.roundEnded(cause),
  });
}

/**
 * The readout, and it is the first `HudReadout` this genre instantiates.
 *
 * A readout owns no slice, so the system declares reads and no writes at all,
 * and the port ships a silent implementation the family already provides — a
 * package that draws nothing gets `silentReadout` and the sealed order is the
 * same order.
 */
export function createPlatformerRoundHudSystem(
  params: RoundParams,
  view: HudReadout<RoundReadout> = silentReadout<RoundReadout>(),
): PlatformerFrameSystem {
  return {
    id: "hud/round",
    contractVersion: "hud-system-v1",
    reads: ["score", "timers", "session"],
    writes: [],
    update(world) {
      const readout = roundReadout(world, params);
      if (readout === null) {
        view.hide?.();
        return;
      }
      view.sync(readout);
    },
  };
}
