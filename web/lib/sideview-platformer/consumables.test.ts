import { describe, expect, test } from "bun:test";
import {
  AMMO_ITEM_KIND,
  HEALING_ITEM_KIND,
  hasHealingConsumable,
  hasThrowableAmmo,
  selectAmmoItemId,
  selectHealingItemId,
} from "./consumables";

const CATALOG = Object.freeze([
  { item_id: "sunleaf_coin", item_kind: "currency" },
  { item_id: "rosehip_tart", item_kind: HEALING_ITEM_KIND },
  { item_id: "spindlehook", item_kind: "traversal_tool" },
  { item_id: "honey_draught", item_kind: HEALING_ITEM_KIND },
  { item_id: "castle_moonkey", item_kind: "key_item" },
]);

describe("healing consumable selection", () => {
  test("spends the first carried healing item in catalog order", () => {
    // Catalog order, not pickup order or largest stack: the deterministic transcript has to
    // reproduce the same drink from the same state on every replay.
    const inventory = new Map([
      ["honey_draught", 3],
      ["rosehip_tart", 1],
    ]);
    expect(selectHealingItemId(CATALOG, inventory)).toBe("rosehip_tart");
  });

  test("falls through to the next stack once one is exhausted", () => {
    expect(
      selectHealingItemId(CATALOG, new Map([["rosehip_tart", 0], ["honey_draught", 2]])),
    ).toBe("honey_draught");
  });

  test("never spends an item whose role is not drinkable", () => {
    const inventory = new Map([
      ["sunleaf_coin", 40],
      ["castle_moonkey", 1],
      ["spindlehook", 2],
    ]);
    expect(selectHealingItemId(CATALOG, inventory)).toBeNull();
  });

  test("carrying nothing is an ordinary outcome, not a failure", () => {
    expect(selectHealingItemId(CATALOG, new Map())).toBeNull();
    expect(selectHealingItemId([], new Map([["rosehip_tart", 5]]))).toBeNull();
  });

  test("reports whether a package ships anything drinkable at all", () => {
    expect(hasHealingConsumable(CATALOG)).toBe(true);
    expect(
      hasHealingConsumable([{ item_id: "sunleaf_coin", item_kind: "currency" }]),
    ).toBe(false);
  });
});

describe("which carried item a throw spends", () => {
  const CATALOG = [
    { item_id: "gold_coin", item_kind: "currency" },
    { item_id: "climbing_hook", item_kind: "traversal_tool" },
    { item_id: "throwing_stone", item_kind: AMMO_ITEM_KIND },
    { item_id: "river_pebble", item_kind: AMMO_ITEM_KIND },
  ];

  test("the first item carrying the role is what a shot spends", () => {
    expect(selectAmmoItemId(CATALOG)).toBe("throwing_stone");
  });

  test("selection is catalog-ordered, so a replay spends the same thing twice", () => {
    expect(selectAmmoItemId([...CATALOG].reverse())).toBe("river_pebble");
  });

  test("a package with nothing throwable answers null", () => {
    expect(selectAmmoItemId(CATALOG.slice(0, 2))).toBeNull();
    expect(hasThrowableAmmo(CATALOG.slice(0, 2))).toBe(false);
    expect(hasThrowableAmmo(CATALOG)).toBe(true);
  });

  test("what is spent is an inventory item, never the drawn projectile", () => {
    // The two are different families on purpose: a quiver fits in a bag and the arrow in the air
    // is a generated sprite. Nothing here reads the projectile catalog.
    expect(selectAmmoItemId(CATALOG)).toBe("throwing_stone");
    expect(CATALOG.some((entry) => entry.item_kind === AMMO_ITEM_KIND)).toBe(true);
  });
});
