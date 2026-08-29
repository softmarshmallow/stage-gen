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
import type { BotPickupView, BotSelfView, BotThreatView, BotWorldView } from "./bot-view";
import type { PlayerStateSnapshot } from "./player";
import { terrainSurfaceY } from "./terrain";
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
    attacking: snapshot.state === "attack",
  });
}

export function preparedBotWorldView(input: Readonly<{
  nowMs: number;
  deltaMs: number;
  player: PlayerStateSnapshot;
  threats: readonly BotThreatView[];
  pickups: readonly BotPickupView[];
  healingCarried: boolean;
  combatEnabled: boolean;
  navigation: NavGraph;
  worldWidth: number;
}>): BotWorldView {
  return Object.freeze({
    nowMs: input.nowMs,
    deltaMs: input.deltaMs,
    self: preparedBotSelfView(input.player),
    threats: Object.freeze([...input.threats]),
    pickups: Object.freeze([...input.pickups]),
    healingCarried: input.healingCarried,
    combatEnabled: input.combatEnabled,
    navigation: input.navigation,
    bounds: Object.freeze({ left: 0, right: input.worldWidth }),
  });
}
