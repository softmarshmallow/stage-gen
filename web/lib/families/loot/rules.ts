// The `loot` family, first half: what a kill drops.
//
// `[[loot_rules]]` is a family whose whole authored surface is numbers — a mob
// id, an item id, a chance and a quantity range — and the rule over them was
// welded into `dropLoot` in the platformer's scene, interleaved with resolving
// a catalog index and adding a sprite to the world. The rule is here; which
// catalog the item id names, and what a drop looks like once it is on the
// ground, are the consumer's.
//
// The roll is seeded rather than random, and the seed is the caller's, because
// a replay has to drop the same things twice. The family never asks where the
// seed came from.

/** One authored rule: this creature drops this item, this often, this many. */
export interface LootRule {
  readonly mob_id: string;
  readonly item_id: string;
  /** 0..1. A rule at 1.0 always drops; the comparison is `roll > chance` refuses. */
  readonly chance: number;
  readonly quantity_min: number;
  readonly quantity_max: number;
}

/** What one rule decided: a stack of one item id. */
export interface LootDrop {
  readonly itemId: string;
  readonly quantity: number;
}

/**
 * Turn the authored rules for one creature into the stacks it drops.
 *
 * One seed for every rule the creature carries, deliberately: that is what the
 * scene did, and it is the difference between "this creature's death was lucky"
 * and "each of its drops was rolled separately". Changing it is a balance
 * decision with an authored surface of its own, not an extraction.
 */
export function resolveLootDrops(
  rules: readonly LootRule[],
  mobId: string,
  seed: number,
): readonly LootDrop[] {
  const roll = seed / 0xffffffff;
  const drops: LootDrop[] = [];
  for (const rule of rules) {
    if (rule.mob_id !== mobId) continue;
    if (roll > rule.chance) continue;
    const span = rule.quantity_max - rule.quantity_min + 1;
    drops.push({ itemId: rule.item_id, quantity: rule.quantity_min + (seed % span) });
  }
  return Object.freeze(drops);
}

/**
 * Where the units of one stack land relative to the body that dropped them.
 *
 * Centred on the corpse and spread by a fixed gap, so a stack of one lands on
 * it and a stack of four straddles it evenly. Presentation in the sense that a
 * player only reads it as "things fell out", and a rule in the sense that the
 * spread decides which column each unit settles in.
 */
export function dropSpread(quantity: number, spacing: number): readonly number[] {
  const offsets: number[] = [];
  for (let index = 0; index < quantity; index += 1) {
    offsets.push((index - (quantity - 1) / 2) * spacing);
  }
  return Object.freeze(offsets);
}
