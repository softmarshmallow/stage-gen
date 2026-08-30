// Who a swing connects with.
//
// This was eight lines inside `PreparedStageScene.updatePlayer`, sitting between the loop that
// found a mob and the block that applied damage to it — which meant the one rule that decides
// whether a fight is fair could not be tested without a Phaser scene, a heightmap and a loaded
// package. It is arithmetic over positions, so it lives here with the other arithmetic.
//
// Only the instant arm lives here. A thrown object's collision belongs to the object, in
// `projectile-flight.ts`, because it is answered against where the shot has travelled to rather
// than where the character is standing.

import { attackFootLevelsOverlap } from "./combat";
import type { WeaponClassProfile } from "./weapon-class";

/** The part of a target an instant strike actually reads. */
export type StrikeTarget = Readonly<{
  x: number;
  /** Ground contact point, which is what `sprite.y` is for every actor in this scene. */
  footY: number;
}>;

export type InstantStrikeInput = Readonly<{
  profile: WeaponClassProfile;
  attackerX: number;
  attackerFootY: number;
  dirSign: 1 | -1;
  tilePixels: number;
  targets: readonly StrikeTarget[];
}>;

/**
 * Indices of the targets one swing connects with, in the caller's order.
 *
 * The band is centred half a reach ahead of the character rather than on it, which is why a swing
 * covers roughly 0.7 tiles behind and 2.1 ahead rather than 1.4 either way. That asymmetry is the
 * shipped behaviour and it is deliberate: a swing that reached as far backwards as forwards would
 * let a player kill something they had already walked past without turning round.
 *
 * Returns an empty array for a class that does not strike instantly, so the caller can branch on
 * the delivery kind once rather than at every call site.
 */
export function resolveInstantStrike(input: InstantStrikeInput): readonly number[] {
  const { profile, attackerX, attackerFootY, dirSign, tilePixels, targets } = input;
  if (profile.delivery.kind !== "instant") return Object.freeze([]);
  if (!Number.isFinite(tilePixels) || tilePixels <= 0) {
    throw new Error("strike resolution requires a positive tile size");
  }

  const reach = tilePixels * profile.delivery.reachTiles;
  const bandCenterX = attackerX + dirSign * reach * 0.5;
  // The vertical rule is asked for its targeting tolerance rather than its own tiles, so a class
  // whose reach is described some other way still answers the same question here.
  const verticalTiles =
    profile.verticalReach.kind === "foot_band"
      ? profile.verticalReach.tiles
      : profile.verticalReach.targetingToleranceTiles;

  const hits: number[] = [];
  for (let index = 0; index < targets.length; index += 1) {
    const target = targets[index];
    if (Math.abs(target.x - bandCenterX) >= reach) continue;
    if (!attackFootLevelsOverlap(attackerFootY, target.footY, tilePixels, verticalTiles)) {
      continue;
    }
    hits.push(index);
    if (hits.length >= profile.maxTargetsPerAction) break;
  }
  return Object.freeze(hits);
}
