import { describe, expect, test } from "bun:test";
import {
  createGauge,
  drain,
  gaugeFraction,
  grow,
  isRefractory,
  refractoryBlinkAlpha,
  restore,
  type Gauge,
} from "./gauge";

const REFRACTORY_MS = 900;

describe("createGauge", () => {
  test("starts full, open, and not depleted", () => {
    expect(createGauge(3)).toEqual({
      value: 3,
      max: 3,
      refractoryUntilMs: 0,
      depleted: false,
    });
  });

  test("refuses a maximum that is not a positive integer", () => {
    expect(() => createGauge(0)).toThrow(RangeError);
    expect(() => createGauge(-1)).toThrow(RangeError);
    expect(() => createGauge(2.5)).toThrow(RangeError);
    expect(() => createGauge(Number.NaN)).toThrow(RangeError);
  });
});

describe("drain", () => {
  test("applies the amount and opens the refractory window", () => {
    const change = drain(createGauge(3), 1, 1_000, REFRACTORY_MS);
    expect(change.connected).toBe(true);
    expect(change.applied).toBe(1);
    expect(change.before).toBe(3);
    expect(change.after).toBe(2);
    expect(change.depleted).toBe(false);
    expect(change.gauge.refractoryUntilMs).toBe(1_900);
  });

  test("absorbs a drain inside the window and hands the gauge back untouched", () => {
    const first = drain(createGauge(3), 1, 1_000, REFRACTORY_MS);
    const second = drain(first.gauge, 1, 1_400, REFRACTORY_MS);
    expect(second.connected).toBe(false);
    expect(second.applied).toBe(0);
    expect(second.after).toBe(2);
    expect(second.gauge).toBe(first.gauge);
  });

  test("connects again once the window has passed", () => {
    const first = drain(createGauge(3), 1, 1_000, REFRACTORY_MS);
    const second = drain(first.gauge, 1, 1_900, REFRACTORY_MS);
    expect(second.connected).toBe(true);
    expect(second.after).toBe(1);
  });

  test("floors at zero and reports depletion rather than overspill", () => {
    const change = drain(createGauge(2), 5, 0, REFRACTORY_MS);
    expect(change.attempted).toBe(5);
    expect(change.applied).toBe(2);
    expect(change.after).toBe(0);
    expect(change.depleted).toBe(true);
    expect(change.gauge.depleted).toBe(true);
  });

  test("refuses a depleted gauge, so depletion resolves exactly once", () => {
    const emptied = drain(createGauge(1), 1, 0, REFRACTORY_MS).gauge;
    const again = drain(emptied, 1, 10_000, REFRACTORY_MS);
    expect(again.connected).toBe(false);
    expect(again.depleted).toBe(true);
  });

  test("refuses an invalid or non-positive amount", () => {
    const gauge = createGauge(3);
    for (const amount of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(drain(gauge, amount, 0, REFRACTORY_MS).connected).toBe(false);
    }
  });

  test("a zero refractory grants no window but still lands", () => {
    const change = drain(createGauge(3), 1, 5_000, 0);
    expect(change.connected).toBe(true);
    expect(isRefractory(change.gauge, 5_000)).toBe(false);
  });

  test("never shortens a window that is already open", () => {
    const long = drain(createGauge(3), 1, 1_000, 5_000).gauge;
    const later = drain({ ...long, refractoryUntilMs: 0 }, 1, 2_000, 100);
    expect(later.gauge.refractoryUntilMs).toBe(2_100);
    // A shorter grant cannot cut a longer standing window short.
    const standing: Gauge = { ...long, refractoryUntilMs: 9_000, depleted: false };
    expect(drain(standing, 1, 9_500, 100).gauge.refractoryUntilMs).toBe(9_600);
  });
});

describe("restore", () => {
  test("refills toward the ceiling and reports what it spent", () => {
    const drained = drain(createGauge(3), 2, 0, REFRACTORY_MS).gauge;
    const change = restore(drained, 5);
    expect(change.connected).toBe(true);
    expect(change.applied).toBe(2);
    expect(change.gauge.value).toBe(3);
  });

  test("refuses a full gauge, so nothing is spent on an untouched pool", () => {
    expect(restore(createGauge(3), 1).connected).toBe(false);
  });

  test("refuses a depleted gauge", () => {
    const emptied = drain(createGauge(1), 1, 0, REFRACTORY_MS).gauge;
    expect(restore(emptied, 1).connected).toBe(false);
  });

  test("leaves the refractory window alone", () => {
    const hit = drain(createGauge(3), 1, 1_000, REFRACTORY_MS).gauge;
    expect(restore(hit, 1).gauge.refractoryUntilMs).toBe(hit.refractoryUntilMs);
  });
});

describe("grow", () => {
  test("raises the ceiling and fills to it", () => {
    const drained = drain(createGauge(3), 2, 0, REFRACTORY_MS).gauge;
    expect(grow(drained, 6)).toMatchObject({ value: 6, max: 6 });
  });

  test("returns an unchanged gauge when the ceiling does not grow", () => {
    const gauge = createGauge(3);
    expect(grow(gauge, 3)).toBe(gauge);
    expect(grow(gauge, 2)).toBe(gauge);
  });

  test("refuses a maximum that is not a positive integer", () => {
    expect(() => grow(createGauge(3), 0)).toThrow(RangeError);
  });
});

describe("refractoryBlinkAlpha", () => {
  test("is opaque outside the window", () => {
    expect(refractoryBlinkAlpha(createGauge(3), 0, 75, 0.35)).toBe(1);
  });

  test("alternates on the interval, counting down from the window's end", () => {
    const hit = drain(createGauge(3), 1, 0, 300).gauge;
    // 300ms remaining: phase 4 -> dim. 200 remaining: phase 2 -> dim. 100: phase 1 -> bright.
    expect(refractoryBlinkAlpha(hit, 0, 75, 0.35)).toBe(0.35);
    expect(refractoryBlinkAlpha(hit, 100, 75, 0.35)).toBe(0.35);
    expect(refractoryBlinkAlpha(hit, 225, 75, 0.35)).toBe(1);
  });

  test("is deterministic — same inputs, same alpha, no clock", () => {
    const hit = drain(createGauge(3), 1, 1_000, 900).gauge;
    for (const now of [1_000, 1_137, 1_400, 1_899]) {
      expect(refractoryBlinkAlpha(hit, now, 75, 0.35)).toBe(
        refractoryBlinkAlpha(hit, now, 75, 0.35),
      );
    }
  });

  test("a depleted gauge never blinks", () => {
    const emptied = drain(createGauge(1), 1, 0, 900).gauge;
    expect(refractoryBlinkAlpha(emptied, 100, 75, 0.35)).toBe(1);
  });
});

describe("gaugeFraction", () => {
  test("reports fullness in [0, 1]", () => {
    expect(gaugeFraction(createGauge(4))).toBe(1);
    expect(gaugeFraction(drain(createGauge(4), 1, 0, 0).gauge)).toBe(0.75);
    expect(gaugeFraction(drain(createGauge(4), 4, 0, 0).gauge)).toBe(0);
  });
});
