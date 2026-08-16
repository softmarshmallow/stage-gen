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

  test("contains one attack, one jump, one inventory toggle, and movement phases", () => {
    const actions = GAMEPLAY_TIMELINE.flatMap((frame) =>
      frame.actions.map((action) => ({ frame: frame.index, ...action })),
    );
    const downs = actions.filter((action) => action.type === "down");
    expect(downs.filter((action) => action.key === "j")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "Space")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "i")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "s")).toHaveLength(1);
    expect(downs.filter((action) => action.key === "ArrowRight")).toHaveLength(2);
    expect(downs.filter((action) => action.key === "Shift")).toHaveLength(2);
    expect(
      downs.filter((action) => action.key === "ArrowRight").map((action) => action.frame),
    ).toEqual([54, 541]);
    expect(GAMEPLAY_POSTER_FRAME).toBe(35);
    expect(GAMEPLAY_SELECTED_FRAMES).toEqual([
      1, 31, 35, 43, 49, 67, 271, 481, 870, 900,
    ]);
    expect(GAMEPLAY_EVENT_VISIBILITY_WINDOWS.stageAdvance).toEqual({
      start: 885,
      end: 899,
    });
  });

  test("keeps real run input active throughout the final presentation window", () => {
    const held = new Set<GameplayKey>();
    for (const frame of GAMEPLAY_TIMELINE) {
      for (const action of frame.actions) {
        if (action.type === "down") held.add(action.key);
        else held.delete(action.key);
      }
      if (frame.index >= 845 && frame.index <= 898) {
        expect(held.has("ArrowRight")).toBeTrue();
        expect(held.has("Shift")).toBeTrue();
      }
    }
    expect(held.size).toBe(0);
  });
});
