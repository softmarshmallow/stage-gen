// The encounter director: the one system that decides a boss fight is due,
// runs it, and hands the run back.
//
// It owns two slices and nothing else: the encounter state and the locomotion
// the avatar wears. The cut-in it plays is not a third — the fx system owns
// that slice and this system asks it for the moment. Everything a
// consequence costs still belongs to the vitals system, everything a score is
// worth still belongs to the run-loop, and every sprite still belongs to a
// view. This file decides only what is happening.
//
// Two reads here are deliberately undeclared feedback, in the pattern the
// sealed-system module sanctions and the avatar already uses. `segments` is
// read to ask which chunk the avatar is standing on: the stream runs a whole
// viewport ahead, so a one-frame-old window cannot be wrong about a column
// the avatar has already reached. `run.phase` is read to freeze the whole
// encounter while the run is dead or holding for the intro. Declaring either
// would seal a cycle, because the systems that write them are downstream.

import type { GameSystem } from "@/lib/kernel/systems";
import { requestFxMoment } from "@/lib/fx/moment-system";
import { drain } from "@/lib/kernel/gauge";

import {
  BOSS_ATTACK_POSE_SECONDS,
  ENCOUNTER_SHOT_CAP,
  type EncounterConfig,
  type EncounterShot,
  type EncounterState,
  advanceShot,
  bossApproach,
  bossBox,
  bossRetreat,
  boxesOverlap,
  createBossState,
  encounterStreamsArena,
  laneSeedFor,

  salvoRows,
  shotBox,
  shotExpired,
} from "./encounter-arithmetic";
import { mulberry32 } from "@/lib/kernel/rng";
import { chunkAt } from "./segments";
import type { RunnerWorld } from "./world";

/** What the director announces. Nothing here decides a cost or a score. */
export type EncounterEvent =
  /** A boss fight has begun; the cut-in, if any, is playing. */
  | { readonly type: "encounter-started"; readonly index: number }
  /** A boss shot reached the avatar. What it costs is the vitals system's. */
  | { readonly type: "shot-contact"; readonly shotId: number }
  /** A player shot reached the boss. */
  | { readonly type: "boss-hit"; readonly remaining: number }
  /** The boss's gauge is empty. */
  | { readonly type: "boss-defeated" }
  /** The boss is gone and the run is its own again. */
  | {
      readonly type: "encounter-ended";
      readonly outcome: "defeated" | "exhausted";
    };

/** Half the avatar's drawn width, in columns, for the shot's hit test. */
function avatarHalfWidth(world: RunnerWorld): number {
  return world.config.arithmetic.avatarHalfWidthColumns;
}

/** The avatar's box in the encounter's own frame: it sits at offset zero. */
function avatarBox(world: RunnerWorld) {
  const half = avatarHalfWidth(world);
  return {
    left: -half,
    right: half,
    top: world.avatar.y - world.config.playerHeightTiles,
    bottom: world.avatar.y,
  };
}

function enterPhase(state: EncounterState, phase: EncounterState["phase"], now: number): void {
  state.phase = phase;
  state.phaseStartedAt = now;
}

/** Where the boss waits before it walks in: just past the right edge. */
function bossEntryOffset(world: RunnerWorld): number {
  const ahead = world.config.viewportColumns * (1 - 0.25);
  return ahead + 2;
}

function pushShot(state: EncounterState, shot: Omit<EncounterShot, "id">): void {
  if (state.shots.length >= ENCOUNTER_SHOT_CAP) return;
  state.shots.push({ id: state.nextShotId, ...shot });
  state.nextShotId += 1;
}

function fireSalvo(world: RunnerWorld, state: EncounterState, config: EncounterConfig): void {
  const boss = state.boss;
  if (boss === null) return;
  const salvo = salvoRows(mulberry32(state.laneSeed + state.salvosFired), {
    walkSurfaceRow: world.config.walkSurfaceRow,
    avatarHeightRows: world.config.playerHeightTiles,
    laneMarginRows: config.laneMarginRows,
    projectileHeightRows: config.projectileHeightRows,
    shots: config.salvoShots,
  });
  for (const row of salvo.rows) {
    pushShot(state, {
      owner: "boss",
      x: boss.offsetColumns,
      row,
      vx: -config.projectileSpeedColumnsPerSecond,
      halfLengthColumns: config.projectileHeightRows / 2,
      halfHeightRows: config.projectileHeightRows / 2,
    });
  }
  state.salvosFired += 1;
  boss.attackImpulses += 1;
  boss.motion = "attack";
}

function firePlayerShot(world: RunnerWorld, state: EncounterState, config: EncounterConfig): void {
  pushShot(state, {
    owner: "player",
    x: avatarHalfWidth(world),
    row: world.avatar.y - world.config.playerHeightTiles / 2,
    vx: config.playerShotSpeedColumnsPerSecond,
    halfLengthColumns: config.projectileHeightRows / 2,
    halfHeightRows: config.projectileHeightRows / 4,
  });
}

/** Begin the fight proper: thrust on, boss inbound, lanes seeded. */
function beginBattle(world: RunnerWorld, state: EncounterState, now: number): void {
  const config = world.config.encounter;
  if (config === null) return;
  world.locomotion = "thrust";
  state.boss = createBossState(config, bossEntryOffset(world), world.config.walkSurfaceRow);
  state.laneSeed = laneSeedFor(world.run.seed, state.encounterIndex);
  state.salvosFired = 0;
  state.nextSalvoAt = now + config.salvoPeriodSeconds;
  state.nextPlayerShotAt = now + config.playerFirePeriodSeconds;
  state.outcome = null;
  enterPhase(state, "battle", now);
}

function endBattle(
  world: RunnerWorld,
  state: EncounterState,
  outcome: "defeated" | "exhausted",
  now: number,
): void {
  state.outcome = outcome;
  state.shots.length = 0;
  // The avatar returns to running physics immediately: it falls under the
  // jump arc's gravity wearing `fly`, lands on the arena floor, and wears
  // `run` again, which the avatar's own step already does.
  world.locomotion = "run";
  if (state.boss !== null && outcome === "defeated") state.boss.motion = "death";
  enterPhase(state, "retreat", now);
}

function stepBattle(world: RunnerWorld, state: EncounterState, now: number, dt: number): void {
  const config = world.config.encounter;
  const boss = state.boss;
  if (config === null || boss === null) return;

  boss.offsetColumns = bossApproach(boss.offsetColumns, config.firingDistanceColumns, dt);
  const atStandOff = boss.offsetColumns <= config.firingDistanceColumns + 1e-9;

  if (boss.poseUntilSeconds !== null && now >= boss.poseUntilSeconds) {
    boss.motion = "hover";
    boss.poseUntilSeconds = null;
  }

  if (
    atStandOff &&
    state.nextSalvoAt !== null &&
    now >= state.nextSalvoAt &&
    state.salvosFired < config.salvoBudget
  ) {
    fireSalvo(world, state, config);
    boss.poseUntilSeconds = now + BOSS_ATTACK_POSE_SECONDS;
    state.nextSalvoAt = now + config.salvoPeriodSeconds;
  }

  if (state.nextPlayerShotAt !== null && now >= state.nextPlayerShotAt) {
    firePlayerShot(world, state, config);
    state.nextPlayerShotAt = now + config.playerFirePeriodSeconds;
  }

  const avatar = avatarBox(world);
  const target = bossBox(boss, config);
  const survivors: EncounterShot[] = [];
  for (const shot of state.shots) {
    advanceShot(shot, dt);
    if (shot.owner === "boss") {
      if (boxesOverlap(shotBox(shot), avatar)) {
        world.events.emit({ type: "shot-contact", shotId: shot.id });
        continue;
      }
    } else if (boxesOverlap(shotBox(shot), target)) {
      const change = drain(boss.hp, 1, world.vitals.clockMs, 0);
      boss.hp = change.gauge;
      boss.lastHitAtMs = world.vitals.clockMs;
      world.events.emit({ type: "boss-hit", remaining: change.after });
      continue;
    }
    if (
      shotExpired(shot, {
        behindColumns: world.config.viewportColumns,
        aheadColumns: boss.offsetColumns + config.firingDistanceColumns,
      })
    ) {
      continue;
    }
    survivors.push(shot);
  }
  state.shots = survivors;

  if (boss.hp.depleted) {
    world.events.emit({ type: "boss-defeated" });
    endBattle(world, state, "defeated", now);
    return;
  }
  // A boss that has spent its budget leaves, but not before the last salvo it
  // fired has had its chance: retreating over live shots would take back a
  // threat the player is already dodging.
  const spent = state.salvosFired >= config.salvoBudget;
  if (spent && state.shots.every((shot) => shot.owner !== "boss")) {
    endBattle(world, state, "exhausted", now);
  }
}

/**
 * Advance the encounter one fixed step.
 *
 * Exported for the same reason `stepAvatar` is: the transitions are the part
 * worth testing, and a test should not have to seal a system list to reach
 * them.
 */
export function stepEncounter(world: RunnerWorld, now: number, dt: number): void {
  const state = world.encounter;
  const config = world.config.encounter;
  if (state === null || config === null) return;
  // Frozen while the run is not the player's: the intro holds, and a dead run
  // has nothing to fight.
  if (world.run.phase !== "running") return;

  switch (state.phase) {
    case "idle": {
      if (world.avatar.distanceColumns >= state.nextArenaAtColumn) {
        enterPhase(state, "arena_pending", now);
      }
      return;
    }
    case "arena_pending": {
      // Wait for the floor to arrive under the avatar's feet. The stream is
      // already appending it; a fight begun over ordinary track would open
      // with the avatar in a pit.
      const standing = chunkAt(world.segments, Math.floor(world.avatar.distanceColumns));
      if (standing?.role !== "arena") return;
      const moment = world.config.encounterMoment;
      // Never clobber a moment already in flight; the stage-start cut-in gets
      // to finish. Announced only once the encounter actually leaves this
      // phase, because waiting here is a frame that repeats.
      if (moment !== null && world.fx !== null) return;
      world.events.emit({ type: "encounter-started", index: state.encounterIndex });
      if (moment === null) {
        beginBattle(world, state, now);
        return;
      }
      // The director asks; `fx/moment` owns the slice and starts the moment on
      // its next tick — which is when it could first have been drawn in any
      // case, because fx is sealed ahead of this system so that this system
      // can hear the release it emits.
      requestFxMoment(world, moment.moment, moment.choreography);
      enterPhase(state, "cut_in", now);
      return;
    }
    case "cut_in": {
      const released = world.events.frame.some(
        (event) => event.type === "fx-released" && event.moment === "encounter_start",
      );
      if (released) beginBattle(world, state, now);
      return;
    }
    case "battle": {
      stepBattle(world, state, now, dt);
      return;
    }
    case "retreat": {
      const boss = state.boss;
      if (boss === null) {
        enterPhase(state, "cooldown", now);
        return;
      }
      boss.offsetColumns = bossRetreat(boss.offsetColumns, dt);
      if (boss.offsetColumns > bossEntryOffset(world)) {
        world.events.emit({
          type: "encounter-ended",
          outcome: state.outcome ?? "exhausted",
        });
        state.boss = null;
        enterPhase(state, "cooldown", now);
      }
      return;
    }
    case "cooldown": {
      // The arena the fight was fought over is still underfoot; the next
      // interval is measured from the moment ordinary track resumes, so two
      // encounters can never overlap.
      const standing = chunkAt(world.segments, Math.floor(world.avatar.distanceColumns));
      if (standing !== null && standing.role === "arena") return;
      state.nextArenaAtColumn = world.avatar.distanceColumns + config.intervalColumns;
      state.encounterIndex += 1;
      state.outcome = null;
      enterPhase(state, "idle", now);
      return;
    }
  }
}

/** Whether the segment stream should be feeding the arena this frame. */
export function encounterWantsArena(world: RunnerWorld): boolean {
  return world.encounter !== null && encounterStreamsArena(world.encounter.phase);
}

export function createEncounterSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/encounter",
    contractVersion: "encounter-system-v2",
    reads: ["avatar", "difficulty"],
    writes: [],
    owns: ["encounter", "locomotion"],
    emits: [
      "encounter-started",
      "shot-contact",
      "boss-hit",
      "boss-defeated",
      "encounter-ended",
      "fx-requested",
    ],
    consumes: ["fx-released"],
    update(world, step) {
      stepEncounter(world, step.now, step.dt);
    },
  };
}
