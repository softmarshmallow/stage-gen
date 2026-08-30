import { describe, expect, test } from "bun:test";

import { parseRoomManifest } from "./contract";
import {
  MISS_LINE,
  MISS_WITH_ITEM_LINE,
  clickHotspot,
  hotspotVisible,
  initialState,
  inspectHotspot,
  selectItem,
} from "./state";
import { roomManifestFixture } from "./fixture";

const manifest = parseRoomManifest(roomManifestFixture());

describe("room state machine", () => {
  test("the fixture room plays to completion through primary clicks", () => {
    let state = initialState(manifest);
    expect(hotspotVisible(manifest, state, "prize")).toBe(false);

    state = clickHotspot(manifest, state, "bench");
    expect(state.inventory).toEqual(["key"]);
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
    expect(again.inventory).toEqual(["key"]);
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
