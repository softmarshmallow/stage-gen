import { describe, expect, test } from "bun:test";
import { easeOutCubic, ParticleRing, particleUnitNoise, unitProgress } from "./particles";

describe("particleUnitNoise", () => {
  test("is deterministic, in range, and separated by channel", () => {
    for (const seed of [0, 1, 7, 0xffff_ffff, 0x27d4_eb2f]) {
      const value = particleUnitNoise(seed, 7);
      expect(value).toBe(particleUnitNoise(seed, 7));
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
    // One record draws several independent numbers without carrying a
    // generator: the channel is what separates its radius from its kick.
    expect(particleUnitNoise(5, 1)).not.toBe(particleUnitNoise(5, 2));
  });
});

describe("the shared curves", () => {
  test("the ease is out-cubic and the progress is clamped", () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(1)).toBe(1);
    expect(easeOutCubic(0.5)).toBeCloseTo(0.875, 9);
    expect(unitProgress(-3)).toBe(0);
    expect(unitProgress(3)).toBe(1);
  });
});

// --- E4: one ring, two presentations that share no record ---------------------------------------

describe("E4: the particle ring instantiated twice", () => {
  test("a puff ring: frozen birth records, oldest evicted, spent ones pruned", () => {
    // Runner-shaped. A puff owns nothing, so nothing is released on eviction;
    // the record is a where and a when, and every frame only samples it.
    type Puff = Readonly<{ kind: string; bornAtMs: number }>;
    const ring = new ParticleRing<Puff>({ max: 3 });
    for (const bornAtMs of [0, 100, 200, 300]) {
      ring.remember(Object.freeze({ kind: "stride", bornAtMs }));
    }
    expect(ring.count).toBe(3);
    expect(ring.records.map((puff) => puff.bornAtMs)).toEqual([100, 200, 300]);
    ring.prune((puff) => 350 - puff.bornAtMs >= 200);
    expect(ring.records.map((puff) => puff.bornAtMs)).toEqual([200, 300]);
    ring.clear();
    expect(ring.count).toBe(0);
  });

  test("a blow ring: the same ring, with a target to let go of", () => {
    // Platformer-shaped. A blow holds its target sprite white while it is live,
    // so every departure — evicted by the cap, pruned once spent, or cleared on
    // teardown — has to release it. That is the one parameter the two differ by.
    type Blow = { readonly id: number; flashing: boolean };
    const released: number[] = [];
    const ring = new ParticleRing<Blow>({
      max: 2,
      onRelease: (blow) => {
        blow.flashing = false;
        released.push(blow.id);
      },
    });
    // The platformer makes room *before* the record exists, because the id it
    // is about to be given comes from a counter the eviction must not touch.
    for (const id of [1, 2, 3]) {
      ring.makeRoom();
      ring.remember({ id, flashing: true });
    }
    expect(released).toEqual([1]);
    expect(ring.records.map((blow) => blow.id)).toEqual([2, 3]);
    ring.prune((blow) => blow.id === 2);
    expect(released).toEqual([1, 2]);
    ring.clear();
    expect(released).toEqual([1, 2, 3]);
    expect(ring.count).toBe(0);
  });

  test("the cap is bounded by its ceiling and never below one", () => {
    expect(new ParticleRing({ max: 4096, ceiling: 256 }).capacity).toBe(256);
    expect(new ParticleRing({ max: 0 }).capacity).toBe(1);
  });
});
