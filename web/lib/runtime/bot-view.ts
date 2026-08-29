// Perception — the world as the bot is allowed to know it.
//
// The view is a plain snapshot with no engine objects in it, and that restriction is doing real
// work. A behaviour that could reach into the scene would quietly grow a dependency on Phaser, on
// this map's construction order, on a sprite's private fields; a behaviour that can only read this
// struct stays a function of its inputs, testable at a keyboard and portable to a runtime that has
// never heard of a Phaser sprite. Everything engine-shaped is confined to the adapter that fills
// this in.
//
// The view is also the honest boundary of the bot's knowledge. If something is not here, the bot
// cannot cheat by consulting it — which is why mob health is present (it is drawn above their
// heads) and mob spawn timers are not.

import type { NavGraph } from "./bot-navigation";

export type BotFacing = "left" | "right";

export type BotSelfView = Readonly<{
  x: number;
  /** Feet, matching every other vertical value the runtime reports. */
  y: number;
  facing: BotFacing;
  vx: number;
  vy: number;
  airborne: boolean;
  support: "terrain" | "platform" | "climbable" | "air";
  airJumpsUsed: number;
  hp: number;
  maxHp: number;
  defeated: boolean;
  /** True while an attack animation owns the character; a fresh swing is refused. */
  attacking: boolean;
}>;

/** A thing worth hitting. Ids are instance-stable so a target survives between frames. */
export type BotThreatView = Readonly<{
  id: string;
  x: number;
  y: number;
  hp: number;
}>;

/** A thing worth walking over. Unsettled drops are still falling and move as they land. */
export type BotPickupView = Readonly<{
  id: string;
  x: number;
  y: number;
  settled: boolean;
}>;

export type BotWorldView = Readonly<{
  nowMs: number;
  deltaMs: number;
  self: BotSelfView;
  /** Live mobs only. A corpse is not a target and never reaches the bot. */
  threats: readonly BotThreatView[];
  pickups: readonly BotPickupView[];
  /** Whether the bag holds anything drinkable right now, not whether the package ships one. */
  healingCarried: boolean;
  /** False for a package with combat disabled, which makes every fighting behaviour decline. */
  combatEnabled: boolean;
  navigation: NavGraph;
  /** Walkable extent of the current map, which is what keeps a patrol on the map. */
  bounds: Readonly<{ left: number; right: number }>;
}>;

export function healthFraction(self: BotSelfView): number {
  if (!(self.maxHp > 0)) return 0;
  return Math.max(0, Math.min(1, self.hp / self.maxHp));
}

export function horizontalDistance(
  a: Readonly<{ x: number }>,
  b: Readonly<{ x: number }>,
): number {
  return Math.abs(a.x - b.x);
}

/**
 * Whether two feet stand close enough in height to trade blows.
 *
 * Combat in this runtime is resolved on foot level rather than on overlapping bodies, so a mob one
 * deck up is not a mob the character can hit no matter how close it looks on screen. Targeting
 * respects the same rule the damage does, otherwise the bot swings at the ceiling.
 */
export function sameFootLevel(
  a: Readonly<{ y: number }>,
  b: Readonly<{ y: number }>,
  toleranceUnits: number,
): boolean {
  return Math.abs(a.y - b.y) <= toleranceUnits;
}

/** Facing sign toward a point, with the current facing kept when already on top of it. */
export function facingToward(self: BotSelfView, targetX: number): BotFacing {
  if (targetX < self.x) return "left";
  if (targetX > self.x) return "right";
  return self.facing;
}
