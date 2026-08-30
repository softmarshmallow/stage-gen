// The adapter — the one place the prepared scene and the bot are allowed to meet.
//
// Everything under `bot-*.ts` is written against plain values, and this file is what makes that
// affordable: it reads the scene's own vocabulary — heightmap columns, upper platforms, climbable
// zones, a player snapshot — and produces the navigation graph and the world view. Porting the bot
// to another runtime means rewriting this file and nothing else beneath it.
//
// The direction of the dependency matters. The bot never reaches into the scene; the scene fills
// the bot's inputs. That is what keeps the bot testable at a keyboard, and what stops a behaviour
// from quietly learning about a sprite.

import {
  buildNavGraph,
  type MovementCapabilities,
  type NavGraph,
} from "./bot-navigation";
import type {
  BotPickupView,
  BotSelfView,
  BotTerrainProfile,
  BotThreatView,
  BotWeaponBand,
  BotWorldView,
} from "./bot-view";
import type { PlayerStateSnapshot } from "./player";
// Imported from the vocabulary module rather than the controller: `player.ts` loads Phaser, and
// nothing beneath this adapter may need a browser to be tested.
import { PLAYER_ATTACK_STATES } from "./player-state";
import { terrainSurfaceY } from "./terrain";
import type { ProjectileProfile } from "./projectile-class";
import {
  targetingToleranceUnits,
  type WeaponClassProfile,
} from "./weapon-class";
import type { ClimbableZone, UpperPlatform } from "./vertical";

/**
 * Build the traversal graph for the map the scene has just finished constructing.
 *
 * Called on map entry rather than per frame. The graph describes terrain and declared geometry,
 * neither of which changes while a map is being played, and rebuilding it every frame would spend
 * a jump proof per link on an answer that cannot have moved.
 */
export function preparedNavGraph(input: Readonly<{
  /** Authored occupancy heights, one per column, exactly as the scene holds them. */
  heights: readonly number[];
  tileUnits: number;
  baselineY: number;
  platforms: readonly UpperPlatform[];
  climbables: readonly ClimbableZone[];
  capabilities: MovementCapabilities;
}>): NavGraph {
  return buildNavGraph({
    columnSurfaceY: input.heights.map((height) =>
      terrainSurfaceY(height, input.tileUnits, input.baselineY),
    ),
    tileUnits: input.tileUnits,
    platforms: input.platforms.map((platform) => ({
      id: platform.id,
      left: platform.left,
      right: platform.right,
      deckY: platform.deckY,
    })),
    climbables: input.climbables.map((climbable) => ({
      id: climbable.id,
      centerX: climbable.centerX,
      upperDeckY: climbable.upperDeckY,
      lowerSurfaceY: climbable.lowerSurfaceY,
    })),
    capabilities: input.capabilities,
  });
}

/**
 * Translate the controller's own snapshot into what the bot is allowed to see.
 *
 * `attacking` reports that the attack animation owns the character, which is broader than the
 * snapshot's `attackActive` — that one names the few frames the hit window is open. The bot wants
 * the broader fact, because it describes when a swing is already under way.
 */
export function preparedBotSelfView(snapshot: PlayerStateSnapshot): BotSelfView {
  return Object.freeze({
    x: snapshot.x,
    y: snapshot.y,
    facing: snapshot.facing,
    vx: snapshot.vx,
    vy: snapshot.vy,
    airborne: snapshot.airborne,
    support: snapshot.support,
    airJumpsUsed: snapshot.airJumpsUsed,
    hp: snapshot.hp,
    maxHp: snapshot.maxHp,
    defeated: snapshot.defeated,
    // Every attack state, not just the swing: a casting character is as committed as a swinging
    // one, and the behaviours read this to decide whether the animation owns the character.
    attacking: PLAYER_ATTACK_STATES.has(snapshot.state),
  });
}

/**
 * Project a weapon class onto the distances the bot reasons in.
 *
 * Here rather than on the profile itself because the tile is the scene's constant, not the table's,
 * and this file is the one place the two vocabularies are allowed to meet. Every number the bot
 * uses to decide where to stand now originates in the same record the scene resolves damage from.
 */
export function preparedBotWeaponBand(
  profile: WeaponClassProfile,
  tilePixels: number,
  projectile: ProjectileProfile | null = null,
  playerHeightUnits = 0,
): BotWeaponBand {
  return Object.freeze({
    minimumUnits: profile.standOffTiles.minimum * tilePixels,
    approachUnits: profile.standOffTiles.approach * tilePixels,
    maximumUnits: profile.standOffTiles.maximum * tilePixels,
    verticalToleranceUnits: targetingToleranceUnits(profile, tilePixels),
    requiresAmmo: profile.ammoKind !== null,
    // Only a class that actually throws declares one, and only then does the flight path exist to
    // be blocked. The height comes from the object rather than the weapon for the same reason
    // everything else about the flight does.
    releaseHeightUnits:
      profile.delivery.kind === "projectile" && projectile !== null
        ? projectile.flight.releaseHeightFraction * playerHeightUnits
        : null,
  });
}

export function preparedBotWorldView(input: Readonly<{
  nowMs: number;
  deltaMs: number;
  player: PlayerStateSnapshot;
  threats: readonly BotThreatView[];
  pickups: readonly BotPickupView[];
  healingCarried: boolean;
  ammoCarried: boolean;
  weaponBand: BotWeaponBand;
  combatEnabled: boolean;
  navigation: NavGraph;
  terrain: BotTerrainProfile;
  worldWidth: number;
}>): BotWorldView {
  return Object.freeze({
    nowMs: input.nowMs,
    deltaMs: input.deltaMs,
    self: preparedBotSelfView(input.player),
    threats: Object.freeze([...input.threats]),
    pickups: Object.freeze([...input.pickups]),
    healingCarried: input.healingCarried,
    ammoCarried: input.ammoCarried,
    weaponBand: input.weaponBand,
    combatEnabled: input.combatEnabled,
    navigation: input.navigation,
    terrain: input.terrain,
    bounds: Object.freeze({ left: 0, right: input.worldWidth }),
  });
}
