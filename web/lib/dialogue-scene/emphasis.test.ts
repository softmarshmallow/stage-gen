import { describe, expect, test } from "bun:test";
import {
  actorEmphasis,
  FAR_LISTENER_ALPHA,
  LISTENER_ALPHA,
  narrationEmphasis,
  SPEAKER_STACK_ORDER,
  SPEAKING_SCALE,
} from "./emphasis";
import { STAGE_SLOTS } from "./scene-hud";
import { SCENARIO_SLOTS } from "@/lib/scenario/program";

describe("actorEmphasis", () => {
  test("the speaker is at full colour, forward, and above every slot", () => {
    for (const slot of SCENARIO_SLOTS) {
      const emphasis = actorEmphasis(slot, true);
      expect(emphasis.alpha).toBe(1);
      expect(emphasis.tint).toBeNull();
      expect(emphasis.scale).toBe(SPEAKING_SCALE);
      expect(emphasis.stackOrder).toBe(SPEAKER_STACK_ORDER);
    }
  });

  test("a listener recedes without leaving: dimmer, cooler, and never invisible", () => {
    for (const slot of SCENARIO_SLOTS) {
      const emphasis = actorEmphasis(slot, false);
      expect(emphasis.alpha).toBeLessThan(1);
      expect(emphasis.alpha).toBeGreaterThan(0.5);
      expect(emphasis.tint).not.toBeNull();
      expect(emphasis.scale).toBe(1);
      expect(emphasis.stackOrder).toBeLessThan(SPEAKER_STACK_ORDER);
    }
  });

  test("the far rank recedes further than the near one", () => {
    expect(actorEmphasis("far_left", false).alpha).toBe(FAR_LISTENER_ALPHA);
    expect(actorEmphasis("left", false).alpha).toBe(LISTENER_ALPHA);
    expect(actorEmphasis("far_left", false).alpha).toBeLessThan(
      actorEmphasis("left", false).alpha,
    );
  });

  test("the emphasis is subtle: the speaker never doubles in size", () => {
    expect(SPEAKING_SCALE).toBeGreaterThan(1);
    expect(SPEAKING_SCALE).toBeLessThan(1.1);
  });
});

describe("narrationEmphasis", () => {
  test("nobody is picked out when nobody is talking", () => {
    expect(narrationEmphasis("center").tint).toBeNull();
    expect(narrationEmphasis("center").alpha).toBe(1);
    for (const slot of SCENARIO_SLOTS) {
      expect(narrationEmphasis(slot).scale).toBe(1);
      expect(narrationEmphasis(slot).stackOrder).toBeLessThan(SPEAKER_STACK_ORDER);
    }
  });

  test("the far rank stays further away even with nobody speaking", () => {
    expect(narrationEmphasis("far_left").alpha).toBeLessThan(
      narrationEmphasis("center").alpha,
    );
  });
});

describe("the slot vocabulary", () => {
  test("the stage draws exactly the five slots the contract declares", () => {
    expect([...STAGE_SLOTS]).toEqual([...SCENARIO_SLOTS]);
    expect(SCENARIO_SLOTS).toEqual([
      "far_left",
      "left",
      "center",
      "right",
      "far_right",
    ]);
  });
});
