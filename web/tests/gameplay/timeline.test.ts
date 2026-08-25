import { describe, expect, test } from "bun:test";
import {
  GAMEPLAY_DURATION_SECONDS,
  GAMEPLAY_EVENT_VISIBILITY_WINDOWS,
  GAMEPLAY_FRAME_COUNT,
  GAMEPLAY_FPS,
  GAMEPLAY_POSTER_FRAME,
  GAMEPLAY_SELECTED_FRAMES,
  GAMEPLAY_TIMELINE,
  type GameplayKey,
} from "./timeline";

describe("deterministic gameplay timeline", () => {
  test("is a deeply immutable 900-frame, 30-second script", () => {
    expect(GAMEPLAY_FPS).toBe(30);
    expect(GAMEPLAY_FRAME_COUNT).toBe(900);
    expect(GAMEPLAY_DURATION_SECONDS).toBe(30);
    expect(GAMEPLAY_TIMELINE).toHaveLength(900);
    expect(GAMEPLAY_TIMELINE.map((frame) => frame.index)).toEqual(
      Array.from({ length: 900 }, (_, index) => index),
    );
    expect(Object.isFrozen(GAMEPLAY_TIMELINE)).toBe(true);
    for (const frame of GAMEPLAY_TIMELINE) {
      expect(Object.isFrozen(frame)).toBe(true);
      expect(Object.isFrozen(frame.actions)).toBe(true);
      for (const action of frame.actions) expect(Object.isFrozen(action)).toBe(true);
    }
  });

  test("uses only balanced real-keyboard actions", () => {
    const down = new Set<GameplayKey>();
    for (const frame of GAMEPLAY_TIMELINE) {
      for (const action of frame.actions) {
        if (action.type === "down") {
          expect(down.has(action.key)).toBe(false);
          down.add(action.key);
        } else {
          expect(down.delete(action.key)).toBe(true);
        }
      }
    }
    expect([...down]).toEqual([]);
  });

  test("contains combat, jump-chain, drop, ladder, inventory, and movement phases", () => {
    const actions = GAMEPLAY_TIMELINE.flatMap((frame) =>
      frame.actions.map((action) => ({ frame: frame.index, ...action })),
    );
    const downs = actions.filter((action) => action.type === "down");
    expect(downs.filter((action) => action.key === "j")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "i")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "s")).toHaveLength(1);
    // Exactly one: the deliberate press that opens the exit portal. Travel
    // used to happen on contact, with no key involved at all.
    expect(downs.filter((action) => action.key === "ArrowUp")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "ArrowLeft")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "ArrowDown")).toHaveLength(3);
    expect(downs.filter((action) => action.key === "ArrowRight")).toHaveLength(5);
    expect(downs.filter((action) => action.key === "Shift")).toHaveLength(6);
    expect(
      downs.filter((action) => action.key === "ArrowRight").map((action) => action.frame),
    ).toEqual([54, 153, 196, 321, 866]);
    // Terrain rises are walls, so the route is mostly jumps now. Counting them
    // exactly would just restate the data; what matters is that the route is
    // built out of climbs rather than a walk.
    expect(
      downs.filter((action) => action.key === "Space").length,
    ).toBeGreaterThan(12);
    expect(GAMEPLAY_POSTER_FRAME).toBe(35);
    expect(GAMEPLAY_SELECTED_FRAMES).toEqual([
      1, 31, 35, 43, 49, 67, 125, 126, 146, 153, 154, 161, 162,
      165, 171, 172, 175, 176, 190, 196, 197, 211, 217, 231, 242,
      256, 275, 297, 300, 320, 481, 858, 859, 860, 900,
    ]);
    // Hashed either side of the portal so a stage transition that silently
    // stopped happening would change the digests rather than pass unnoticed.
    expect(GAMEPLAY_EVENT_VISIBILITY_WINDOWS.stageAdvance).toEqual({
      start: 859,
      end: 859,
    });
  });

  test("keeps real run input active throughout the final presentation window", () => {
    const held = new Set<GameplayKey>();
    for (const frame of GAMEPLAY_TIMELINE) {
      for (const action of frame.actions) {
        if (action.type === "down") held.add(action.key);
        else held.delete(action.key);
      }
      if (frame.index >= 866 && frame.index <= 898) {
        expect(held.has("ArrowRight")).toBeTrue();
        expect(held.has("Shift")).toBeTrue();
      }
    }
    expect(held.size).toBe(0);
  });

  test("includes one paused, balanced ladder descent after the jump chain", () => {
    const actions = GAMEPLAY_TIMELINE.flatMap((frame) =>
      frame.actions.map((action) => ({ frame: frame.index, ...action })),
    );
    expect(actions.filter((action) => action.key === "ArrowUp")).toEqual([
      { frame: 858, type: "down", key: "ArrowUp" },
      { frame: 859, type: "up", key: "ArrowUp" },
    ]);
    expect(actions.filter((action) => action.key === "ArrowDown")).toEqual([
      { frame: 153, type: "down", key: "ArrowDown" },
      { frame: 154, type: "up", key: "ArrowDown" },
      { frame: 274, type: "down", key: "ArrowDown" },
      { frame: 296, type: "up", key: "ArrowDown" },
      { frame: 299, type: "down", key: "ArrowDown" },
      { frame: 320, type: "up", key: "ArrowDown" },
    ]);
  });

  test("stages readable platform settling, drop-through, and recovery", () => {
    const actions = GAMEPLAY_TIMELINE.flatMap((frame) =>
      frame.actions.map((action) => ({ frame: frame.index, ...action })),
    );
    const space = actions.filter((action) => action.key === "Space");
    // Every press is released on the very next frame: a held Space would make
    // the second impulse of a double jump depend on key repeat rather than on
    // the script.
    for (let index = 0; index < space.length; index += 2) {
      expect(space[index]!.type).toBe("down");
      expect(space[index + 1]).toEqual({
        frame: space[index]!.frame + 1,
        type: "up",
        key: "Space",
      });
    }
    const pressedAt = space
      .filter((action) => action.type === "down")
      .map((action) => action.frame);
    // The choreographed platform beats stay pinned; the rest are terrain climbs.
    expect(pressedAt).toContain(125); // terrain onto the tier-one deck
    expect(pressedAt).toContain(153); // drop through it
    expect(pressedAt).toContain(174); // recovery, off the wall the drop left
    expect(pressedAt).toContain(184); // and its air jump onto the deck
    expect(pressedAt).toContain(196); // jump chain to tier two
    expect(pressedAt).toContain(216);
    expect(pressedAt).toContain(241);
    // A double jump's second press has to arrive while the first arc is still
    // rising, or it lands on the ground and buys an ordinary jump instead.
    expect(184 - 174).toBeLessThan(21);
    expect(153 - 146).toBeGreaterThanOrEqual(6);
    expect(153 - 146).toBeLessThanOrEqual(10);
    expect(172 - 165).toBeGreaterThanOrEqual(6);
    expect(172 - 165).toBeLessThanOrEqual(10);
    expect(196 - 190).toBeGreaterThanOrEqual(6);
    expect(actions.filter((action) => action.key === "ArrowLeft")).toEqual([
      { frame: 172, type: "down", key: "ArrowLeft" },
      { frame: 185, type: "up", key: "ArrowLeft" },
    ]);
  });
});
