// RunnerWorld: the one mutable state every system reads and writes.
//
// The world is data, the systems are behavior, and the seed is identity: a
// world created from the same manifest and seed streams the same chunks and
// scores the same run, which is what makes a report about a run repeatable.
// The generator is the kernel's — mulberry32, tiny and deterministic, and
// good enough for chunk selection, which is the only random decision the
// runner makes. It used to be declared here as well as in
// `encounter-arithmetic.ts`, two byte-identical copies of one guarantee.

import type {
  RunnerRuntimeManifest,
  RunnerChunk,
  RunnerConsequences,
  RunnerMotionState,
} from "./contract";
import { beginFxMoment, type FxState } from "@/lib/families/screen-fx/moment-system";
import type { FxMoment } from "@/lib/manifest/fx";
import { createClock, type ClockState } from "@/lib/families/clock/clock";
import type { SessionState } from "@/lib/families/session/session";
import { createEventQueue, type EventQueue } from "@/lib/kernel/events";
import { createGauge } from "@/lib/kernel/gauge";
import { mulberry32, type Rng } from "@/lib/kernel/rng";
import { cameraScrollX } from "./camera";
import type { RunnerEvent, VitalsState } from "./vitals";
import type { DifficultyState } from "./difficulty";
import { rampProfile, type RampProfileName } from "./difficulty";
import {
  type EncounterConfig,
  type EncounterState,
  createEncounterState,
} from "./encounter-arithmetic";
import type { RunnerIntent } from "./intent";
import { createScoreState, type ScoreState } from "./score";
import { NEUTRAL_RUNNER_INTENT } from "./intent";
import {
  createSegmentStream,
  streamAhead,
  type SegmentStream,
  type StreamedPickup,
} from "./segments";

/**
 * `intro` holds the simulation while a screen-FX moment plays over it; the
 * run-loop leaves it on `fx-released`. Born once per boot, never on restart.
 */
export type RunPhase = "intro" | "running" | "dead";

/**
 * Why the run ended, when it has.
 *
 * The same three names the authored contract answers separately, so what a
 * package chose and what actually happened are stated in one vocabulary.
 * `crush` was called `step` while it was only ever a way to die; now that a
 * package can forgive it, it is worth a name a reader recognises.
 */
export type DeathCause = "hazard" | "pit" | "crush" | "shot";

/**
 * Which physics the avatar integrates.
 *
 * A locomotion is the whole map from intent to vertical motion, not a
 * modifier on running: `thrust` has no jump edge, no slide and no arc, and
 * `run` has no held climb. The encounter director owns the switch; the avatar
 * feedback-reads it.
 */
export type RunnerLocomotion = "run" | "thrust";

export interface AvatarState {
  /** Forward progress of the avatar's feet, in world columns. */
  distanceColumns: number;
  /** Feet altitude in occupancy-row units; larger is lower, like row indices. */
  y: number;
  /** Vertical speed in rows per second; positive is downward. */
  vy: number;
  grounded: boolean;
  /** Air jumps spent since the last grounding; the profile caps them. */
  airJumpsUsed: number;
  /** Held low while grounded and the duck profile allows it. */
  sliding: boolean;
  /** Total jump launches this run - the presentation replays the strip on the
   * impulse, not the state change, so a second hop re-animates. */
  jumpImpulses: number;
  motion: RunnerMotionState;
}

export interface ObstaclesState {
  /** Instance keys of pickups already collected, so they never re-score. */
  collected: Set<string>;
  /** Instance keys of pickups that scrolled past uncollected: each is missed once. */
  missed: Set<string>;
  /** True while the avatar overlaps a hazard this frame. */
  hazardContact: boolean;
  /** Instance keys of hazards already struck, so one prop costs one point. */
  struck: Set<string>;
  /** Pickups first collected this frame, for scoring and despawn effects. */
  collectedThisFrame: StreamedPickup[];
  /** Pickups newly missed this frame; the run-loop breaks the chain on them. */
  missedThisFrame: number;
}

/**
 * The session: phase, seed lineage, and what ended the run.
 *
 * The `score`, `chain` and `multiplier` that used to sit here left with the
 * scorer. "What ended the run" and "what a token was worth" are two questions
 * and they had one author; now the lifecycle owns this slice and `score/run`
 * owns its own.
 */
export interface RunState extends SessionState<RunPhase, DeathCause> {
  /** This run's stream: chunk selection, and the seed the next run is drawn from. */
  rng: Rng;
}

export interface CameraState {
  /** Horizontal world scroll in screen pixels at parallax 1. */
  scrollX: number;
}

/** The published arc arithmetic, read from the manifest rather than asserted
 * locally: the runtime flies exactly the arc admission proved. */
export interface RunnerArithmetic {
  readonly baseSpeedColumnsPerSecond: number;
  /** The multiplier every spacing proof was run at; the ramp never exceeds it. */
  readonly maxSpeedMultiplier: number;
  readonly jumpPeakMarginTiles: number;
  readonly airtimeHeadroom: number;
  readonly avatarHalfWidthColumns: number;
  readonly hazardColumnInset: number;
}

/** Everything static a system needs, derived once from the manifest. */
export interface RunnerWorldConfig {
  readonly rows: number;
  readonly walkSurfaceRow: number;
  readonly tilePx: number;
  readonly playerHeightTiles: number;
  readonly maxClearGapColumns: number;
  readonly maxRiseTiles: number;
  readonly jumpProfile: "single_arc_v1" | "double_arc_v1";
  readonly duckProfile: "slide_v1" | null;
  /** The slide's proved height fraction; null exactly when duckProfile is. */
  readonly duckedHeightFraction: number | null;
  /** What each way of coming to grief costs, as the package authored it. */
  readonly consequences: RunnerConsequences;
  /** The gauge's ceiling; null exactly when no consequence drains. */
  readonly maxVitalPoints: number | null;
  readonly hurtRepresentation: "blink_v1" | "drawn_v1" | null;
  readonly arithmetic: RunnerArithmetic;
  readonly rampProfile: RampProfileName;
  /** Highest difficulty actually present in this package's nonempty chunk catalog. */
  readonly maxAuthoredDifficulty: number;
  readonly chunks: readonly RunnerChunk[];
  /** Declared prop magnitudes in player-height units, for hazard collision boxes. */
  readonly propHeightUnits: ReadonlyMap<string, number>;
  /** How far past the avatar the stream keeps track, in columns. */
  readonly streamAheadColumns: number;
  /** How far behind the avatar passed chunks are retained, in columns. */
  readonly keepBehindColumns: number;
  /** Screen x the avatar is pinned to, in pixels. */
  readonly avatarScreenX: number;
  /** The stage-start binding the package plays before the run, if any. */
  readonly introMoment: FxMoment | null;
  /** The boss-arrival binding, if the package binds one. */
  readonly encounterMoment: FxMoment | null;
  /** The published encounter arithmetic; null when the package fights nothing. */
  readonly encounter: EncounterConfig | null;
  /**
   * The arena chunk an encounter is fought over, held out of `chunks`.
   *
   * Separated so the difficulty selector cannot draw it: the arena is not a
   * harder or easier chunk, it is a chunk for a different purpose, and the
   * band it would fall into would be a lie either way.
   */
  readonly arenaChunk: RunnerChunk | null;
  /** Viewport width in columns, for placing a boss off the right edge. */
  readonly viewportColumns: number;
}

export interface RunnerWorld {
  /**
   * The simulation clock: this frame's delta and its integral.
   *
   * Owned by the `clock` family. Every integrator reads `simulationDt` rather
   * than `step.dt`, and everything that stamps a deadline reads
   * `simulationNow` rather than `step.now`, so a moment holding the simulation
   * stops both instead of stopping the first and burning through the second.
   */
  clock: ClockState;
  intent: RunnerIntent;
  difficulty: DifficultyState;
  avatar: AvatarState;
  segments: SegmentStream;
  obstacles: ObstaclesState;
  vitals: VitalsState;
  run: RunState;
  /** The scorekeeper's slice; one author, and not the lifecycle's. */
  score: ScoreState;
  camera: CameraState;
  /** The screen-FX moment in flight, driven by the generic fx system; null when none. */
  fx: FxState | null;
  /** Which physics the avatar is wearing this frame. */
  locomotion: RunnerLocomotion;
  /** The boss-encounter director's slice; null exactly when none is authored. */
  encounter: EncounterState | null;
  /** This frame's occurrences. Cleared by the sealed tick, not by any system. */
  readonly events: EventQueue<RunnerEvent>;
  readonly config: RunnerWorldConfig;
}

/** Fixed design-space viewport shared by every runner boot. */
export const RUNNER_VIEW_WIDTH = 1280;
export const RUNNER_VIEW_HEIGHT = 720;

/** Where the avatar sits on screen: a quarter in, so the run reads forward. */
export const AVATAR_SCREEN_ANCHOR_FRACTION = 0.25;

const STREAM_MARGIN_COLUMNS = 8;

/**
 * What the manifest cannot yet tell the world about an encounter.
 *
 * Injected rather than derived here so the world's shape does not depend on
 * the order the parser and the director were built in: the boot resolves the
 * published block once and hands it over, and everything downstream - the
 * avatar's physics, the segment stream, the director - is testable from a
 * hand-built config with no manifest at all.
 */
export interface RunnerEncounterBinding {
  readonly encounter: EncounterConfig;
  readonly arenaChunk: RunnerChunk;
  readonly moment: FxMoment | null;
}

export function runnerWorldConfig(
  manifest: RunnerRuntimeManifest,
  binding: RunnerEncounterBinding | null = null,
): RunnerWorldConfig {
  const viewportColumns = Math.ceil(RUNNER_VIEW_WIDTH / manifest.scale.tilePx);
  const arenaSegmentId = binding?.arenaChunk.segmentId ?? null;
  const runChunks = manifest.segments.chunks.filter(
    (chunk) => chunk.segmentId !== arenaSegmentId,
  );
  return Object.freeze({
    rows: manifest.segments.rows,
    walkSurfaceRow: manifest.segments.walkSurfaceRow,
    tilePx: manifest.scale.tilePx,
    playerHeightTiles: manifest.scale.playerHeightTiles,
    maxClearGapColumns: manifest.gameplay.maxClearGapColumns,
    maxRiseTiles: manifest.gameplay.maxRiseTiles,
    jumpProfile: manifest.gameplay.jumpProfile,
    duckProfile: manifest.gameplay.duckProfile,
    duckedHeightFraction: manifest.gameplay.duckedHeightFraction,
    consequences: manifest.gameplay.consequences,
    maxVitalPoints: manifest.gameplay.vitals?.maxPoints ?? null,
    hurtRepresentation: manifest.gameplay.vitals?.hurtRepresentation ?? null,
    arithmetic: Object.freeze({
      baseSpeedColumnsPerSecond: manifest.gameplay.baseSpeedColumnsPerSecond,
      maxSpeedMultiplier: manifest.gameplay.maxSpeedMultiplier,
      jumpPeakMarginTiles: manifest.gameplay.jumpPeakMarginTiles,
      airtimeHeadroom: manifest.gameplay.airtimeHeadroom,
      avatarHalfWidthColumns: manifest.gameplay.avatarHalfWidthColumns,
      hazardColumnInset: manifest.gameplay.hazardColumnInset,
    }),
    rampProfile: manifest.gameplay.rampProfile,
    maxAuthoredDifficulty: Math.max(...runChunks.map((chunk) => chunk.difficulty)),
    chunks: runChunks,
    propHeightUnits: new Map(
      manifest.props.map((prop) => [prop.id, prop.calibration.heightUnits]),
    ),
    streamAheadColumns: viewportColumns + STREAM_MARGIN_COLUMNS,
    keepBehindColumns: STREAM_MARGIN_COLUMNS,
    avatarScreenX: Math.round(RUNNER_VIEW_WIDTH * AVATAR_SCREEN_ANCHOR_FRACTION),
    introMoment:
      manifest.fx?.moments.find((entry) => entry.moment === "stage_start") ?? null,
    encounterMoment: binding?.moment ?? null,
    encounter: binding?.encounter ?? null,
    arenaChunk: binding?.arenaChunk ?? null,
    viewportColumns,
  });
}

/**
 * Screen y of a world row edge under `floor_to_screen_bottom`: the bottom of
 * the deepest authored row meets the bottom of the canvas, so the ground can
 * never reveal a gap beneath the world.
 */
export function rowToScreenY(row: number, config: RunnerWorldConfig): number {
  return RUNNER_VIEW_HEIGHT - (config.rows - row) * config.tilePx;
}

/** Screen y of the shared walk datum: the top of the seam-column ground stack. */
export function groundLineY(config: RunnerWorldConfig): number {
  return rowToScreenY(config.walkSurfaceRow, config);
}

/**
 * Horizontal world scroll that pins the avatar to its screen anchor.
 *
 * Re-exported from the `camera` family's binding, where the arithmetic and the
 * system that writes it now live. Kept here because the world is where the
 * slice is initialised and reset, and both of those are camera positions
 * rather than camera frames.
 */
export { cameraScrollX };

/**
 * Reset every dynamic half of the world in place for a new run under `seed`.
 *
 * In place rather than by replacement because the sealed systems and the
 * renderer hold the world object itself; a fresh object would strand them on
 * a dead one. The initial window is primed here so the avatar's feedback read
 * of the stream is valid from the very first tick.
 */
export function resetRunnerWorld(
  world: RunnerWorld,
  seed: number,
  options: { readonly intro?: boolean } = {},
): void {
  const rng = mulberry32(seed);
  // The intro plays once per boot: a restart after a death goes straight to
  // running, because a two-second overlay on every death is the wrong feel
  // for a runner. The boot passes `intro: true`; the run-loop passes false.
  const intro = (options.intro ?? false) && world.config.introMoment !== null;
  world.intent = NEUTRAL_RUNNER_INTENT;
  world.difficulty = {
    ceiling: 1,
    floor: 1,
    speedMultiplier: 1,
    speedColumnsPerSecond: world.config.arithmetic.baseSpeedColumnsPerSecond,
  };
  world.avatar = {
    distanceColumns: 2,
    y: world.config.walkSurfaceRow,
    vy: 0,
    grounded: true,
    airJumpsUsed: 0,
    sliding: false,
    jumpImpulses: 0,
    motion: "run",
  };
  world.segments = createSegmentStream(world.config.rows, world.config.walkSurfaceRow);
  world.obstacles = {
    collected: new Set(),
    missed: new Set(),
    hazardContact: false,
    struck: new Set(),
    collectedThisFrame: [],
    missedThisFrame: 0,
  };
  world.vitals = {
    gauge: world.config.maxVitalPoints === null ? null : createGauge(world.config.maxVitalPoints),
    clockMs: 0,
    pendingRecovery: null,
    hurtThisFrame: false,
    depletedThisFrame: false,
  };
  world.run = {
    phase: intro ? "intro" : "running",
    seed,
    // Overwritten by the session's own reset, which knows whether this is the
    // next run of a session or the first of a new one; the boot's first world
    // is run zero.
    runIndex: world.run?.runIndex ?? 0,
    rng,
    endedBy: null,
  };
  world.fx = null;
  world.locomotion = "run";
  world.encounter =
    world.config.encounter === null ? null : createEncounterState(world.config.encounter);
  if (intro && world.config.introMoment !== null) {
    beginFxMoment(world, world.config.introMoment.moment, world.config.introMoment.choreography);
  }
  world.camera = { scrollX: cameraScrollX(world.avatar.distanceColumns, world.config) };
  streamAhead(
    world.segments,
    world.config.chunks,
    { ceiling: world.difficulty.ceiling, floor: world.difficulty.floor },
    rng,
    Math.ceil(world.avatar.distanceColumns) + world.config.streamAheadColumns,
  );
}

export function createRunnerWorld(
  manifest: RunnerRuntimeManifest,
  seed: number,
  options: {
    readonly intro?: boolean;
    readonly encounter?: RunnerEncounterBinding | null;
  } = { intro: true },
): RunnerWorld {
  const config = runnerWorldConfig(manifest, options.encounter ?? null);
  // The reset fills every dynamic field; the placeholders exist only to give
  // it a complete object to work on.
  const world: RunnerWorld = {
    // Built here and never rebuilt: the clock belongs to the session, and a
    // restart inside one does not rewind it. `resetRunnerWorld` leaves it
    // alone for that reason, and the clock system's own `reset` decides what a
    // session start means.
    clock: createClock(),
    intent: NEUTRAL_RUNNER_INTENT,
    difficulty: {
      ceiling: 1,
      floor: 1,
      speedMultiplier: 1,
      speedColumnsPerSecond: config.arithmetic.baseSpeedColumnsPerSecond,
    },
    avatar: {
      distanceColumns: 0,
      y: 0,
      vy: 0,
      grounded: true,
      airJumpsUsed: 0,
      sliding: false,
      jumpImpulses: 0,
      motion: "run",
    },
    segments: createSegmentStream(config.rows, config.walkSurfaceRow),
    obstacles: {
      collected: new Set(),
      missed: new Set(),
      hazardContact: false,
      struck: new Set(),
      collectedThisFrame: [],
      missedThisFrame: 0,
    },
    vitals: {
      gauge: null,
      clockMs: 0,
      pendingRecovery: null,
      hurtThisFrame: false,
      depletedThisFrame: false,
    },
    run: {
      phase: "running",
      seed,
      runIndex: 0,
      rng: mulberry32(seed),
      endedBy: null,
    },
    // Reset by `score/run`, which owns it; `resetRunnerWorld` leaves it alone
    // so that the slice has exactly one author on a restart as well as on a
    // tick.
    score: createScoreState(),
    camera: { scrollX: 0 },
    fx: null,
    locomotion: "run",
    encounter: null,
    events: createEventQueue<RunnerEvent>(),
    config,
  };
  resetRunnerWorld(world, seed, options);
  // Sanity-check the ramp profile eagerly so a bad name fails at boot.
  rampProfile(config.rampProfile);
  return world;
}
