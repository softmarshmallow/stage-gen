import { describe, expect, test } from "bun:test";
import {
  BUST_ENTRY_OFFSET,
  CUT_IN_CHOREOGRAPHIES,
  CUT_IN_DIM,
  cutInFrame,
  RIP_ENTRY_SCALE,
} from "./cut-in";

const beats = CUT_IN_CHOREOGRAPHIES.tear_reveal_v1;

describe("cutInFrame", () => {
  test("starts with the rip off-screen right and the portrait held back", () => {
    const frame = cutInFrame(0, beats);
    expect(frame.ripX).toBe(1);
    expect(frame.ripScale).toBe(RIP_ENTRY_SCALE);
    expect(frame.bustDx).toBeCloseTo(BUST_ENTRY_OFFSET, 9);
    expect(frame.dim).toBe(0);
    expect(frame.released).toBe(false);
    expect(frame.finished).toBe(false);
  });

  test("the rip lands at rest and unit scale when its sweep ends", () => {
    const frame = cutInFrame(beats.ripInEndMs, beats);
    expect(frame.ripX).toBeCloseTo(0, 6);
    expect(frame.ripScale).toBeCloseTo(1, 6);
  });

  test("the portrait overshoots past centre on its way in, then settles", () => {
    const mid = cutInFrame((beats.bustInStartMs + beats.bustInEndMs) * 0.7, beats);
    expect(mid.bustDx).toBeGreaterThan(0);
    const settled = cutInFrame(beats.bustInEndMs, beats);
    expect(settled.bustDx).toBeCloseTo(0, 6);
    expect(settled.bustScale).toBeCloseTo(1, 6);
  });

  test("the hold pushes in slowly and dims the frame beneath", () => {
    const early = cutInFrame(beats.dimFromMs - 1, beats);
    const late = cutInFrame(beats.releaseMs - 1, beats);
    expect(early.dim).toBe(0);
    expect(late.dim).toBe(CUT_IN_DIM);
    expect(late.bustScale).toBeGreaterThan(early.bustScale);
  });

  test("release precedes finish, and the tear-away carries the rip off left", () => {
    const released = cutInFrame(beats.releaseMs, beats);
    expect(released.released).toBe(true);
    expect(released.finished).toBe(false);
    const gone = cutInFrame(beats.durationMs, beats);
    expect(gone.finished).toBe(true);
    expect(gone.ripX).toBeLessThan(-1);
    expect(gone.bannerX).toBeLessThan(-1);
  });

  test("the stripes never stop drifting", () => {
    expect(cutInFrame(1000, beats).stripePhase).toBeGreaterThan(cutInFrame(500, beats).stripePhase);
  });

  test("refuses a clock it cannot draw", () => {
    expect(() => cutInFrame(Number.NaN, beats)).toThrow("non-negative finite");
    expect(() => cutInFrame(-1, beats)).toThrow("non-negative finite");
  });

  test("every frame is frozen", () => {
    expect(Object.isFrozen(cutInFrame(10, beats))).toBe(true);
  });
});
