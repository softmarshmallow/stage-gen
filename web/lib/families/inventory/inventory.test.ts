import { describe, expect, test } from "bun:test";
import {
  bagEntries,
  bagItemIds,
  bagOfOne,
  carried,
  consume,
  EMPTY_BAG,
  grant,
  slotByKind,
  totalCarried,
  UNLIMITED,
  type CountedBag,
} from "./bag";
import { NO_INVENTORY_PANEL, type InventoryPanelView } from "./panel";
import { parseInventoryBlock } from "./manifest";

// --- E4: one bag, two genres that had written it twice ---------------------------------------

describe("E4: the inventory family instantiated into two shapes", () => {
  test("a platformer-shaped bag: quantities, a spend per shot, and a stack that empties", () => {
    // The bag the run opens with: `[player].starting_item_ids`, one of each.
    let bag: CountedBag = bagOfOne(["paper_dart", "welcome_tart"]);
    // A loot drop lands, then a quest hands over three at once.
    bag = grant(bag, "paper_dart", 1).bag;
    bag = grant(bag, "castle_moonkey", 3).bag;
    expect(bagEntries(bag)).toEqual([
      ["castle_moonkey", 3],
      ["paper_dart", 2],
      ["welcome_tart", 1],
    ]);
    expect(totalCarried(bag)).toBe(6);

    // Two throws, and the second empties the stack out of the bag rather than
    // leaving a zero behind — which is what makes `bagItemIds` the carried list.
    const first = consume(bag, "paper_dart", 1);
    expect(first.moved).toBe(1);
    const second = consume(first.bag, "paper_dart", 1);
    expect(carried(second.bag, "paper_dart")).toBe(0);
    expect(bagItemIds(second.bag)).toEqual(["castle_moonkey", "welcome_tart"]);

    // A third throw is refused by name rather than silently doing nothing.
    expect(consume(second.bag, "paper_dart", 1).refusal).toBe("absent");
  });

  test("a room-shaped bag: the same bag with every quantity one and no capacity", () => {
    // The room's authored vocabulary grants one and removes the stack, which is
    // the whole of what made its set look like a different model.
    let bag: CountedBag = EMPTY_BAG;
    bag = grant(bag, "brass_key", 1, UNLIMITED).bag;
    bag = grant(bag, "oil_can", 1, UNLIMITED).bag;
    expect(bagItemIds(bag)).toEqual(["brass_key", "oil_can"]);
    // `remove_item` takes the stack, however many are in it. With unit grants
    // that is one, which is why a set was ever enough here.
    bag = consume(bag, "brass_key", carried(bag, "brass_key")).bag;
    expect(bagItemIds(bag)).toEqual(["oil_can"]);
    // And a set is exactly what a unit-granted bag reads back as.
    expect(bagEntries(bag)).toEqual([["oil_can", 1]]);
  });
});

// --- the capacity the room does not have, and the refusal it buys ----------------------------

describe("capacity", () => {
  test("a full bag refuses the whole grant rather than filling to the brim", () => {
    const bag = grant(EMPTY_BAG, "coin", 3, { capacity: 4 }).bag;
    const refused = grant(bag, "gem", 2, { capacity: 4 });
    expect(refused.moved).toBe(0);
    expect(refused.refusal).toBe("capacity");
    // The refused bag is the bag it was handed, object identity included, so a
    // caller cannot accidentally publish a copy as a change.
    expect(refused.bag).toBe(bag);
    // And the request that does fit lands whole.
    expect(grant(bag, "gem", 1, { capacity: 4 }).moved).toBe(1);
  });

  test("no capacity is a bag that cannot refuse, not a missing number", () => {
    let bag: CountedBag = EMPTY_BAG;
    for (let index = 0; index < 500; index += 1) bag = grant(bag, "pebble", 1).bag;
    expect(carried(bag, "pebble")).toBe(500);
  });

  test("a nonsense quantity is refused by name on both sides", () => {
    expect(grant(EMPTY_BAG, "coin", 0).refusal).toBe("quantity");
    expect(grant(EMPTY_BAG, "coin", Number.NaN).refusal).toBe("quantity");
    expect(consume(bagOfOne(["coin"]), "coin", -1).refusal).toBe("quantity");
  });

  test("a fractional grant floors, which is what both consumers already did", () => {
    expect(carried(grant(EMPTY_BAG, "coin", 2.9).bag, "coin")).toBe(2);
  });
});

// --- the slot rule that left the HUD ---------------------------------------------------------

describe("slot assignment", () => {
  test("a stack keeps one slot for the life of a run", () => {
    expect(slotByKind(0, 8)).toBe(0);
    expect(slotByKind(7, 8)).toBe(7);
    // The wrap the platformer's panel has always had: a catalog longer than the
    // grid shares squares, which is a design problem in the package and not a
    // failure here.
    expect(slotByKind(9, 8)).toBe(1);
  });

  test("and asking for a slot on a panel with none is refused rather than divided by zero", () => {
    expect(() => slotByKind(0, 0)).toThrow("at least one slot");
    expect(() => slotByKind(-1, 8)).toThrow("nonnegative kind index");
  });
});

// --- the port, and the subtraction (E7) ------------------------------------------------------

describe("the panel port", () => {
  test("the bag mirrors a count rather than a delta, so a grant of three is one call", () => {
    const calls: string[] = [];
    const panel: InventoryPanelView = {
      setSlot: (slot, kind, count) => calls.push(`${slot}:${kind}:${count}`),
    };
    let bag: CountedBag = EMPTY_BAG;
    const mirror = (itemId: string, kindIndex: number) =>
      panel.setSlot(slotByKind(kindIndex, 8), kindIndex, carried(bag, itemId));
    bag = grant(bag, "dart", 3).bag;
    mirror("dart", 2);
    bag = consume(bag, "dart", 3).bag;
    mirror("dart", 2);
    expect(calls).toEqual(["2:2:3", "2:2:0"]);
  });

  test("E7: a bag with nothing drawing it behaves identically", () => {
    // The subtraction at this family's grain: the panel is a port, so removing
    // it removes drawing and nothing else.
    const bag = grant(EMPTY_BAG, "dart", 2).bag;
    NO_INVENTORY_PANEL.setSlot(slotByKind(2, 8), 2, carried(bag, "dart"));
    expect(bagEntries(bag)).toEqual([["dart", 2]]);
  });
});

// --- the block, and the refusal ---------------------------------------------------------------

describe("the block the family gates for itself", () => {
  test("a moved block is refused by name, from the family that could not go on", () => {
    expect(() =>
      parseInventoryBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow(
      'manifest block "gameplay" is published as platformer-gameplay-block-v2; this build reads platformer-gameplay-block-v1',
    );
  });

  test("and the version this build reads is an answer", () => {
    expect(
      parseInventoryBlock(
        { gameplay: "platformer-gameplay-block-v1" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toEqual({
      block: "gameplay",
      version: "platformer-gameplay-block-v1",
      published: true,
    });
  });
});
