import { describe, expect, test } from "bun:test";
import {
  createFixedStepAccumulator,
  FIXED_STEP_SECONDS,
  MAX_SUBSTEPS_PER_ADVANCE,
} from "./fixed-step";

const STEP_MS = FIXED_STEP_SECONDS * 1000;

describe("createFixedStepAccumulator", () => {
  test("converts frame deltas into fixed steps and carries the remainder", () => {
    const accumulator = createFixedStepAccumulator();
    expect(accumulator.advance(STEP_MS / 2)).toHaveLength(0);
    const steps = accumulator.advance(STEP_MS / 2);
    expect(steps).toHaveLength(1);
    expect(steps[0].dt).toBeCloseTo(FIXED_STEP_SECONDS, 10);
    expect(steps[0].frame).toBe(1);
    expect(steps[0].now).toBeCloseTo(FIXED_STEP_SECONDS, 10);
  });

  test("emits the same total step count for the same total time, however sliced", () => {
    const smooth = createFixedStepAccumulator();
    const jittery = createFixedStepAccumulator();
    let smoothSteps = 0;
    let jitterySteps = 0;
    for (let i = 0; i < 60; i += 1) smoothSteps += smooth.advance(STEP_MS).length;
    for (let i = 0; i < 30; i += 1) {
      jitterySteps += jittery.advance(STEP_MS * 0.4).length;
      jitterySteps += jittery.advance(STEP_MS * 1.6).length;
    }
    expect(smoothSteps).toBe(60);
    expect(jitterySteps).toBe(60);
  });

  test("numbers frames monotonically across advances", () => {
    const accumulator = createFixedStepAccumulator();
    const first = accumulator.advance(STEP_MS * 2.2);
    const second = accumulator.advance(STEP_MS * 1);
    expect(first.map((step) => step.frame)).toEqual([1, 2]);
    expect(second.map((step) => step.frame)).toEqual([3]);
  });

  test("clamps a stall to the max substeps and drops the backlog", () => {
    const accumulator = createFixedStepAccumulator();
    const steps = accumulator.advance(STEP_MS * 60);
    expect(steps).toHaveLength(MAX_SUBSTEPS_PER_ADVANCE);
    // The backlog is gone: the next normal frame emits one step, not a burst.
    expect(accumulator.advance(STEP_MS)).toHaveLength(1);
  });

  test("ignores negative and non-finite deltas", () => {
    const accumulator = createFixedStepAccumulator();
    expect(accumulator.advance(-100)).toHaveLength(0);
    expect(accumulator.advance(Number.NaN)).toHaveLength(0);
    expect(accumulator.advance(Number.POSITIVE_INFINITY)).toHaveLength(0);
    expect(accumulator.advance(STEP_MS)).toHaveLength(1);
  });

  test("reset forgets both accumulated time and step identity", () => {
    const accumulator = createFixedStepAccumulator();
    accumulator.advance(STEP_MS * 3);
    accumulator.reset();
    const steps = accumulator.advance(STEP_MS);
    expect(steps[0].frame).toBe(1);
    expect(steps[0].now).toBeCloseTo(FIXED_STEP_SECONDS, 10);
  });

  test("refuses a nonsensical configuration", () => {
    expect(() => createFixedStepAccumulator(0)).toThrow("must be positive");
    expect(() => createFixedStepAccumulator(FIXED_STEP_SECONDS, 0)).toThrow(
      "positive integer",
    );
  });
});
