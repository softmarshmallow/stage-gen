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

/**
 * The distance band a weapon class wants a target in, in world units.
 *
 * Projected by the scene from the runtime's weapon-class table rather than restated here, because
 * the reach the bot aims for and the reach the scene resolves are the same number and used to be
 * two. `minimum` is zero for a class that has no distance too close, which is what keeps a melee
 * policy walking all the way in.
 */
export type BotWeaponBand = Readonly<{
  minimumUnits: number;
  /** The distance the policy walks in to. Equal to `maximumUnits` for a class that gains nothing by closing. */
  approachUnits: number;
  maximumUnits: number;
  verticalToleranceUnits: number;
  /** Whether the class spends something to attack, and therefore can run out. */
  requiresAmmo: boolean;
  /**
   * How high above the character's feet a thrown object leaves, or null for a class that throws
   * nothing.
   *
   * The number a swing has no use for and a throw cannot do without: it is the height the flight
   * path sits at, and therefore the height at which the terrain either clears or does not.
   */
  releaseHeightUnits: number | null;
}>;

/**
 * The ground the character and its targets stand on, one surface height per column.
 *
 * Plain numbers rather than a query function, so the whole view stays a serialisable snapshot and a
 * behaviour remains a function of its inputs. The navigation graph is built from the same profile
 * but cannot answer this question: its nodes are walkable spans, and a projectile does not care
 * where a character could stand — it cares what is in the way at the height it is flying.
 */
export type BotTerrainProfile = Readonly<{
  /** Surface y per column, in world units. Index is the column, not the pixel. */
  columnSurfaceY: readonly number[];
  tileUnits: number;
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
  /** Whether the bag holds a round right now. Always true for a class that spends nothing. */
  ammoCarried: boolean;
  /** How far this class fights from, and how far off the level it will still engage. */
  weaponBand: BotWeaponBand;
  /** False for a package with combat disabled, which makes every fighting behaviour decline. */
  combatEnabled: boolean;
  navigation: NavGraph;
  /** What the ground does between here and there. Empty when the scene has no terrain to report. */
  terrain: BotTerrainProfile;
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

/**
 * Whether a flat shot from one point to another would reach, or hit the ground on the way.
 *
 * The rule the projectile itself obeys, asked one frame early: a shot dies where its own height
 * meets the terrain surface, so a straight line at the release height either clears every column
 * between the two or it does not. Sampled per column, because the terrain is per column and a
 * midpoint test would fly straight through a one-column pillar.
 *
 * This exists because of a real softlock. Targeting used to ask only how far away a creature was
 * and how close its feet were to the character's; a creature standing on a ledge satisfied both
 * while the ledge face stood between them, so every throw died in the wall and the engage
 * behaviour — which outranks pursuit — proposed the same throw forever. Declining is what lets
 * pursuit take the frame and walk the character somewhere it can actually shoot from.
 *
 * The character's own column is skipped: it is standing on that ground, not shooting through it.
 */
export function lineOfFireClear(
  terrain: BotTerrainProfile,
  fromX: number,
  toX: number,
  flightY: number,
): boolean {
  const { columnSurfaceY, tileUnits } = terrain;
  // A scene that reports no terrain blocks nothing. Refusing every shot would be worse than the
  // defect this prevents.
  if (columnSurfaceY.length === 0 || !(tileUnits > 0)) return true;
  const first = Math.floor(Math.min(fromX, toX) / tileUnits);
  const last = Math.floor(Math.max(fromX, toX) / tileUnits);
  const standing = Math.floor(fromX / tileUnits);
  for (let column = first; column <= last; column += 1) {
    if (column === standing) continue;
    const index = Math.min(Math.max(column, 0), columnSurfaceY.length - 1);
    const surfaceY = columnSurfaceY[index];
    // y grows downward, so the shot is in the air only while it is above the surface.
    if (flightY >= surfaceY) return false;
  }
  return true;
}

/** Facing sign toward a point, with the current facing kept when already on top of it. */
export function facingToward(self: BotSelfView, targetX: number): BotFacing {
  if (targetX < self.x) return "left";
  if (targetX > self.x) return "right";
  return self.facing;
}
