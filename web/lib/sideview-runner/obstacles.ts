// Hazard and pickup instances from the streamed chunks, plus their overlaps.
//
// Every box lives in world units — columns across, rows down — so overlap is
// a statement about the track, not about pixels. A hazard's height comes from
// its declared magnitude (player = 1.0 unit) scaled by the player's height in
// tiles, which is the same arithmetic that sizes its artwork. The collision
// insets come from the manifest's published arithmetic: the offline press
// window proof used exactly these numbers, so retuning them here without a
// contract change is impossible by construction.

import {
  streamedHazards,
  streamedPickups,
  surfaceRowAt,
  type StreamedHazard,
  type StreamedPickup,
} from "./segments";
import type { GameSystem } from "@/lib/game-systems/systems";
import type { AvatarState, RunnerWorld, RunnerWorldConfig } from "./world";

export interface WorldBox {
  readonly left: number;
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
}

/** Strict AABB overlap: touching edges do not collide. */
export function boxesOverlap(a: WorldBox, b: WorldBox): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

/** A pickup occupies the middle of its cell, so collecting takes intent. */
export const PICKUP_CELL_INSET = 0.2;

export function avatarBox(
  avatar: Pick<AvatarState, "distanceColumns" | "y" | "sliding">,
  config: Pick<RunnerWorldConfig, "playerHeightTiles" | "arithmetic" | "duckedHeightFraction">,
): WorldBox {
  // The ducked fraction is published, refusal-bearing arithmetic: admission
  // proved every overhead clearance against exactly this box.
  const height =
    avatar.sliding && config.duckedHeightFraction !== null
      ? config.playerHeightTiles * config.duckedHeightFraction
      : config.playerHeightTiles;
  return {
    left: avatar.distanceColumns - config.arithmetic.avatarHalfWidthColumns,
    right: avatar.distanceColumns + config.arithmetic.avatarHalfWidthColumns,
    top: avatar.y - height,
    bottom: avatar.y,
  };
}

/** A surface hazard stands on its column; an overhead one hangs above its
 * declared clearance, both measured from the same supported surface. */
export function hazardBox(
  hazard: Pick<StreamedHazard, "anchor" | "clearanceRows">,
  worldColumn: number,
  surfaceRow: number,
  heightRows: number,
  hazardColumnInset: number,
): WorldBox {
  const bottom =
    hazard.anchor === "overhead" ? surfaceRow - (hazard.clearanceRows ?? 0) : surfaceRow;
  return {
    left: worldColumn + hazardColumnInset,
    right: worldColumn + 1 - hazardColumnInset,
    top: bottom - heightRows,
    bottom,
  };
}

export function pickupBox(worldColumn: number, row: number): WorldBox {
  return {
    left: worldColumn + PICKUP_CELL_INSET,
    right: worldColumn + 1 - PICKUP_CELL_INSET,
    top: row + PICKUP_CELL_INSET,
    bottom: row + 1 - PICKUP_CELL_INSET,
  };
}

/** One pickup instance's identity. World columns never repeat within a run. */
export function pickupKey(pickup: StreamedPickup): string {
  return `${pickup.worldColumn}:${pickup.row}:${pickup.itemId}`;
}

/** Instance identity for a hazard placement, matching `pickupKey`'s shape. */
export function hazardKey(hazard: StreamedHazard): string {
  return `${hazard.worldColumn}:${hazard.propId}`;
}

export function createObstaclesSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/obstacles",
    contractVersion: "obstacles-system-v3",
    reads: ["segments", "avatar"],
    writes: ["obstacles"],
    emits: ["hazard-contact"],
    update(world) {
      const obstacles = world.obstacles;
      obstacles.hazardContact = false;
      obstacles.collectedThisFrame = [];
      obstacles.missedThisFrame = 0;
      // Feedback read of last frame's phase: a dead avatar collides with
      // nothing and collects nothing, and a held one has not started.
      if (world.run.phase !== "running") return;

      const avatar = avatarBox(world.avatar, world.config);
      for (const hazard of streamedHazards(world.segments)) {
        // Only placements near the avatar can overlap; skip the rest cheaply.
        if (Math.abs(hazard.worldColumn - world.avatar.distanceColumns) > 2) continue;
        const surface = surfaceRowAt(world.segments, hazard.worldColumn);
        // Admission proved hazards stand on support; a pit here is unreachable.
        if (surface === null) continue;
        const heightRows =
          (world.config.propHeightUnits.get(hazard.propId) ?? 1) *
          world.config.playerHeightTiles;
        const box = hazardBox(
          hazard,
          hazard.worldColumn,
          surface,
          heightRows,
          world.config.arithmetic.hazardColumnInset,
        );
        if (boxesOverlap(avatar, box)) {
          obstacles.hazardContact = true;
          // Per instance, edge-triggered, keyed the way pickups already are.
          // Overlap is a *level* — it holds for every frame of the crossing —
          // and a gauge told about a level would be emptied by one prop. What
          // the vitals system needs to hear is that this particular hazard was
          // struck, which happens exactly once however long the crossing runs.
          const key = hazardKey(hazard);
          if (!obstacles.struck.has(key)) {
            obstacles.struck.add(key);
            world.events.emit({ type: "hazard-contact", key });
          }
        }
      }
      for (const pickup of streamedPickups(world.segments)) {
        const key = pickupKey(pickup);
        if (obstacles.collected.has(key)) continue;
        // A pickup fully behind the avatar was passed for good: it is missed
        // exactly once, and the run-loop breaks the chain on it.
        if (pickup.worldColumn + 1 < world.avatar.distanceColumns - 0.5) {
          if (!obstacles.missed.has(key)) {
            obstacles.missed.add(key);
            obstacles.missedThisFrame += 1;
          }
          continue;
        }
        if (Math.abs(pickup.worldColumn - world.avatar.distanceColumns) > 2) continue;
        if (boxesOverlap(avatar, pickupBox(pickup.worldColumn, pickup.row))) {
          obstacles.collected.add(key);
          obstacles.collectedThisFrame.push(pickup);
        }
      }
    },
  };
}
