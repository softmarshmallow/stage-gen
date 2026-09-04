// The `inventory` family: a counted bag, and where a stack sits on a panel.
//
// Three bags existed. The platformer scene kept a `Map<string, number>` and
// two private methods over it; its HUD kept a *second* map, keyed by catalog
// index, with the slot-assignment rule written inside the drawing code in four
// places; and the room's reducer kept a `readonly string[]` used as a set, with
// its own add and remove written inline in `applyInteraction`.
//
// The ruling is that the room's set-shaped bag is this counted bag with every
// quantity 1 and no capacity — which is a fact about the room's *authoring*
// (`grant_item` grants one, `remove_item` takes the stack) and not a different
// model. So there is one bag here, quantities and all, and the room instantiates
// it with the unit grant.
//
// Two things that look like they belong here and do not:
//
//   - `selectedItem`. The room stores "which carried item is the player holding
//     over the cursor" beside its bag, which made it look like inventory state.
//     It is an interaction latch: it is set by a click, cleared by *every*
//     interaction whether or not an item was involved, and no rule about what
//     is carried ever reads it. It stays with the room's interaction state.
//   - The panel's geometry. Where the slots are on the sheet is `ui`; which
//     slot a stack occupies is a bag question, and that is the half that moves
//     here.

/** What the player carries: item id → how many, with absent meaning none. */
export type CountedBag = ReadonlyMap<string, number>;

export const EMPTY_BAG: CountedBag = Object.freeze(new Map<string, number>());

/**
 * What the bag refuses, and why.
 *
 * `"quantity"` is a caller asking for a non-positive or non-finite count —
 * always a bug at the call site rather than a game state, which is why both
 * previous implementations silently returned instead. It is still named, so a
 * consumer that wants to hear about it can.
 */
export type BagRefusal = "quantity" | "capacity" | "absent";

export interface BagPolicy {
  /**
   * The most units this bag will hold, or null for a bag with no limit.
   *
   * Null is not a missing value: a room's bag genuinely has no capacity — the
   * solvability proof searches a state space where carrying is unbounded — and
   * a bag that refuses is a different bag from one that cannot.
   */
  readonly capacity: number | null;
}

export const UNLIMITED: BagPolicy = Object.freeze({ capacity: null });

export interface BagVerdict {
  /** The bag after the operation; the same object when nothing moved. */
  readonly bag: CountedBag;
  /** How many units actually moved. Zero means the operation was refused. */
  readonly moved: number;
  /** Why nothing (or not everything) moved, or null when the whole request landed. */
  readonly refusal: BagRefusal | null;
}

/** How many of one item the bag holds. */
export function carried(bag: CountedBag, itemId: string): number {
  return bag.get(itemId) ?? 0;
}

/** Every unit in the bag, counted. Capacity is measured against this. */
export function totalCarried(bag: CountedBag): number {
  let total = 0;
  for (const quantity of bag.values()) total += quantity;
  return total;
}

/**
 * The bag's item ids in a stable order.
 *
 * Sorted rather than insertion-ordered, because both consumers that render a
 * bag render it as a list and a list whose order depends on pickup history is
 * not reproducible across a replay that collects the same items in a different
 * sequence.
 */
export function bagItemIds(bag: CountedBag): readonly string[] {
  return [...bag.keys()].sort();
}

/** Every stack, sorted by item id: the shape a readout or a digest wants. */
export function bagEntries(bag: CountedBag): readonly (readonly [string, number])[] {
  return bagItemIds(bag).map((itemId) => [itemId, bag.get(itemId) as number] as const);
}

/** A bag holding one of each named item: the room's set, as a counted bag. */
export function bagOfOne(itemIds: Iterable<string>): CountedBag {
  const bag = new Map<string, number>();
  for (const itemId of itemIds) bag.set(itemId, 1);
  return Object.freeze(bag);
}

function normalizedQuantity(quantity: number): number {
  if (!Number.isFinite(quantity) || quantity <= 0) return 0;
  return Math.floor(quantity);
}

/**
 * Put units in the bag.
 *
 * A capacity refuses the whole request rather than filling to the brim: half a
 * stack arriving is a state neither authored form can describe, and a partial
 * grant would make "did the player get the quest item" depend on how full the
 * bag was.
 */
export function grant(
  bag: CountedBag,
  itemId: string,
  quantity: number,
  policy: BagPolicy = UNLIMITED,
): BagVerdict {
  const wanted = normalizedQuantity(quantity);
  if (wanted <= 0) return { bag, moved: 0, refusal: "quantity" };
  if (policy.capacity !== null && totalCarried(bag) + wanted > policy.capacity) {
    return { bag, moved: 0, refusal: "capacity" };
  }
  const next = new Map(bag);
  next.set(itemId, carried(bag, itemId) + wanted);
  return { bag: Object.freeze(next), moved: wanted, refusal: null };
}

/**
 * Spend units from the bag, taking as many as are there.
 *
 * Partial *here* rather than all-or-nothing, and for the same reason the grant
 * is not: spending is the half a consumer has already checked — a throw asks
 * whether a round is carried before it fires — so the arithmetic is a floor at
 * zero and never a surprise. An emptied stack leaves the bag rather than
 * sitting at zero, so `bagItemIds` is the carried list and not a history.
 */
export function consume(bag: CountedBag, itemId: string, quantity: number): BagVerdict {
  const wanted = normalizedQuantity(quantity);
  if (wanted <= 0) return { bag, moved: 0, refusal: "quantity" };
  const held = carried(bag, itemId);
  const spent = Math.min(held, wanted);
  if (spent <= 0) return { bag, moved: 0, refusal: "absent" };
  const next = new Map(bag);
  if (held - spent > 0) next.set(itemId, held - spent);
  else next.delete(itemId);
  return { bag: Object.freeze(next), moved: spent, refusal: null };
}

/**
 * Which panel slot a catalog kind occupies.
 *
 * The rule the platformer's HUD had written inline in four places — the add,
 * the remove, and twice in the snapshot, where the same expression was
 * recomputed to report what the icon was *supposed* to be beside where it is.
 * It is a bag rule and not a drawing rule: it decides that a stack keeps one
 * slot for the life of a run, so a potion picked up, spent and picked up again
 * comes back to the same square.
 */
export function slotByKind(kindIndex: number, slotCount: number): number {
  if (!Number.isInteger(kindIndex) || kindIndex < 0) {
    throw new Error("inventory slot assignment requires a nonnegative kind index");
  }
  if (!Number.isInteger(slotCount) || slotCount <= 0) {
    throw new Error("inventory slot assignment requires at least one slot");
  }
  return kindIndex % slotCount;
}
