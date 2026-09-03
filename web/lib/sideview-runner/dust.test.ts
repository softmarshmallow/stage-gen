import { describe, expect, test } from "bun:test";
import { stepAvatar } from "./avatar";
import { parseRunnerRuntimeManifest } from "./contract";
import {
  createDustSystem,
  DUST_LAND_PUFFS,
  DUST_PUFF_LIFE_MS,
  DUST_SLIDE_INTERVAL_MS,
  DUST_STRIDE_INTERVAL_MS,
  DUST_TAKEOFF_PUFFS,
  dustCloudLobes,
  dustRecordSpent,
  dustUnitNoise,
  sampleDustPuff,
  type DustPuff,
  type DustRecord,
} from "./dust";
import { runnerManifestFixture } from "./fixture";
import { runnerIntent } from "./intent";
import { createRunnerWorld, rowToScreenY } from "./world";

const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

const RECORD: DustRecord = Object.freeze({
  kind: "stride",
  index: 0,
  seed: 0x5eed_1234,
  bornAtMs: 1_000,
  feetX: 320,
  feetY: 560,
  scrollXAtBirth: 4_000,
  tilePx: 64,
  intensity: 0,
});

function stepAt(frame: number) {
  return { dt: 1 / 60, now: frame / 60, frame } as const;
}

function recorder() {
  const frames: DustPuff[][] = [];
  return {
    frames,
    begin: () => {
      frames.push([]);
    },
    puff: (puff: DustPuff) => {
      frames[frames.length - 1]?.push(puff);
    },
    last: () => frames[frames.length - 1] ?? [],
  };
}

function runningWorld() {
  const world = createRunnerWorld(manifest, 1, { intro: false });
  world.run.phase = "running";
  return world;
}

describe("sampleDustPuff", () => {
  test("is a pure function of the record and the instant", () => {
    const first = sampleDustPuff(RECORD, 1_100, 4_200);
    const again = sampleDustPuff(RECORD, 1_100, 4_200);
    expect(first).toEqual(again);
    expect(first).not.toBeNull();
  });

  test("is unborn before its frame and spent after its life", () => {
    expect(sampleDustPuff(RECORD, 999, 4_000)).toBeNull();
    expect(sampleDustPuff(RECORD, 1_000, 4_000)).not.toBeNull();
    expect(sampleDustPuff(RECORD, 1_000 + DUST_PUFF_LIFE_MS, 4_000)).toBeNull();
    expect(dustRecordSpent(RECORD, 1_000 + DUST_PUFF_LIFE_MS)).toBe(true);
    expect(dustRecordSpent(RECORD, 1_000 + DUST_PUFF_LIFE_MS - 1)).toBe(false);
  });

  test("belongs to the ground: it slides back exactly as far as the camera scrolled", () => {
    const still = sampleDustPuff(RECORD, 1_200, 4_000);
    const scrolled = sampleDustPuff(RECORD, 1_200, 4_150);
    expect(still).not.toBeNull();
    expect(scrolled).not.toBeNull();
    expect(still!.x - scrolled!.x).toBeCloseTo(150, 6);
    expect(still!.y).toBe(scrolled!.y);
  });

  test("swells, lifts and thins over its life, and never leaves the ground's side", () => {
    const young = sampleDustPuff(RECORD, 1_020, 4_000)!;
    const old = sampleDustPuff(RECORD, 1_300, 4_000)!;
    expect(old.radiusX).toBeGreaterThan(young.radiusX);
    expect(old.y).toBeLessThan(young.y);
    expect(old.alpha).toBeLessThan(young.alpha);
    // Solid through the first part of its life; the fade is the last act, not the whole one.
    expect(young.alpha).toBe(1);
    expect(sampleDustPuff(RECORD, 1_000 + DUST_PUFF_LIFE_MS * 0.5, 4_000)!.alpha).toBe(1);
    // Flat and wide at the heel, rounder once it has lifted.
    expect(young.radiusX / young.radiusY).toBeGreaterThan(old.radiusX / old.radiusY);
    // Seated on the line rather than straddling it: the newborn's underside is at the datum.
    expect(young.y + young.radiusY).toBeLessThanOrEqual(RECORD.feetY + young.radiusY * 0.31);
    expect(young.y).toBeLessThan(RECORD.feetY);
  });

  test("a puff is drawn as three lobes that share its centre and rise on its shoulders", () => {
    const puff = sampleDustPuff(RECORD, 1_200, 4_000)!;
    const lobes = dustCloudLobes(puff);
    expect(lobes).toHaveLength(3);
    expect(lobes[0]).toEqual({ x: puff.x, y: puff.y, radiusX: puff.radiusX, radiusY: puff.radiusY });
    for (const lobe of lobes.slice(1)) {
      expect(lobe.y).toBeLessThan(puff.y);
      expect(lobe.radiusX).toBeLessThan(puff.radiusX);
    }
  });

  test("a stride puff grows with the speed ramp; every other kind ignores it", () => {
    const slow = sampleDustPuff({ ...RECORD, intensity: 0 }, 1_200, 4_000)!;
    const fast = sampleDustPuff({ ...RECORD, intensity: 1 }, 1_200, 4_000)!;
    expect(fast.radiusX).toBeGreaterThan(slow.radiusX);
    const landSlow = sampleDustPuff({ ...RECORD, kind: "land", intensity: 0 }, 1_200, 4_000)!;
    const landFast = sampleDustPuff({ ...RECORD, kind: "land", intensity: 1 }, 1_200, 4_000)!;
    expect(landFast.radiusX).toBe(landSlow.radiusX);
  });

  test("a landing splays both ways and a takeoff throws back", () => {
    const left = sampleDustPuff({ ...RECORD, kind: "land", index: 0 }, 1_300, 4_000)!;
    const right = sampleDustPuff({ ...RECORD, kind: "land", index: 1 }, 1_300, 4_000)!;
    expect(left.x).toBeLessThan(RECORD.feetX);
    expect(right.x).toBeGreaterThan(RECORD.feetX);
    for (let index = 0; index < DUST_TAKEOFF_PUFFS; index += 1) {
      const puff = sampleDustPuff({ ...RECORD, kind: "takeoff", index }, 1_300, 4_000)!;
      expect(puff.x).toBeLessThan(RECORD.feetX);
      expect(puff.y).toBeLessThan(RECORD.feetY);
    }
  });

  test("noise is stable per seed and channel and lives in the unit interval", () => {
    expect(dustUnitNoise(7, 3)).toBe(dustUnitNoise(7, 3));
    expect(dustUnitNoise(7, 3)).not.toBe(dustUnitNoise(7, 4));
    for (let channel = 0; channel < 64; channel += 1) {
      const value = dustUnitNoise(0x1234, channel);
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
  });
});

describe("createDustSystem", () => {
  test("declares itself as presentation pinned behind the audio system", () => {
    const system = createDustSystem(recorder());
    expect(system.id).toBe("runner/dust");
    expect(system.writes).toEqual([]);
    expect(system.after).toContain("runner/audio");
  });

  test("a run lays a stride puff on the cadence, locked to where the feet stood", () => {
    const world = runningWorld();
    const canvas = recorder();
    const system = createDustSystem(canvas);
    system.update(world, stepAt(1));
    expect(system.snapshot().activeCount).toBe(1);
    const first = system.snapshot().records[0]!;
    expect(first.kind).toBe("stride");
    expect(first.feetX).toBe(world.config.avatarScreenX);
    expect(first.feetY).toBe(rowToScreenY(world.avatar.y, world.config));
    expect(canvas.last()).toHaveLength(1);

    // Frames inside the same cadence tick lay nothing new; the next tick lays one.
    const perTick = Math.floor(DUST_STRIDE_INTERVAL_MS / (1000 / 60));
    for (let frame = 2; frame <= perTick; frame += 1) system.update(world, stepAt(frame));
    expect(system.snapshot().activeCount).toBe(1);
    system.update(world, stepAt(perTick + 1));
    expect(system.snapshot().activeCount).toBe(2);
  });

  test("a ground takeoff bursts once; the air jump kicks no ground", () => {
    const world = runningWorld();
    const system = createDustSystem(recorder());
    system.update(world, stepAt(1));
    const before = system.snapshot().activeCount;

    world.intent = runnerIntent({ jump: true });
    stepAvatar(world, 1 / 60);
    system.update(world, stepAt(2));
    const kinds = system.snapshot().records.map((record) => record.kind);
    expect(kinds.filter((kind) => kind === "takeoff")).toHaveLength(DUST_TAKEOFF_PUFFS);
    expect(system.snapshot().activeCount).toBe(before + DUST_TAKEOFF_PUFFS);

    stepAvatar(world, 1 / 60);
    system.update(world, stepAt(3));
    expect(system.snapshot().activeCount).toBe(before + DUST_TAKEOFF_PUFFS);
  });

  test("a landing splays a burst on the frame the feet touch down", () => {
    const world = runningWorld();
    const system = createDustSystem(recorder());
    system.update(world, stepAt(1));
    world.avatar.grounded = false;
    world.avatar.motion = "jump";
    system.update(world, stepAt(2));
    world.avatar.grounded = true;
    world.avatar.motion = "run";
    system.update(world, stepAt(3));
    const lands = system.snapshot().records.filter((record) => record.kind === "land");
    expect(lands).toHaveLength(DUST_LAND_PUFFS);
    expect(lands.map((record) => record.index)).toEqual([0, 1, 2, 3]);
  });

  test("a slide lays its first puff at once and then denser than a run", () => {
    const world = runningWorld();
    const system = createDustSystem(recorder());
    world.intent = runnerIntent({ duck: true });
    stepAvatar(world, 1 / 60);
    expect(world.avatar.sliding).toBe(true);
    system.update(world, stepAt(1));
    const slides = () => system.snapshot().records.filter((record) => record.kind === "slide");
    expect(slides()).toHaveLength(1);
    expect(system.snapshot().records.some((record) => record.kind === "stride")).toBe(false);
    const perTick = Math.ceil(DUST_SLIDE_INTERVAL_MS / (1000 / 60));
    for (let frame = 2; frame <= perTick + 1; frame += 1) system.update(world, stepAt(frame));
    expect(slides().length).toBeGreaterThanOrEqual(2);
    expect(DUST_SLIDE_INTERVAL_MS).toBeLessThan(DUST_STRIDE_INTERVAL_MS);
  });

  test("spent puffs are forgotten and the active cap drops the oldest", () => {
    const world = runningWorld();
    const system = createDustSystem(recorder(), { maxActive: 2 });
    system.update(world, stepAt(1));
    world.avatar.grounded = false;
    system.update(world, stepAt(2));
    world.avatar.grounded = true;
    system.update(world, stepAt(3));
    expect(system.snapshot().activeCount).toBe(2);
    // Everything born so far is spent once a whole life has passed.
    const later = 3 + Math.ceil(DUST_PUFF_LIFE_MS / (1000 / 60)) + 1;
    world.avatar.grounded = false;
    system.update(world, stepAt(later));
    expect(system.snapshot().activeCount).toBe(0);
  });

  test("a restart forgets the dust of the run that ended", () => {
    const world = runningWorld();
    const system = createDustSystem(recorder());
    world.avatar.distanceColumns = 40;
    system.update(world, stepAt(1));
    expect(system.snapshot().activeCount).toBe(1);
    world.avatar.distanceColumns = 2;
    system.update(world, stepAt(2));
    expect(system.snapshot().activeCount).toBe(0);
  });

  test("nothing is laid outside the running phase or under reduced motion", () => {
    const intro = createRunnerWorld(manifest, 1);
    intro.run.phase = "intro";
    const canvas = recorder();
    const system = createDustSystem(canvas);
    system.update(intro, stepAt(1));
    expect(system.snapshot().activeCount).toBe(0);
    expect(canvas.frames).toHaveLength(1);
    expect(canvas.last()).toEqual([]);

    const quiet = createDustSystem(recorder(), { reducedMotion: true });
    quiet.update(runningWorld(), stepAt(1));
    expect(quiet.snapshot().activeCount).toBe(0);
    expect(quiet.snapshot().reducedMotion).toBe(true);
  });

  test("the drawing follows the scroll frame by frame", () => {
    const world = runningWorld();
    const canvas = recorder();
    const system = createDustSystem(canvas);
    system.update(world, stepAt(1));
    const before = canvas.last()[0]!;
    world.camera.scrollX += 30;
    world.avatar.grounded = false;
    system.update(world, stepAt(2));
    const after = canvas.last()[0]!;
    // The puff moved back by the scroll, plus the little it was thrown back on its own.
    expect(before.x - after.x).toBeGreaterThanOrEqual(30);
  });
});
