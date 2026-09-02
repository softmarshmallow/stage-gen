// The runner's vitals: what a contact costs, and what happens after it.
//
// Everything genuinely general here — the gauge, its refractory window, the
// blink phase — lives in `lib/game-systems/gauge.ts` and is shared with the
// platformer. What stays in this file is what is actually the runner's: which
// occurrences can hurt, which consequence each package chose for them, and
// where the avatar is put down again when a fall is survivable.
//
// The numbers below are consumer-owned on purpose, and the split is the one
// stated in `runner_gameplay/models.py`: a number belongs in the SDK constant
// table iff a refusal depends on it, and stays here iff only the feel does.
// Admission proves that every hazard is *avoidable* at the base speed; it
// proves nothing about how long immunity lasts or how fast the sprite blinks,
// because those change nothing about whether a track is fair. So the manifest
// publishes the gauge's ceiling — a bar cannot be drawn without it — and the
// rest is tunable here without regenerating a single image.

import { drain, isRefractory, refractoryBlinkAlpha, type Gauge } from "@/lib/game-systems/gauge";
import type { FxEvent } from "@/lib/fx/moment-system";
import type { RunnerDamageSource } from "./contract";
import type { GameSystem } from "@/lib/game-systems/systems";
import { surfaceRowAt } from "./segments";
import type { EncounterEvent } from "./encounter";
import type { RunnerWorld } from "./world";

/**
 * Immunity after a contact, in ms.
 *
 * Contact with a runner hazard is continuous while the avatar crosses it, and
 * at the brisk profile's 7.5 columns per second a 1-column prop is in contact
 * for about 133ms — twenty frames. Without a window a single clip would empty
 * a three-point gauge before the player's hand left the key. 900ms matches the
 * platformer's, and at base speed it is comfortably longer than any authored
 * hazard's crossing, so one prop can only ever cost one point.
 */
export const RUNNER_REFRACTORY_MS = 900;

/** One bright/dim phase of the avatar while the window is open. */
export const RUNNER_BLINK_INTERVAL_MS = 75;

/** Dim phase opacity: trackable while running, unmistakable as immunity. */
export const RUNNER_BLINK_ALPHA = 0.35;

/** Points one contact spends. One, for every source: a hit is a hit. */
export const RUNNER_DRAIN_AMOUNT = 1;

/**
 * How far ahead recovery looks for somewhere to stand, in columns.
 *
 * A pit is at most `maxClearGapColumns` wide by admission, and the streamed
 * window always extends past the avatar, so a legal surface is always within a
 * few columns. The bound exists so a malformed stream ends the run instead of
 * scanning forever.
 */
export const RUNNER_RECOVERY_LOOKAHEAD_COLUMNS = 12;

export interface VitalsState {
  /** Null exactly when no consequence drains — a one-hit-kill package. */
  gauge: Gauge | null;
  /**
   * The simulation clock, in milliseconds, that the gauge was last evaluated
   * against.
   *
   * The fixed step counts in *seconds* while the gauge and its window are in
   * milliseconds, and presentation must blink against exactly the clock the
   * window was written from — Phaser's own `time.now` is a different clock and
   * would drift out of phase with the simulation on any stall. So the
   * conversion happens once, here, and everything that needs the time reads
   * this rather than converting again.
   */
  clockMs: number;
  /**
   * Where a survivor is to be put down, applied by the avatar next frame.
   *
   * Not written straight onto the avatar, and the sealer is what proved that
   * cannot work: the avatar emits the occurrence, so a vitals system that
   * wrote the avatar back would have to run both before and after it. A
   * one-frame feedback hand-off is the honest shape, and it is the same one
   * `stepAvatar` already uses for the run phase and the segment window — at
   * 60Hz it is one extra frame of falling, which is invisible.
   */
  pendingRecovery: Readonly<{ column: number; row: number }> | null;
  /** Set on the frame a drain connected, for the audio cue and the bar flash. */
  hurtThisFrame: boolean;
  /** Set on the frame the gauge emptied, so the run-loop ends the run once. */
  depletedThisFrame: boolean;
}

export type RunnerEvent =
  /** The avatar overlapped this hazard instance for the first time. */
  | { readonly type: "hazard-contact"; readonly key: string }
  /** The avatar fell below the world. */
  | { readonly type: "pit" }
  /** Ground rose into the avatar, or it was buried without crossing from above. */
  | { readonly type: "crush" }
  /** A consequence spent a point. */
  | { readonly type: "drained"; readonly source: RunnerDamageSource; readonly remaining: number }
  /** A consequence arrived while immune, or against a package that cannot spend. */
  | { readonly type: "absorbed"; readonly source: RunnerDamageSource }
  /** The run is over, by this source. */
  | { readonly type: "run-ended"; readonly source: RunnerDamageSource }
  /** A screen-FX moment released the simulation, or finished. */
  | FxEvent
  /** The boss encounter's own announcements. */
  | EncounterEvent;

/**
 * The first solid surface at or after a column, or null within the lookahead.
 *
 * Deliberately the same `surfaceRowAt` the physics and the collision boxes
 * read, so a recovered avatar stands exactly where a running one would have.
 */
export function recoverySurface(
  world: RunnerWorld,
  fromColumn: number,
): Readonly<{ column: number; row: number }> | null {
  const start = Math.floor(fromColumn);
  for (let offset = 0; offset <= RUNNER_RECOVERY_LOOKAHEAD_COLUMNS; offset += 1) {
    const column = start + offset;
    const row = surfaceRowAt(world.segments, column);
    if (row !== null) return Object.freeze({ column, row });
  }
  return null;
}

/** Whether the avatar is inside its post-contact immunity window. */
export function avatarIsImmune(world: RunnerWorld): boolean {
  const gauge = world.vitals.gauge;
  return gauge !== null && isRefractory(gauge, world.vitals.clockMs);
}

/** The fixed step counts seconds; the gauge counts milliseconds. */
export function stepClockMs(stepNowSeconds: number): number {
  return stepNowSeconds * 1000;
}

/** Sprite opacity for this frame: the shared blink, at the runner's cadence. */
export function avatarBlinkAlpha(world: RunnerWorld): number {
  const gauge = world.vitals.gauge;
  if (gauge === null) return 1;
  return refractoryBlinkAlpha(
    gauge,
    world.vitals.clockMs,
    RUNNER_BLINK_INTERVAL_MS,
    RUNNER_BLINK_ALPHA,
  );
}

/**
 * The vitals system: turn occurrences into what they cost.
 *
 * Sealed between the systems that detect trouble and the run-loop that ends
 * runs, and it is the only place that reads a package's consequence table. The
 * run-loop no longer decides what a hazard means — it consumes `run-ended` and
 * does the one thing it is for.
 */
export function createVitalsSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/vitals",
    contractVersion: "vitals-system-v2",
    reads: ["avatar", "segments"],
    writes: ["vitals"],
    consumes: ["hazard-contact", "pit", "crush", "shot-contact"],
    emits: ["drained", "absorbed", "run-ended"],
    update(world, step) {
      const vitals = world.vitals;
      vitals.clockMs = stepClockMs(step.now);
      vitals.hurtThisFrame = false;
      vitals.depletedThisFrame = false;
      if (world.run.phase !== "running") return;

      // One frame can carry several sources — clipping a prop on the way into
      // a pit is ordinary play. They are resolved in the order they happened,
      // and the refractory window makes all but the first absorbed, so a
      // compound accident costs one point rather than three.
      const occurrences = world.events.frame.filter(
        (event) =>
          event.type === "hazard-contact" ||
          event.type === "pit" ||
          event.type === "crush" ||
          event.type === "shot-contact",
      );

      for (const occurrence of occurrences) {
        const source: RunnerDamageSource =
          occurrence.type === "hazard-contact"
            ? "hazard"
            : occurrence.type === "shot-contact"
              ? "shot"
              : occurrence.type;
        const consequence = world.config.consequences[source];

        if (consequence === undefined || consequence === null) {
          // Unreachable: the contract pairs a shot answer with the encounter
          // that fires it. A missing answer must still not forgive the hit.
          world.events.emit({ type: "run-ended", source });
          return;
        }

        if (consequence === "end_run_v1") {
          world.events.emit({ type: "run-ended", source });
          return;
        }

        const gauge = vitals.gauge;
        if (gauge === null) {
          // A package whose consequences all end the run has no gauge, and the
          // contract refuses this combination — but a draining consequence
          // reaching a missing gauge must still not silently forgive the hit.
          world.events.emit({ type: "run-ended", source });
          return;
        }

        const change = drain(gauge, RUNNER_DRAIN_AMOUNT, vitals.clockMs, RUNNER_REFRACTORY_MS);
        if (!change.connected) {
          world.events.emit({ type: "absorbed", source });
          continue;
        }
        vitals.gauge = change.gauge;
        vitals.hurtThisFrame = true;
        world.events.emit({ type: "drained", source, remaining: change.after });

        if (consequence === "drain_and_recover_v1") {
          recoverAvatar(world, source);
        }

        if (change.depleted) {
          vitals.depletedThisFrame = true;
          world.events.emit({ type: "run-ended", source });
          return;
        }
      }
    },
  };
}

/**
 * Put a survivor back on the ground.
 *
 * A pit fall and a crush both leave the avatar somewhere it cannot legally be,
 * so forgiving them means choosing a place to continue from. The next solid
 * column ahead is the honest choice: it never rewinds progress the player
 * earned, it never skips a hazard they have not passed, and it is the same
 * surface query the avatar's own physics uses, so the landing is exactly a
 * landing. With nowhere to stand inside the lookahead the run ends instead —
 * a forgiving package should not become an unplayable one on a malformed
 * stream.
 */
function recoverAvatar(world: RunnerWorld, source: RunnerDamageSource): void {
  const surface = recoverySurface(world, world.avatar.distanceColumns);
  if (surface === null) {
    world.events.emit({ type: "run-ended", source });
    return;
  }
  world.vitals.pendingRecovery = surface;
}

/**
 * Put a survivor back on the ground, at the top of the avatar's own update.
 *
 * Exported and pure-ish so the placement is assertable without a frame loop.
 * The column never moves backwards: recovery forgives a fall, it does not undo
 * the distance the player earned reaching it.
 */
export function applyPendingRecovery(world: RunnerWorld): void {
  const recovery = world.vitals.pendingRecovery;
  if (recovery === null) return;
  world.vitals.pendingRecovery = null;
  world.avatar.distanceColumns = Math.max(world.avatar.distanceColumns, recovery.column);
  world.avatar.y = recovery.row;
  world.avatar.vy = 0;
  world.avatar.grounded = true;
  world.avatar.airJumpsUsed = 0;
  world.avatar.sliding = false;
  world.avatar.motion = "run";
}
