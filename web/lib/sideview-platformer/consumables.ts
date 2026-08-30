// Which carried item a consumable request spends.
//
// The generator publishes an item's identity and role — `item_kind` on every catalog entry — and
// publishes no numbers for it. That split is the architecture rule: the recipe decides that a
// package ships a rosehip tart and that a tart is the thing you drink, while the runtime decides
// what drinking one is worth. So the selection below reads `item_kind` and nothing else; the
// restore amount lives with the other combat numbers.
//
// Selection is by catalog order, not by quantity or by pickup time, because the runtime's
// deterministic transcript has to reproduce the same drink from the same state on every replay.

/** The catalog role the runtime treats as drinkable. Mirrors `ItemContent.item_kind` in Python. */
export const HEALING_ITEM_KIND = "healing_consumable";

/** The part of a manifest item entry that consumable selection actually reads. */
export type ConsumableCatalogEntry = Readonly<{
  item_id: string;
  item_kind: string;
}>;

/**
 * The first healing consumable the player is actually carrying, or null when they carry none.
 *
 * Returning null is an ordinary outcome, not a failure: a package is free to ship no healing item
 * at all, and a player is free to run out of the one it ships.
 */
export function selectHealingItemId(
  catalog: readonly ConsumableCatalogEntry[],
  inventory: ReadonlyMap<string, number>,
): string | null {
  for (const entry of catalog) {
    if (entry.item_kind !== HEALING_ITEM_KIND) continue;
    const carried = inventory.get(entry.item_id) ?? 0;
    if (Number.isFinite(carried) && carried >= 1) return entry.item_id;
  }
  return null;
}

/** Whether a package ships anything drinkable at all, independent of what is carried. */
export function hasHealingConsumable(
  catalog: readonly ConsumableCatalogEntry[],
): boolean {
  return catalog.some((entry) => entry.item_kind === HEALING_ITEM_KIND);
}

// --- Ammunition ------------------------------------------------------------------------------

/** The catalog role the runtime treats as throwable. Mirrors `ItemContent.item_kind` in Python. */
export const AMMO_ITEM_KIND = "throwable_ammo";

/**
 * Which carried item a throwing class spends per shot.
 *
 * Deliberately not the projectile. What flies is a drawn object from the projectile catalog and is
 * not something anyone picks up; what is *spent* is an inventory item, and a game is free to make
 * those unrelated — a quiver of arrows and the arrow that appears in the air are the same idea but
 * not the same record, and one of them has to fit in a bag.
 *
 * Catalog-ordered for the same determinism reason the healing selection is, and it ignores the bag
 * for the same reason the projectile's texture is resolved at world build: this answers *what*
 * would be spent, not whether the player can spend it right now.
 */
export function selectAmmoItemId(
  catalog: readonly ConsumableCatalogEntry[],
): string | null {
  for (const entry of catalog) {
    if (entry.item_kind === AMMO_ITEM_KIND) return entry.item_id;
  }
  return null;
}

/** Whether a package ships anything throwable at all, independent of what is carried. */
export function hasThrowableAmmo(
  catalog: readonly ConsumableCatalogEntry[],
): boolean {
  return catalog.some((entry) => entry.item_kind === AMMO_ITEM_KIND);
}
