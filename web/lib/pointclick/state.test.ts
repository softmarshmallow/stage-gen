import { bagEntries } from "@/lib/families/inventory";
import { describe, expect, test } from "bun:test";

import { parseRoomManifest } from "./contract";
import {
  MISS_LINE,
  MISS_WITH_ITEM_LINE,
  clickHotspot,
  hotspotVisible,
  initialState,
  inspectHotspot,
  roomFlagVocabulary,
  selectItem,
} from "./state";
import { roomManifestFixture } from "./fixture";

const manifest = parseRoomManifest(roomManifestFixture());

describe("room state machine", () => {
  test("the fixture room plays to completion through primary clicks", () => {
    let state = initialState(manifest);
    expect(hotspotVisible(manifest, state, "prize")).toBe(false);

    state = clickHotspot(manifest, state, "bench");
    expect(bagEntries(state.inventory)).toEqual([["key", 1]]);
    expect(state.narration).toBe("You find a key under the bench.");

    state = selectItem(state, "key");
    expect(state.selectedItem).toBe("key");
    state = clickHotspot(manifest, state, "chest");
    expect(state.flags).toContain("chest_open");
    expect(state.selectedItem).toBeNull();
    expect(hotspotVisible(manifest, state, "prize")).toBe(true);

    state = clickHotspot(manifest, state, "prize");
    expect(state.solved).toBe(true);
    expect(state.narration).toBe("You take the prize. The room is finished.");
  });

  test("hidden hotspots refuse interaction until revealed", () => {
    const state = initialState(manifest);
    const after = clickHotspot(manifest, state, "prize");
    expect(after.narration).toBe(MISS_LINE);
    expect(after.flags).toEqual([]);
  });

  test("guards hold: the prize needs the chest open even once revealed", () => {
    let state = initialState(manifest);
    state = { ...state, revealed: ["prize"] };
    const after = clickHotspot(manifest, state, "prize");
    expect(after.flags).toEqual([]);
    expect(after.narration).toBe(MISS_LINE);
  });

  test("an effectful interaction fires once; pure narration repeats", () => {
    let state = initialState(manifest);
    state = clickHotspot(manifest, state, "bench");
    const again = clickHotspot(manifest, state, "bench");
    // The grant already fired, so the primary click falls through to inspect.
    expect(bagEntries(again.inventory)).toEqual([["key", 1]]);
    expect(again.narration).toBe("A sturdy bench.");
    const inspected = inspectHotspot(manifest, again, "bench");
    expect(inspected.narration).toBe("A sturdy bench.");
  });

  test("a held item that fits nothing narrates the miss and drops selection", () => {
    let state = initialState(manifest);
    state = clickHotspot(manifest, state, "bench");
    state = selectItem(state, "key");
    const after = clickHotspot(manifest, state, "bench");
    expect(after.narration).toBe(MISS_WITH_ITEM_LINE);
    expect(after.selectedItem).toBeNull();
  });

  test("selecting an item you do not hold is refused", () => {
    const state = initialState(manifest);
    expect(selectItem(state, "key")).toBe(state);
  });
});

describe("room manifest parser", () => {
  test("refuses a foreign kind with the regenerate hint", () => {
    expect(() => parseRoomManifest({ kind: "prepared-game-runtime-v10" })).toThrow(
      /regenerate this room/,
    );
  });

  test("refuses a sprite hotspot without its sprite ref", () => {
    const raw = roomManifestFixture();
    const hotspots = raw.hotspots as Array<Record<string, unknown>>;
    hotspots[1].sprite = null;
    expect(() => parseRoomManifest(raw)).toThrow(/sprite ref/);
  });

  test("refuses interactions that name unknown ids", () => {
    const raw = roomManifestFixture();
    const interactions = raw.interactions as Array<Record<string, unknown>>;
    (interactions[0].on as Record<string, unknown>).hotspot = "ghost";
    expect(() => parseRoomManifest(raw)).toThrow(/unknown hotspot/);
  });
});


describe("carrying facts into a room", () => {
  test("the flag vocabulary is recovered from the document the reducer walks", () => {
    expect(roomFlagVocabulary(manifest)).toEqual(new Set(["chest_open", "prize_taken"]));
  });

  test("a fact this room uses arrives set", () => {
    expect(initialState(manifest, ["chest_open"]).flags).toEqual(["chest_open"]);
  });

  test("a fact this room never mentions is dropped rather than added to its state", () => {
    expect(initialState(manifest, ["a_fact_from_a_scenario"]).flags).toEqual([]);
  });

  test("carrying nothing is exactly the room as the player used to find it", () => {
    expect(initialState(manifest, [])).toEqual(initialState(manifest));
  });

  test("a room whose win flag arrives already set opens solved, and says so", () => {
    // An authoring error rather than a feature: the win flag belongs to the room's
    // own exit. The reducer is honest about it instead of pretending otherwise.
    expect(initialState(manifest, ["prize_taken"]).solved).toBe(true);
  });
});
