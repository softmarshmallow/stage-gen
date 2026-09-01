// Hazard and pickup instances from the streamed chunks, plus their overlaps.
//
// Every box lives in world units — columns across, rows down — so overlap is
// a statement about the track, not about pixels. A hazard's height comes from
// its declared magnitude (player = 1.0 unit) scaled by the player's height in
// tiles, which is the same arithmetic that sizes its artwork; its footprint
// is its authored column, inset so brushing past reads as a near miss rather
// than a death.

import {
  streamedHazards,
  streamedPickups,
  surfaceRowAt,
  type StreamedPickup,
} from "./segments";
import type { GameSystem } from "./systems";
import type { AvatarState, RunnerWorld } from "./world";

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

/** Half of the avatar's collision width, in columns: a torso, not the artwork. */
export const AVATAR_HALF_WIDTH_COLUMNS = 0.3;

/** Horizontal inset of a hazard's box inside its authored column. */
export const HAZARD_COLUMN_INSET = 0.15;

/** A pickup occupies the middle of its cell, so collecting takes intent. */
export const PICKUP_CELL_INSET = 0.2;

export function avatarBox(avatar: AvatarState, playerHeightTiles: number): WorldBox {
  return {
    left: avatar.distanceColumns - AVATAR_HALF_WIDTH_COLUMNS,
    right: avatar.distanceColumns + AVATAR_HALF_WIDTH_COLUMNS,
    top: avatar.y - playerHeightTiles,
    bottom: avatar.y,
  };
}

export function hazardBox(
  worldColumn: number,
  surfaceRow: number,
  heightRows: number,
): WorldBox {
  return {
    left: worldColumn + HAZARD_COLUMN_INSET,
    right: worldColumn + 1 - HAZARD_COLUMN_INSET,
    top: surfaceRow - heightRows,
    bottom: surfaceRow,
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

export function createObstaclesSystem(): GameSystem<RunnerWorld> {
  return {
    id: "runner/obstacles",
    contractVersion: "obstacles-system-v1",
    reads: ["segments", "avatar"],
    writes: ["obstacles"],
    update(world) {
      const obstacles = world.obstacles;
      obstacles.hazardContact = false;
      obstacles.collectedThisFrame = [];
      // Feedback read of last frame's phase: a dead avatar collides with
      // nothing and collects nothing.
      if (world.run.phase === "dead") return;

      const avatar = avatarBox(world.avatar, world.config.playerHeightTiles);
      for (const hazard of streamedHazards(world.segments)) {
        // Only placements near the avatar can overlap; skip the rest cheaply.
        if (Math.abs(hazard.worldColumn - world.avatar.distanceColumns) > 2) continue;
        const surface = surfaceRowAt(world.segments, hazard.worldColumn);
        // Admission proved hazards stand on support; a pit here is unreachable.
        if (surface === null) continue;
        const heightRows =
          (world.config.propHeightUnits.get(hazard.propId) ?? 1) *
          world.config.playerHeightTiles;
        if (boxesOverlap(avatar, hazardBox(hazard.worldColumn, surface, heightRows))) {
          obstacles.hazardContact = true;
        }
      }
      for (const pickup of streamedPickups(world.segments)) {
        if (Math.abs(pickup.worldColumn - world.avatar.distanceColumns) > 2) continue;
        const key = pickupKey(pickup);
        if (obstacles.collected.has(key)) continue;
        if (boxesOverlap(avatar, pickupBox(pickup.worldColumn, pickup.row))) {
          obstacles.collected.add(key);
          obstacles.collectedThisFrame.push(pickup);
        }
      }
    },
  };
}
