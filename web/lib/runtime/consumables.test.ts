import { describe, expect, test } from "bun:test";
import {
  HEALING_ITEM_KIND,
  hasHealingConsumable,
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
