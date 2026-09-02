import { describe, expect, test } from "bun:test";
import type Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./depths";
import {
  IMPACT_BURST_MS,
  IMPACT_BURST_SHARDS,
  IMPACT_CRITICAL_SCALE,
  IMPACT_DEPTH,
  IMPACT_FLASH_MS,
  IMPACT_HITSTOP_MS,
  IMPACT_KILL_HITSTOP_MS,
  IMPACT_SHAKE_MS,
  IMPACT_SHAKE_PX,
  IMPACT_SPARK_MS,
  IMPACT_SPARK_RAYS,
  IMPACT_SWING_MS,
  IMPACT_SWING_SPAN_RADIANS,
  ImpactSystem,
  impactHitstopMs,
  impactLifetimeMs,
  impactUnitNoise,
  sampleImpact,
  sampleImpactFlash,
  sampleImpactRays,
  sampleImpactShake,
  sampleImpactShards,
  sampleSwingArc,
  type ImpactEvent,
  type SwingEvent,
} from "./impact-presentation";

const HIT: ImpactEvent = Object.freeze({
  eventId: 1,
  seed: 0x1234_5678,
  startedAtMs: 2_000,
  x: 400,
  y: 300,
  dirSign: 1,
  critical: false,
  died: false,
  reducedMotion: false,
});

const KILL: ImpactEvent = Object.freeze({ ...HIT, eventId: 2, died: true });

describe("impact presentation samplers", () => {
  test("noise is deterministic, unit-bounded, and channel-separated", () => {
    for (let seed = 0; seed < 64; seed += 1) {
      const value = impactUnitNoise(seed, 7);
      expect(value).toBe(impactUnitNoise(seed, 7));
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
    expect(impactUnitNoise(5, 1)).not.toBe(impactUnitNoise(5, 2));
  });

  test("flash holds for exactly its window and clamps time before the event", () => {
    expect(sampleImpactFlash(HIT, HIT.startedAtMs)).toBeTrue();
    expect(sampleImpactFlash(HIT, HIT.startedAtMs + IMPACT_FLASH_MS - 1)).toBeTrue();
    expect(sampleImpactFlash(HIT, HIT.startedAtMs + IMPACT_FLASH_MS)).toBeFalse();
    expect(sampleImpactFlash(HIT, 0)).toBeTrue();
  });

  test("spark rays fan ahead of the blow, grow, fade, and end on time", () => {
    const start = sampleImpactRays(HIT, HIT.startedAtMs);
    expect(start).toHaveLength(IMPACT_SPARK_RAYS);
    for (const ray of start) {
      expect(ray.x2).toBeCloseTo(HIT.x, 12);
      expect(ray.alpha).toBe(1);
    }
    const grown = sampleImpactRays(HIT, HIT.startedAtMs + IMPACT_SPARK_MS * 0.45);
    for (const ray of grown) expect(ray.x2).toBeGreaterThan(HIT.x);
    const mirrored = sampleImpactRays({ ...HIT, dirSign: -1 }, HIT.startedAtMs + 60);
    for (const ray of mirrored) expect(ray.x2).toBeLessThan(HIT.x);
    const late = sampleImpactRays(HIT, HIT.startedAtMs + IMPACT_SPARK_MS - 1);
    for (const ray of late) expect(ray.alpha).toBeLessThan(0.05);
    expect(sampleImpactRays(HIT, HIT.startedAtMs + IMPACT_SPARK_MS)).toHaveLength(0);
  });

  test("burst shards exist only for a kill, fall under gravity, and end on time", () => {
    expect(sampleImpactShards(HIT, HIT.startedAtMs + 50)).toHaveLength(0);
    const early = sampleImpactShards(KILL, KILL.startedAtMs + 40);
    expect(early).toHaveLength(IMPACT_BURST_SHARDS);
    const late = sampleImpactShards(KILL, KILL.startedAtMs + 400);
    expect(late).toHaveLength(IMPACT_BURST_SHARDS);
    for (let index = 0; index < IMPACT_BURST_SHARDS; index += 1) {
      expect(late[index]!.alpha).toBeLessThan(early[index]!.alpha);
      expect(late[index]!.radius).toBeLessThan(early[index]!.radius);
    }
    // Every shard has fallen relative to a gravity-free flight by the end of the burst.
    const meanEarlyY = early.reduce((sum, shard) => sum + shard.y, 0) / early.length;
    const meanLateY = late.reduce((sum, shard) => sum + shard.y, 0) / late.length;
    expect(meanLateY).toBeGreaterThan(meanEarlyY);
    expect(sampleImpactShards(KILL, KILL.startedAtMs + IMPACT_BURST_MS)).toHaveLength(0);
  });

  test("shake is a kill-only bounded nudge that decays to zero", () => {
    expect(sampleImpactShake(HIT, HIT.startedAtMs)).toEqual({ x: 0, y: 0 });
    let sawMotion = false;
    for (let elapsedMs = 0; elapsedMs < IMPACT_SHAKE_MS; elapsedMs += 4) {
      const shake = sampleImpactShake(KILL, KILL.startedAtMs + elapsedMs);
      expect(Math.abs(shake.x)).toBeLessThanOrEqual(IMPACT_SHAKE_PX);
      expect(Math.abs(shake.y)).toBeLessThanOrEqual(IMPACT_SHAKE_PX);
      if (shake.x !== 0 || shake.y !== 0) sawMotion = true;
    }
    expect(sawMotion).toBeTrue();
    expect(sampleImpactShake(KILL, KILL.startedAtMs + IMPACT_SHAKE_MS)).toEqual({ x: 0, y: 0 });
    const critical = sampleImpactShake({ ...KILL, critical: true }, KILL.startedAtMs);
    const plain = sampleImpactShake(KILL, KILL.startedAtMs);
    expect(Math.abs(critical.x)).toBeCloseTo(Math.abs(plain.x) * IMPACT_CRITICAL_SCALE, 12);
  });

  test("lifetime and hitstop follow the kill and critical flags", () => {
    expect(impactLifetimeMs(HIT)).toBe(IMPACT_SPARK_MS);
    expect(impactLifetimeMs(KILL)).toBe(IMPACT_BURST_MS);
    expect(impactLifetimeMs({ died: true, reducedMotion: true })).toBe(IMPACT_FLASH_MS);
    expect(impactHitstopMs({ died: false, critical: false })).toBe(IMPACT_HITSTOP_MS);
    expect(impactHitstopMs({ died: true, critical: false })).toBe(IMPACT_KILL_HITSTOP_MS);
    expect(impactHitstopMs({ died: true, critical: true })).toBe(
      Math.round(IMPACT_KILL_HITSTOP_MS * 1.25),
    );
  });

  test("the combined sample is deterministic and completes at its lifetime", () => {
    for (let elapsedMs = 0; elapsedMs <= IMPACT_BURST_MS; elapsedMs += 7) {
      const first = sampleImpact(KILL, KILL.startedAtMs + elapsedMs);
      const second = sampleImpact(KILL, KILL.startedAtMs + elapsedMs);
      expect(second).toEqual(first);
      expect(first.complete).toBe(elapsedMs >= IMPACT_BURST_MS);
    }
  });

  test("reduced motion keeps the flash and drops every moving shape", () => {
    const reduced = Object.freeze({ ...KILL, reducedMotion: true });
    const sample = sampleImpact(reduced, reduced.startedAtMs + 20);
    expect(sample.flash).toBeTrue();
    expect(sample.rays).toHaveLength(0);
    expect(sample.shards).toHaveLength(0);
    expect(sample.shake).toEqual({ x: 0, y: 0 });
    expect(sampleImpact(reduced, reduced.startedAtMs + IMPACT_FLASH_MS).complete).toBeTrue();
  });
});

class FakeGraphics {
  depth = 0;
  destroyed = false;
  clears = 0;
  lines: number[][] = [];
  circles: number[][] = [];

  setDepth(value: number): this {
    this.depth = value;
    return this;
  }

  clear(): this {
    this.clears += 1;
    this.lines = [];
    this.circles = [];
    this.arcs = [];
    return this;
  }

  lineStyle(_width: number, _color: number, _alpha: number): this {
    return this;
  }

  fillStyle(_color: number, _alpha: number): this {
    return this;
  }

  lineBetween(x1: number, y1: number, x2: number, y2: number): this {
    this.lines.push([x1, y1, x2, y2]);
    return this;
  }

  fillCircle(x: number, y: number, radius: number): this {
    this.circles.push([x, y, radius]);
    return this;
  }

  arcs: number[][] = [];

  beginPath(): this {
    return this;
  }

  arc(x: number, y: number, radius: number, start: number, end: number): this {
    this.arcs.push([x, y, radius, start, end]);
    return this;
  }

  strokePath(): this {
    return this;
  }

  destroy(): void {
    this.destroyed = true;
  }
}

class FakeTarget {
  flashes: boolean[] = [];

  setFlash(on: boolean): void {
    this.flashes.push(on);
  }
}

function fakeScene(): Readonly<{ scene: Phaser.Scene; graphics: FakeGraphics[] }> {
  const graphics: FakeGraphics[] = [];
  const scene = {
    add: {
      graphics(): FakeGraphics {
        const created = new FakeGraphics();
        graphics.push(created);
        return created;
      },
    },
  } as unknown as Phaser.Scene;
  return Object.freeze({ scene, graphics });
}

describe("swing arc", () => {
  const SWING: SwingEvent = Object.freeze({
    eventId: 3,
    startedAtMs: 500,
    x: 200,
    y: 150,
    dirSign: 1,
    radiusPx: 120,
    reducedMotion: false,
  });

  test("the head travels from up-front to down-front and the arc is spent on time", () => {
    const start = sampleSwingArc(SWING, SWING.startedAtMs)!;
    expect(start.endAngle).toBeCloseTo(-IMPACT_SWING_SPAN_RADIANS / 2, 12);
    expect(start.startAngle).toBe(start.endAngle);
    expect(start.anticlockwise).toBeFalse();
    const mid = sampleSwingArc(SWING, SWING.startedAtMs + IMPACT_SWING_MS / 2)!;
    expect(mid.endAngle).toBeGreaterThan(start.endAngle);
    expect(mid.startAngle).toBeLessThan(mid.endAngle);
    expect(mid.alpha).toBeLessThan(1);
    expect(mid.radius).toBe(120);
    expect(sampleSwingArc(SWING, SWING.startedAtMs + IMPACT_SWING_MS)).toBeNull();
  });

  test("facing left mirrors about the vertical and walks anticlockwise", () => {
    const right = sampleSwingArc(SWING, SWING.startedAtMs + 40)!;
    const left = sampleSwingArc({ ...SWING, dirSign: -1 }, SWING.startedAtMs + 40)!;
    expect(left.anticlockwise).toBeTrue();
    expect(left.endAngle).toBeCloseTo(Math.PI - right.endAngle, 12);
    expect(left.startAngle).toBeCloseTo(Math.PI - right.startAngle, 12);
  });

  test("reduced motion draws no arc", () => {
    expect(sampleSwingArc({ ...SWING, reducedMotion: true }, SWING.startedAtMs)).toBeNull();
  });

  test("the system draws a swing whether or not it connected, then forgets it", () => {
    const { scene, graphics } = fakeScene();
    const system = new ImpactSystem({ scene });
    expect(system.showSwing({ x: 10, y: 20, dirSign: -1, radiusPx: 90, nowMs: 0 })).toBe(1);
    expect(system.showSwing({ x: 10, y: 20, dirSign: -1, radiusPx: 0, nowMs: 0 })).toBeNull();
    system.update(30);
    expect(graphics[0]!.arcs).toHaveLength(1);
    expect(graphics[0]!.arcs[0]![2]).toBe(90);
    expect(system.snapshot().swingCount).toBe(1);
    system.update(IMPACT_SWING_MS);
    expect(graphics[0]!.arcs).toHaveLength(0);
    expect(system.snapshot().swingCount).toBe(0);
  });
});

describe("impact system", () => {
  test("draws one pooled Graphics at effect depth and releases finished events", () => {
    const { scene, graphics } = fakeScene();
    const system = new ImpactSystem({ scene });
    const target = new FakeTarget();
    const id = system.showHit({
      x: 100,
      y: 80,
      dirSign: 1,
      critical: false,
      died: true,
      seed: 99,
      nowMs: 1_000,
      target,
    });
    expect(id).toBe(1);
    expect(target.flashes).toEqual([true]);
    system.update(1_010);
    expect(graphics).toHaveLength(1);
    expect(graphics[0]!.depth).toBe(IMPACT_DEPTH);
    expect(IMPACT_DEPTH).toBe(SCENE_CONTENT_DEPTH.effect);
    expect(graphics[0]!.lines.length).toBe(IMPACT_SPARK_RAYS);
    expect(graphics[0]!.circles.length).toBe(IMPACT_BURST_SHARDS);
    system.update(1_000 + IMPACT_FLASH_MS);
    expect(target.flashes).toEqual([true, false]);
    system.update(1_000 + IMPACT_BURST_MS);
    expect(system.snapshot().activeCount).toBe(0);
    expect(graphics[0]!.lines).toHaveLength(0);
    expect(graphics[0]!.circles).toHaveLength(0);
    expect(graphics).toHaveLength(1);
  });

  test("hitstop extends to the longest live blow and shake sums bounded", () => {
    const { scene } = fakeScene();
    const system = new ImpactSystem({ scene });
    expect(system.hitstopActive(1_000)).toBeFalse();
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: true, seed: 1, nowMs: 1_000 });
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 2, nowMs: 1_000 });
    expect(system.snapshot().hitstopUntilMs).toBe(1_000 + IMPACT_KILL_HITSTOP_MS);
    expect(system.hitstopActive(1_000 + IMPACT_KILL_HITSTOP_MS - 1)).toBeTrue();
    expect(system.hitstopActive(1_000 + IMPACT_KILL_HITSTOP_MS)).toBeFalse();
    for (let index = 0; index < 8; index += 1) {
      system.showHit({ x: 0, y: 0, dirSign: 1, critical: true, died: true, seed: index, nowMs: 1_000 });
    }
    for (let elapsedMs = 0; elapsedMs < IMPACT_SHAKE_MS; elapsedMs += 8) {
      const offset = system.shakeOffset(1_000 + elapsedMs);
      expect(Math.abs(offset.x)).toBeLessThanOrEqual(IMPACT_SHAKE_PX * IMPACT_CRITICAL_SCALE);
      expect(Math.abs(offset.y)).toBeLessThanOrEqual(IMPACT_SHAKE_PX * IMPACT_CRITICAL_SCALE);
    }
  });

  test("the cap evicts the oldest event and clears its flash", () => {
    const { scene } = fakeScene();
    const system = new ImpactSystem({ scene, maxActive: 2 });
    const first = new FakeTarget();
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 1, nowMs: 0, target: first });
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 2, nowMs: 0 });
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 3, nowMs: 0 });
    expect(system.snapshot().activeCount).toBe(2);
    expect(first.flashes).toEqual([true, false]);
    expect(system.snapshot().entries.map((entry) => entry.eventId)).toEqual([2, 3]);
  });

  test("disabled, invalid, cleared and disposed states show nothing", () => {
    const { scene, graphics } = fakeScene();
    const system = new ImpactSystem({ scene, enabled: false });
    expect(
      system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 1, nowMs: 0 }),
    ).toBeNull();
    system.setEnabled(true);
    expect(
      system.showHit({ x: Number.NaN, y: 0, dirSign: 1, critical: false, died: false, seed: 1, nowMs: 0 }),
    ).toBeNull();
    expect(
      system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 1.5, nowMs: 0 }),
    ).toBeNull();
    const target = new FakeTarget();
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: true, seed: 1, nowMs: 0, target });
    system.clear();
    expect(target.flashes).toEqual([true, false]);
    expect(system.hitstopActive(1)).toBeFalse();
    system.update(5);
    system.dispose();
    expect(graphics[0]!.destroyed).toBeTrue();
    expect(system.snapshot().disposed).toBeTrue();
    expect(
      system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: false, seed: 1, nowMs: 0 }),
    ).toBeNull();
  });

  test("reduced motion is carried on the event at the moment it is shown", () => {
    const { scene, graphics } = fakeScene();
    const system = new ImpactSystem({ scene, reducedMotion: true });
    system.showHit({ x: 0, y: 0, dirSign: 1, critical: false, died: true, seed: 1, nowMs: 0 });
    system.update(10);
    expect(graphics[0]!.lines).toHaveLength(0);
    expect(graphics[0]!.circles).toHaveLength(0);
    expect(system.shakeOffset(10)).toEqual({ x: 0, y: 0 });
    system.update(IMPACT_FLASH_MS);
    expect(system.snapshot().activeCount).toBe(0);
  });
});
