// Which kits a developer may play one published run with, and how that choice is spelled.
//
// The problem this exists for: a package's weapon class and the character's drawn equipment are one
// decision, so changing the kit in `gameplay.toml` means changing `content/player.toml` too, and
// that field is inside the concept node's cache digest. Trying a different kit therefore costs a
// re-render of the whole player domain. That price is correct for a package being *authored* - the
// artwork genuinely changes - and absurd for a developer who only wants to see how the other arm
// plays on the map in front of them.
//
// So this is an override and never an authored fact. Three properties keep it honest:
//
//   1. It only ever *selects*. Every weapon class here is a name Python published, every projectile
//      is an entry the run's own manifest carries, and every number still comes from
//      `weapon-class.ts` and `projectile-class.ts`. Nothing here invents a binding the contract
//      could not have expressed - in particular a throwing kit is offered only when the run
//      actually shipped something to throw, because a runtime that picked a round for you would be
//      authoring the package fact `projectile_id`.
//   2. It never reaches the published contract. The scene keeps the parsed `gameplay` object
//      exactly as it was validated and applies the override where the runtime *decides*, so the
//      manifest, its digests, and every artifact stay the bytes the pipeline wrote.
//   3. It cannot express something the package validator would have refused. `player_equipment_mismatch`
//      is a Python check over a field the manifest does not publish, so the runtime genuinely
//      cannot re-run it - which is why an override is a developer affordance and not a shortcut
//      around authoring. What is drawn does not change; only what the drawn character does.

import type { WeaponClass } from "./weapon-class";
import { WEAPON_CLASSES, weaponClassProfile } from "./weapon-class";

/** One playable combination of a weapon class and, when the class throws, the round it throws. */
export type DeveloperKit = Readonly<{
  weaponClass: WeaponClass;
  projectileId: string | null;
}>;

/** The shape this needs from a published projectile; the catalog entry carries much more. */
export type PublishedProjectile = Readonly<{ projectile_id: string }>;

/** A kit's stable identity for a list key and a test id. `class` or `class:projectile`. */
export function developerKitToken(kit: DeveloperKit): string {
  return kit.projectileId === null ? kit.weaponClass : `${kit.weaponClass}:${kit.projectileId}`;
}

/** Kit identity. Two kits are the same when they name the same class and the same round. */
export function sameDeveloperKit(left: DeveloperKit, right: DeveloperKit): boolean {
  return left.weaponClass === right.weaponClass && left.projectileId === right.projectileId;
}

/**
 * Every kit this particular run can actually be played with, the authored one first.
 *
 * Derived from what the run published rather than from the vocabulary, because the vocabulary
 * describes what a package *may* declare and this has to describe what these bytes can do. A run
 * generated before projectiles existed offers exactly one kit, and the console correctly has
 * nothing to switch to - which is a true report, not a broken feature.
 */
export function selectableDeveloperKits(input: {
  publishedWeaponClass: WeaponClass;
  publishedProjectileId: string | null;
  projectileCatalog: readonly PublishedProjectile[];
  publishedMotionStates: Readonly<Record<string, unknown>>;
}): readonly DeveloperKit[] {
  const published: DeveloperKit = Object.freeze({
    weaponClass: input.publishedWeaponClass,
    projectileId: input.publishedProjectileId,
  });
  const kits: DeveloperKit[] = [published];

  const posePublished = (weaponClass: WeaponClass): boolean =>
    input.publishedMotionStates[weaponClassProfile(weaponClass).motionState] !== undefined;

  for (const weaponClass of WEAPON_CLASSES) {
    if (!posePublished(weaponClass)) continue;
    const throws = weaponClassProfile(weaponClass).delivery.kind === "projectile";
    // A throwing class needs a round, and the only rounds that exist are the ones this run drew.
    const rounds: readonly (string | null)[] = throws
      ? input.projectileCatalog.map((entry) => entry.projectile_id)
      : [null];
    for (const projectileId of rounds) {
      const kit: DeveloperKit = Object.freeze({ weaponClass, projectileId });
      if (!kits.some((existing) => sameDeveloperKit(existing, kit))) kits.push(kit);
    }
  }
  return Object.freeze(kits);
}

/**
 * The next kit in the cycle, for the in-scene key.
 *
 * Wraps, and returns the first kit for anything it does not recognise, so the key always advances
 * to something playable rather than sticking on an override that is no longer offered.
 */
export function nextDeveloperKit(
  current: DeveloperKit | null,
  selectable: readonly DeveloperKit[],
): DeveloperKit | null {
  if (selectable.length === 0) return null;
  if (current === null) return selectable.length > 1 ? selectable[1] : selectable[0];
  const index = selectable.findIndex((kit) => sameDeveloperKit(kit, current));
  return selectable[index === -1 ? 0 : (index + 1) % selectable.length];
}

/** One short clause naming the kit, for the debug overlay and the switch notice. Never parsed. */
export function developerKitLabel(kit: DeveloperKit): string {
  const throwing = weaponClassProfile(kit.weaponClass).delivery.kind === "projectile";
  return throwing && kit.projectileId !== null
    ? `${kit.weaponClass} (${kit.projectileId})`
    : kit.weaponClass;
}
