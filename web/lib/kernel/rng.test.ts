import { describe, expect, test } from "bun:test";

import { fnv1a32, mix32 } from "./hash";
import { createRng, mulberry32, xorshift32 } from "./rng";

describe("mulberry32", () => {
  test("is deterministic and uniform-ish in [0, 1)", () => {
    const a = mulberry32(1234);
    const b = mulberry32(1234);
    const values = Array.from({ length: 100 }, () => a());
    expect(Array.from({ length: 100 }, () => b())).toEqual(values);
    for (const value of values) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
    expect(new Set(values).size).toBeGreaterThan(90);
  });

  test("different seeds produce different streams", () => {
    const a = mulberry32(1);
    const b = mulberry32(2);
    expect(Array.from({ length: 8 }, () => a())).not.toEqual(
      Array.from({ length: 8 }, () => b()),
    );
  });

  // The runner's replay golden and the platformer's heightmaps are pinned to
  // these exact streams; the copies this module replaced produced them, so a
  // change here is a change to every baked artifact in the tree.
  test("pins the stream the consolidated copies produced", () => {
    const rng = mulberry32(0x5eed_1234);
    expect(Array.from({ length: 3 }, () => rng().toFixed(12))).toEqual([
      "0.411579957232",
      "0.841819531750",
      "0.216255637584",
    ]);
  });
});

describe("xorshift32", () => {
  test("pins the stream the platformer's heightmap was baked against", () => {
    const rng = xorshift32(fnv1a32("stage-tag"));
    expect(Array.from({ length: 3 }, () => rng().toFixed(12))).toEqual([
      "0.859657196095",
      "0.907320304075",
      "0.714649733389",
    ]);
  });

  test("refuses to sit on the zero fixed point", () => {
    const rng = xorshift32(0);
    expect(rng()).toBeGreaterThan(0);
  });
});

describe("fnv1a32", () => {
  test("pins the hash both platformer copies computed", () => {
    expect(fnv1a32("")).toBe(0x811c9dc5);
    expect(fnv1a32("a")).toBe(0xe40c292c);
    expect(fnv1a32("foobar")).toBe(0xbf9cf968);
  });
});

describe("named channels", () => {
  test("the same name on the same seed is the same stream", () => {
    const rng = createRng(7);
    const first = rng.channel("segments");
    expect(rng.channel("segments")).toBe(first);
  });

  test("one channel's draws do not move another's", () => {
    const quiet = createRng(7);
    const busy = createRng(7);
    for (let i = 0; i < 50; i += 1) busy.channel("salvo")();
    expect(busy.channel("segments")()).toBe(quiet.channel("segments")());
  });

  test("different names are different streams", () => {
    const rng = createRng(7);
    expect(rng.channel("segments")()).not.toBe(rng.channel("salvo")());
  });

  test("different seeds move every channel", () => {
    expect(createRng(1).channel("segments")()).not.toBe(
      createRng(2).channel("segments")(),
    );
  });
});

describe("mix32", () => {
  test("avalanches both halves", () => {
    expect(mix32(1, 0)).not.toBe(mix32(0, 0));
    expect(mix32(0, 1)).not.toBe(mix32(0, 0));
    expect(mix32(1, 2) >>> 0).toBe(mix32(1, 2));
  });
});
