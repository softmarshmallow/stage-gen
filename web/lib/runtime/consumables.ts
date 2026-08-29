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
