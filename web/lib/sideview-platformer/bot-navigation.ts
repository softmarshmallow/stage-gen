// This genre's binding of the `navigation` family.
//
// The graph, the lanes, the search and the steering are the family's — nothing
// in them mentions a bot, and the creature that wanders a shelf derives its
// lane from the same rule now. What is this genre's, and what stays here, is
// the *repertoire*: a navigator's model of itself has to be the model its
// physics uses, so the default capabilities are the platformer controller's own
// constants, and the buttons come back as this genre's `PlayerIntent` through
// the family's `intentOf` seam rather than as a record the family invented.

import { playerIntent, type PlayerIntent } from "./player-intent";
import {
  PLATFORMER_AIR_JUMP_VELOCITY,
  PLATFORMER_GRAVITY,
  PLATFORMER_JUMP_VELOCITY,
  PLATFORMER_RUN_SPEED,
  PLATFORMER_WALK_SPEED,
  TERRAIN_STEP_UP_TOLERANCE,
} from "./vertical";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import {
  DEFAULT_NAV_STEER_TUNING,
  movementCapabilities as sealMovementCapabilities,
  parseNavigationBlock,
  steerNav as familySteerNav,
  type MovementCapabilities,
  type NavAgentState,
  type NavLink,
  type NavSteerTuning,
  type NavigationBlockView,
} from "@/lib/families/navigation";

export {
  buildNavGraph,
  EMPTY_NAV_GRAPH,
  laneAtColumn,
  locateNavNode,
  navReach,
  reachOf,
  terrainLanes,
  DEFAULT_NAV_STEER_TUNING,
  type LaneSpan,
  type MovementCapabilities,
  type NavAgentState,
  type NavClimbableInput,
  type NavGraph,
  type NavGraphInput,
  type NavLink,
  type NavMove,
  type NavNode,
  type NavNodeKind,
  type NavPlatformInput,
  type NavReach,
  type NavSteerTuning,
} from "@/lib/families/navigation";

/**
 * The repertoire the platformer's own controller has.
 *
 * Every number here is the constant the physics integrates with, which is the
 * point: a route the graph admits is a route the body can fly, because the
 * admission ran the same arc the controller will.
 */
export const DEFAULT_MOVEMENT_CAPABILITIES: MovementCapabilities = Object.freeze({
  walkSpeed: PLATFORMER_WALK_SPEED,
  runSpeed: PLATFORMER_RUN_SPEED,
  jumpVelocity: PLATFORMER_JUMP_VELOCITY,
  airJumpVelocity: PLATFORMER_AIR_JUMP_VELOCITY,
  gravity: PLATFORMER_GRAVITY,
  stepSeconds: 1 / 30,
  stepUpTolerance: TERRAIN_STEP_UP_TOLERANCE,
  canClimb: true,
  canDropThrough: true,
});

export function movementCapabilities(
  overrides: Partial<MovementCapabilities> = {},
): MovementCapabilities {
  return sealMovementCapabilities(DEFAULT_MOVEMENT_CAPABILITIES, overrides);
}

/**
 * The block this genre authors its repertoire in.
 *
 * `gameplay`, because `[navigation].allowed_movements` is what admits a link at
 * all. The geometry has no block — it is derived from the traversal core — so
 * this is the one dependency navigation has, and it names it itself.
 */
export const PLATFORMER_NAVIGATION_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's navigation block. Refuses by naming `gameplay`. */
export function parsePlatformerNavigationBlock(blocks: BlockTable): NavigationBlockView {
  return parseNavigationBlock(blocks, PLATFORMER_NAVIGATION_BLOCK);
}

/** The buttons this frame, in this genre's own intent record. */
export function steerNav(input: Readonly<{
  self: NavAgentState;
  link: NavLink | null;
  targetX: number;
  capabilities: MovementCapabilities;
  tuning?: NavSteerTuning;
}>): PlayerIntent {
  return familySteerNav({ ...input, intentOf: playerIntent });
}
