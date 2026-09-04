// The runner's vitals: what a contact costs, and what happens after it.
//
// Everything genuinely general here — the gauge, its refractory window, the
// blink phase — lives in `lib/kernel/gauge.ts` and is shared with the
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

import type { Gauge } from "@/lib/kernel/gauge";
import {
  bodyBlinkAlpha,
  bodyIsImmune,
  CONTACT_HURT_PROFILE,
  parseVitalsBlock,
  resolveVitals,
  vitalsClockMs,
  type VitalsBlockView,
  type VitalsSlice,
} from "@/lib/families/vitals";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { FxEvent } from "@/lib/fx/moment-system";
import { RUNNER_BLOCKS, type RunnerDamageSource } from "./contract";
import type { GameSystem } from "@/lib/kernel/systems";
import { surfaceRowAt } from "./segments";
import type { EncounterEvent } from "./encounter";
import type { SessionEvent } from "./session";
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
export const RUNNER_REFRACTORY_MS = CONTACT_HURT_PROFILE.refractoryMs;

/** One bright/dim phase of the avatar while the window is open. */
export const RUNNER_BLINK_INTERVAL_MS = CONTACT_HURT_PROFILE.blinkIntervalMs;

/** Dim phase opacity: trackable while running, unmistakable as immunity. */
export const RUNNER_BLINK_ALPHA = CONTACT_HURT_PROFILE.blinkAlpha;

/** Points one contact spends. One, for every source: a hit is a hit. */
export const RUNNER_DRAIN_AMOUNT = CONTACT_HURT_PROFILE.drainAmount;

/**
 * How far ahead recovery looks for somewhere to stand, in columns.
 *
 * A pit is at most `maxClearGapColumns` wide by admission, and the streamed
 * window always extends past the avatar, so a legal surface is always within a
 * few columns. The bound exists so a malformed stream ends the run instead of
 * scanning forever.
 */
export const RUNNER_RECOVERY_LOOKAHEAD_COLUMNS = 12;

/**
 * This genre's vitals slice: the family's, with the runner's recovery shape.
 *
 * A recovery is "a column and a row" here and something else in the next
 * genre, so the family is generic over it and never learns what standing
 * somewhere means.
 */
export type RunnerRecovery = Readonly<{ column: number; row: number }>;
export type VitalsState = VitalsSlice<RunnerRecovery>;

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
  /** A moment was asked for, released the simulation, or finished. */
  | FxEvent
  /** The boss encounter's own announcements. */
  | EncounterEvent
  /** The lifecycle's own: this run is over and another was asked for. */
  | SessionEvent;

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
  return bodyIsImmune(world.vitals);
}

/** The fixed step counts seconds; the gauge counts milliseconds. */
export const stepClockMs = vitalsClockMs;

/** Sprite opacity for this frame: the shared blink, at the shared cadence. */
export function avatarBlinkAlpha(world: RunnerWorld): number {
  return bodyBlinkAlpha(world.vitals, CONTACT_HURT_PROFILE);
}

/**
 * The block this genre's consequence table is authored in.
 *
 * `[run.consequences]` and `[run.vitals]` both live under `gameplay`, so a
 * producer that moves the block gets a refusal naming it from the family that
 * cannot resolve a contact without it.
 */
export const RUNNER_VITALS_BLOCK = Object.freeze({
  block: "gameplay",
  version: RUNNER_BLOCKS.gameplay,
});

/** Gate the runner's vitals block. Refuses by naming `gameplay`. */
export function parseRunnerVitalsBlock(blocks: BlockTable): VitalsBlockView {
  return parseVitalsBlock(blocks, RUNNER_VITALS_BLOCK);
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
    contractVersion: "vitals-system-v3",
    reads: ["clock", "avatar", "segments"],
    writes: [],
    owns: ["vitals"],
    consumes: ["hazard-contact", "pit", "crush", "shot-contact"],
    emits: ["drained", "absorbed", "run-ended"],
    update(world) {
      const vitals = world.vitals;
      // The simulation's own clock, not the frame's. A refractory window
      // stamped against `step.now` keeps expiring while a moment holds the
      // simulation, so a two-second cut-in burns straight through a
      // nine-hundred-millisecond immunity that never protected anything.
      vitals.clockMs = stepClockMs(world.clock.simulationNow);
      vitals.hurtThisFrame = false;
      vitals.depletedThisFrame = false;
      if (world.run.phase !== "running") return;

      // Which occurrences can hurt is this genre's question; what each one
      // costs is the package's table; resolving the two is the family's.
      const sources = world.events.frame
        .filter(
          (event) =>
            event.type === "hazard-contact" ||
            event.type === "pit" ||
            event.type === "crush" ||
            event.type === "shot-contact",
        )
        .map((event): RunnerDamageSource =>
          event.type === "hazard-contact"
            ? "hazard"
            : event.type === "shot-contact"
              ? "shot"
              : (event.type as "pit" | "crush"),
        );

      const verdicts = resolveVitals<RunnerDamageSource, RunnerRecovery>({
        vitals,
        sources,
        consequences: world.config.consequences,
        profile: CONTACT_HURT_PROFILE,
        // The `RecoveryPolicy` port, answered by this genre's own space: the
        // next solid column ahead, found with the same surface query the
        // avatar's physics uses, so a landing is exactly a landing.
        recover: () => recoverySurface(world, world.avatar.distanceColumns),
      });

      for (const verdict of verdicts) {
        if (verdict.kind === "drained") {
          world.events.emit({
            type: "drained",
            source: verdict.source,
            remaining: verdict.remaining,
          });
        } else if (verdict.kind === "absorbed") {
          world.events.emit({ type: "absorbed", source: verdict.source });
        } else {
          world.events.emit({ type: "run-ended", source: verdict.source });
        }
      }
    },
  };
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
