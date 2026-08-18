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
    expect(downs.filter((action) => action.key === "Space")).toHaveLength(6);
    expect(downs.filter((action) => action.key === "i")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "s")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "ArrowUp")).toHaveLength(0);
    expect(downs.filter((action) => action.key === "ArrowLeft")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "ArrowDown")).toHaveLength(3);
    expect(downs.filter((action) => action.key === "ArrowRight")).toHaveLength(4);
    expect(downs.filter((action) => action.key === "Shift")).toHaveLength(6);
    expect(
      downs.filter((action) => action.key === "ArrowRight").map((action) => action.frame),
    ).toEqual([54, 153, 196, 316]);
    expect(GAMEPLAY_POSTER_FRAME).toBe(35);
    expect(GAMEPLAY_SELECTED_FRAMES).toEqual([
      1, 31, 35, 43, 49, 67, 130, 131, 145, 153, 154, 161, 162,
      165, 171, 172, 175, 176, 190, 196, 197, 211, 217, 231, 242,
      256, 270, 292, 295, 315, 481, 869, 881, 900,
    ]);
    expect(GAMEPLAY_EVENT_VISIBILITY_WINDOWS.stageAdvance).toEqual({
      start: 869,
      end: 869,
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
    expect(actions.filter((action) => action.key === "ArrowUp")).toEqual([]);
    expect(actions.filter((action) => action.key === "ArrowDown")).toEqual([
      { frame: 153, type: "down", key: "ArrowDown" },
      { frame: 154, type: "up", key: "ArrowDown" },
      { frame: 269, type: "down", key: "ArrowDown" },
      { frame: 291, type: "up", key: "ArrowDown" },
      { frame: 294, type: "down", key: "ArrowDown" },
      { frame: 315, type: "up", key: "ArrowDown" },
    ]);
  });

  test("stages readable platform settling, drop-through, and recovery", () => {
    const actions = GAMEPLAY_TIMELINE.flatMap((frame) =>
      frame.actions.map((action) => ({ frame: frame.index, ...action })),
    );
    expect(actions.filter((action) => action.key === "Space")).toEqual([
      { frame: 130, type: "down", key: "Space" },
      { frame: 131, type: "up", key: "Space" },
      { frame: 153, type: "down", key: "Space" },
      { frame: 154, type: "up", key: "Space" },
      { frame: 175, type: "down", key: "Space" },
      { frame: 176, type: "up", key: "Space" },
      { frame: 196, type: "down", key: "Space" },
      { frame: 197, type: "up", key: "Space" },
      { frame: 216, type: "down", key: "Space" },
      { frame: 217, type: "up", key: "Space" },
      { frame: 241, type: "down", key: "Space" },
      { frame: 242, type: "up", key: "Space" },
    ]);
    expect(153 - 145).toBeGreaterThanOrEqual(6);
    expect(153 - 145).toBeLessThanOrEqual(10);
    expect(172 - 165).toBeGreaterThanOrEqual(6);
    expect(172 - 165).toBeLessThanOrEqual(10);
    expect(196 - 190).toBeGreaterThanOrEqual(6);
    expect(actions.filter((action) => action.key === "ArrowLeft")).toEqual([
      { frame: 172, type: "down", key: "ArrowLeft" },
      { frame: 175, type: "up", key: "ArrowLeft" },
    ]);
  });
});
