// The arithmetic of a boss encounter, with no Phaser and no world in it.
//
// Split from the system that owns the state for the reason the projectile
// flight was split from the pool that owns its sprites: everything an
// encounter does that can be *wrong* — where a salvo leaves its lane, whether
// the boss is at its stand-off, when a shot has left the world, how long the
// climb takes — is arithmetic, and arithmetic can be tested without a browser.
//
// Two frames of reference meet here, and confusing them is the one mistake
// this module exists to prevent. The run carries the avatar and the boss
// forward together, so an encounter is easiest to think about in the AVATAR's
// frame: the boss hovers at a fixed offset ahead, and a shot closes at its
// published speed regardless of how fast the run is going. That is also the
// frame the generator's admission proof is written in — `firing_distance /
// projectile_speed` is the honest time-to-arrival only if the speed is
// relative — so the runtime measures what admission proved. World columns are
// recovered by adding the avatar's distance, once, at draw time.
//
// Every number the generator publishes is read here; nothing is re-derived.
// The consumer's own constants at the bottom are feel — approach speed, pose
// duration, the hit flash — and no refusal reads them.

import { createGauge, type Gauge } from "@/lib/game-systems/gauge";

/** The published encounter arithmetic, camel-cased from the manifest. */
export interface EncounterConfig {
  readonly profile: string;
  readonly locomotion: string;
  readonly intervalColumns: number;
  readonly arenaSegmentId: string;
  readonly bossId: string;
  readonly bossProjectileId: string;
  readonly playerProjectileId: string;
  readonly thrust: ThrustArithmetic;
  readonly firingDistanceColumns: number;
  readonly projectileSpeedColumnsPerSecond: number;
  readonly projectileHeightRows: number;
  readonly salvoShots: number;
  readonly salvoPeriodSeconds: number;
  readonly salvoBudget: number;
  readonly laneMarginRows: number;
  readonly hitsToDefeat: number;
  readonly playerFirePeriodSeconds: number;
  readonly playerShotSpeedColumnsPerSecond: number;
  /** The boss's drawn height in rows, from its calibration and the package scale. */
  readonly bossHeightRows: number;
}

/** The locomotion half, mirrored from the SDK's `ThrustProfile`. */
export interface ThrustArithmetic {
  readonly maxClimbRowsPerSecond: number;
  readonly maxFallRowsPerSecond: number;
  readonly climbAccelerationRowsPerSecondSquared: number;
}

/**
 * Where an encounter is in its life.
 *
 * `arena_pending` is the gap between asking for the arena and standing on it:
 * the stream appends a chunk or two ahead of the camera, so the floor arrives
 * a beat after it is requested and the fight may not start before it does.
 * `cooldown` is the mirror at the end — the boss is gone but the arena the
 * fight was fought over is still under the avatar's feet.
 */
export type EncounterPhase =
  | "idle"
  | "arena_pending"
  | "cut_in"
  | "battle"
  | "retreat"
  | "cooldown";

export type BossMotionState = "hover" | "attack" | "death";

export type EncounterOutcome = "defeated" | "exhausted";

/** One shot in the air, measured in the avatar's frame. */
export interface EncounterShot {
  readonly id: number;
  readonly owner: "boss" | "player";
  /** Columns ahead of the avatar. Negative is behind. */
  x: number;
  /** Row of the shot's centre. */
  readonly row: number;
  /** Columns per second in the avatar's frame; negative closes on the avatar. */
  readonly vx: number;
  readonly halfLengthColumns: number;
  readonly halfHeightRows: number;
}

export interface BossState {
  /** Columns ahead of the avatar. */
  offsetColumns: number;
  /** Feet row, in the same datum the avatar's `y` uses. */
  y: number;
  hp: Gauge;
  motion: BossMotionState;
  /** Bumped once per salvo so the view can replay the attack strip. */
  attackImpulses: number;
  poseUntilSeconds: number | null;
  lastHitAtMs: number | null;
}

export interface EncounterState {
  phase: EncounterPhase;
  /** Step-clock seconds, stamped on the first tick of the phase. */
  phaseStartedAt: number | null;
  nextArenaAtColumn: number;
  encounterIndex: number;
  boss: BossState | null;
  shots: EncounterShot[];
  nextShotId: number;
  salvosFired: number;
  nextSalvoAt: number | null;
  nextPlayerShotAt: number | null;
  laneSeed: number;
  outcome: EncounterOutcome | null;
}

/** Feel, not truth: no refusal reads anything below. */
export const BOSS_APPROACH_COLUMNS_PER_SECOND = 5;
export const BOSS_RETREAT_COLUMNS_PER_SECOND = 8;
export const BOSS_ATTACK_POSE_SECONDS = 0.35;
export const BOSS_HIT_FLASH_MS = 64;
/** How wide the boss's hit box is, as a fraction of its drawn height. */
export const BOSS_HALF_WIDTH_FRACTION = 0.35;
/** A hard ceiling so a pathological package cannot grow the array without end. */
export const ENCOUNTER_SHOT_CAP = 32;

export function createEncounterState(config: EncounterConfig): EncounterState {
  return {
    phase: "idle",
    phaseStartedAt: null,
    nextArenaAtColumn: config.intervalColumns,
    encounterIndex: 0,
    boss: null,
    shots: [],
    nextShotId: 0,
    salvosFired: 0,
    nextSalvoAt: null,
    nextPlayerShotAt: null,
    laneSeed: 0,
    outcome: null,
  };
}

/**
 * Whether the segment stream should be feeding the arena this frame.
 *
 * True from the moment the arena is asked for until the boss is gone, so the
 * floor is already there when the fight starts and does not vanish under a
 * retreating boss. The moment it goes false the stream resumes drawing from
 * the run-role catalog, and whatever arena is already queued plays out.
 */
export function encounterStreamsArena(phase: EncounterPhase): boolean {
  return phase === "arena_pending" || phase === "cut_in" || phase === "battle" ||
    phase === "retreat";
}

export function createBossState(config: EncounterConfig, entryOffsetColumns: number): BossState {
  return {
    offsetColumns: entryOffsetColumns,
    y: bossHoverFeetRow(config),
    hp: createGauge(config.hitsToDefeat),
    motion: "hover",
    attackImpulses: 0,
    poseUntilSeconds: null,
    lastHitAtMs: null,
  };
}

/**
 * The row the boss's feet sit on so its body centres in the playable band.
 *
 * Its art is anchored at the feet like every other actor, so a boss taller
 * than the band would otherwise hang its head off the top of the screen. A
 * boss shorter than the band floats to the middle of it, which is what a
 * hovering machine should do; one exactly as tall stands on the floor.
 */
export function bossHoverFeetRow(config: EncounterConfig, walkSurfaceRow?: number): number {
  const surface = walkSurfaceRow ?? config.bossHeightRows;
  const slack = Math.max(0, surface - config.bossHeightRows);
  return surface - slack / 2;
}

/**
 * Close the boss toward its stand-off, then hold there.
 *
 * It enters from off the right edge and walks in at a fixed rate rather than
 * appearing at its firing distance, because a boss that pops into position has
 * no arrival for the cut-in to have announced.
 */
export function bossApproach(
  currentOffsetColumns: number,
  firingDistanceColumns: number,
  dt: number,
): number {
  if (currentOffsetColumns <= firingDistanceColumns) return firingDistanceColumns;
  const stepped = currentOffsetColumns - BOSS_APPROACH_COLUMNS_PER_SECOND * dt;
  return Math.max(firingDistanceColumns, stepped);
}

export function bossRetreat(currentOffsetColumns: number, dt: number): number {
  return currentOffsetColumns + BOSS_RETREAT_COLUMNS_PER_SECOND * dt;
}

/** A small deterministic generator, seeded per encounter. */
export type Rng = () => number;

export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * The lane seed for one encounter of one run.
 *
 * Derived from the run seed and the encounter's ordinal rather than drawn from
 * the chunk-selection stream, so the lanes of the third fight are the same
 * whether the player reached it in three chunks or thirty.
 */
export function laneSeedFor(runSeed: number, encounterIndex: number): number {
  return (Math.imul(runSeed ^ 0x9e3779b1, encounterIndex + 1) + 0x85ebca6b) >>> 0;
}

export interface SalvoLane {
  readonly top: number;
  readonly bottom: number;
}

export interface Salvo {
  readonly rows: readonly number[];
  readonly lane: SalvoLane;
}

/**
 * Place one salvo so a lane the avatar fits through is always left open.
 *
 * The lane is chosen FIRST and the shots are stacked outward from its edges,
 * rather than shots being placed and a gap hoped for. That inverts where the
 * guarantee lives: with shots first, "is there a gap?" is a question about the
 * result, and the answer is sometimes no. With the lane first it is a property
 * of the construction, and the only thing left to prove is that the lane fits
 * in the band — which the generator proved offline, before any of this ran.
 *
 * Whether the avatar can *reach* the lane in the shot's flight time is the
 * other half of that offline proof (the dodge window), so nothing here has to
 * re-derive it.
 */
export function salvoRows(
  rng: Rng,
  options: {
    readonly walkSurfaceRow: number;
    readonly avatarHeightRows: number;
    readonly laneMarginRows: number;
    readonly projectileHeightRows: number;
    readonly shots: number;
  },
): Salvo {
  const { walkSurfaceRow, avatarHeightRows, laneMarginRows, projectileHeightRows, shots } = options;
  const laneHeight = avatarHeightRows + 2 * laneMarginRows;
  const slack = Math.max(0, walkSurfaceRow - laneHeight);
  const laneTop = rng() * slack;
  const laneBottom = laneTop + laneHeight;
  const half = projectileHeightRows / 2;

  const candidates: number[] = [];
  for (let centre = laneTop - half; centre - half >= 0; centre -= projectileHeightRows) {
    candidates.push(centre);
  }
  for (
    let centre = laneBottom + half;
    centre + half <= walkSurfaceRow;
    centre += projectileHeightRows
  ) {
    candidates.push(centre);
  }

  // Shuffle so a salvo smaller than the band does not always crowd the ceiling.
  for (let i = candidates.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [candidates[i], candidates[j]] = [candidates[j], candidates[i]];
  }

  return Object.freeze({
    rows: Object.freeze(candidates.slice(0, Math.min(shots, candidates.length))),
    lane: Object.freeze({ top: laneTop, bottom: laneBottom }),
  });
}

/** Advance one shot in the avatar's frame. */
export function advanceShot(shot: EncounterShot, dt: number): void {
  shot.x += shot.vx * dt;
}

/**
 * Whether a shot has left the encounter.
 *
 * A boss shot that has passed behind the avatar is spent; a player shot that
 * has passed the boss missed. Both are measured against the avatar rather than
 * the screen so the test does not need a viewport.
 */
export function shotExpired(
  shot: EncounterShot,
  options: { readonly behindColumns: number; readonly aheadColumns: number },
): boolean {
  if (shot.owner === "boss") return shot.x < -options.behindColumns;
  return shot.x > options.aheadColumns;
}

export interface Box {
  readonly left: number;
  readonly right: number;
  readonly top: number;
  readonly bottom: number;
}

/**
 * Overlap in the avatar's frame, strict on every edge.
 *
 * Strict rather than inclusive to match the hazard test the rest of the runner
 * already uses: two overlap semantics in one runtime is a bug waiting for the
 * one frame a box lands exactly on an edge.
 */
export function boxesOverlap(a: Box, b: Box): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

export function shotBox(shot: EncounterShot): Box {
  return {
    left: shot.x - shot.halfLengthColumns,
    right: shot.x + shot.halfLengthColumns,
    top: shot.row - shot.halfHeightRows,
    bottom: shot.row + shot.halfHeightRows,
  };
}

/** The boss's hit box, in the avatar's frame. */
export function bossBox(boss: BossState, config: EncounterConfig): Box {
  const halfWidth = config.bossHeightRows * BOSS_HALF_WIDTH_FRACTION;
  return {
    left: boss.offsetColumns - halfWidth,
    right: boss.offsetColumns + halfWidth,
    top: boss.y - config.bossHeightRows,
    bottom: boss.y,
  };
}

/**
 * The velocity a held or released thrust settles toward.
 *
 * One acceleration, two caps: held pulls up toward the climb cap, released
 * falls toward the fall cap. The asymmetry that matters is between the caps,
 * because a rise slower than the fall is what makes a dodge cost something.
 */
export function thrustVelocity(
  vy: number,
  held: boolean,
  dt: number,
  thrust: ThrustArithmetic,
): number {
  const accelerated = vy + (held ? -1 : 1) * thrust.climbAccelerationRowsPerSecondSquared * dt;
  return Math.max(
    -thrust.maxClimbRowsPerSecond,
    Math.min(thrust.maxFallRowsPerSecond, accelerated),
  );
}
