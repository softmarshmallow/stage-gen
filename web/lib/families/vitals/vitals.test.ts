import { describe, expect, test } from "bun:test";
import { createGauge } from "@/lib/kernel/gauge";
import {
  bodyBlinkAlpha,
  bodyIsImmune,
  CONTACT_HURT_PROFILE,
  resolveVitals,
  vitalsClockMs,
  type Consequence,
  type VitalsSlice,
} from "./vitals";
import { parseVitalsBlock } from "./manifest";

/** A runner-shaped recovery: put the body down on a column and a row. */
type Surface = Readonly<{ column: number; row: number }>;
type RunSource = "hazard" | "pit" | "crush";

/** A platformer-shaped recovery: there is none; a defeated body waits for a respawn. */
type Contact = "contact";

function slice<R>(max: number | null): VitalsSlice<R> {
  return {
    gauge: max === null ? null : createGauge(max),
    clockMs: 0,
    pendingRecovery: null,
    hurtThisFrame: false,
    depletedThisFrame: false,
  };
}

const RUN_TABLE: Readonly<Record<RunSource, Consequence>> = Object.freeze({
  hazard: "drain_v1",
  pit: "drain_and_recover_v1",
  crush: "end_run_v1",
});

// --- E4: one family, two bodies with different sources and different recoveries -------------

describe("E4: the vitals family instantiated into two shapes", () => {
  test("a runner-shaped body: a table per source, and a recovery port that answers", () => {
    const vitals = slice<Surface>(3);
    const asked: RunSource[] = [];
    const drained = resolveVitals<RunSource, Surface>({
      vitals,
      sources: ["hazard"],
      consequences: RUN_TABLE,
      profile: CONTACT_HURT_PROFILE,
      recover: (source) => {
        asked.push(source);
        return { column: 12, row: 4 };
      },
    });
    expect(drained).toEqual([{ kind: "drained", source: "hazard", remaining: 2 }]);
    expect(vitals.hurtThisFrame).toBe(true);
    expect(vitals.pendingRecovery).toBe(null);
    // A draining consequence asks nothing of the space family.
    expect(asked).toEqual([]);

    // A forgiven fall does, and the answer is scheduled rather than applied:
    // the body emits the occurrence, so writing it back here is an order no
    // frame can satisfy.
    vitals.clockMs = 2000;
    const forgiven = resolveVitals<RunSource, Surface>({
      vitals,
      sources: ["pit"],
      consequences: RUN_TABLE,
      profile: CONTACT_HURT_PROFILE,
      recover: () => ({ column: 40, row: 8 }),
    });
    expect(forgiven).toEqual([{ kind: "drained", source: "pit", remaining: 1 }]);
    expect(vitals.pendingRecovery).toEqual({ column: 40, row: 8 });
  });

  test("a platformer-shaped body: one opaque source, no recovery, the same window", () => {
    const vitals = slice<never>(6);
    const table: Readonly<Record<Contact, Consequence>> = Object.freeze({ contact: "drain_v1" });
    const hit = () =>
      resolveVitals<Contact, never>({
        vitals,
        sources: ["contact"],
        consequences: table,
        profile: CONTACT_HURT_PROFILE,
        recover: () => null,
      });
    expect(hit()).toEqual([{ kind: "drained", source: "contact", remaining: 5 }]);
    // Standing inside a creature: the window absorbs everything for 900ms,
    // which is what makes contact survivable in either genre.
    expect(hit()).toEqual([{ kind: "absorbed", source: "contact" }]);
    expect(bodyIsImmune(vitals)).toBe(true);
    expect(bodyBlinkAlpha(vitals, CONTACT_HURT_PROFILE)).toBeLessThanOrEqual(1);
    vitals.clockMs = CONTACT_HURT_PROFILE.refractoryMs;
    expect(bodyIsImmune(vitals)).toBe(false);
    expect(hit()).toEqual([{ kind: "drained", source: "contact", remaining: 4 }]);
  });
});

describe("what the table decides, and what it refuses to forgive", () => {
  test("a compound accident in one frame costs one point, not three", () => {
    const vitals = slice<Surface>(3);
    const verdicts = resolveVitals<RunSource, Surface>({
      vitals,
      sources: ["hazard", "hazard", "hazard"],
      consequences: RUN_TABLE,
      profile: CONTACT_HURT_PROFILE,
      recover: () => null,
    });
    expect(verdicts.map((verdict) => verdict.kind)).toEqual(["drained", "absorbed", "absorbed"]);
    expect(vitals.gauge?.value).toBe(2);
  });

  test("a terminal consequence ends it, and nothing after it is resolved", () => {
    const vitals = slice<Surface>(3);
    const verdicts = resolveVitals<RunSource, Surface>({
      vitals,
      sources: ["crush", "hazard"],
      consequences: RUN_TABLE,
      profile: CONTACT_HURT_PROFILE,
      recover: () => null,
    });
    expect(verdicts).toEqual([{ kind: "ended", source: "crush" }]);
    expect(vitals.gauge?.value).toBe(3);
  });

  test("an unanswered source, and a draining one with no gauge, both end it", () => {
    const unanswered = slice<Surface>(3);
    expect(
      resolveVitals<RunSource, Surface>({
        vitals: unanswered,
        sources: ["pit"],
        consequences: { hazard: "drain_v1" },
        profile: CONTACT_HURT_PROFILE,
        recover: () => null,
      }),
    ).toEqual([{ kind: "ended", source: "pit" }]);

    const gaugeless = slice<Surface>(null);
    expect(
      resolveVitals<RunSource, Surface>({
        vitals: gaugeless,
        sources: ["hazard"],
        consequences: RUN_TABLE,
        profile: CONTACT_HURT_PROFILE,
        recover: () => null,
      }),
    ).toEqual([{ kind: "ended", source: "hazard" }]);
  });

  test("a forgiving package with nowhere to stand ends the run rather than teleporting", () => {
    const vitals = slice<Surface>(3);
    const verdicts = resolveVitals<RunSource, Surface>({
      vitals,
      sources: ["pit"],
      consequences: RUN_TABLE,
      profile: CONTACT_HURT_PROFILE,
      recover: () => null,
    });
    expect(verdicts).toEqual([
      { kind: "drained", source: "pit", remaining: 2 },
      { kind: "ended", source: "pit" },
    ]);
    expect(vitals.pendingRecovery).toBe(null);
  });

  test("the last point spent reports the depletion once", () => {
    const vitals = slice<never>(1);
    const verdicts = resolveVitals<Contact, never>({
      vitals,
      sources: ["contact"],
      consequences: { contact: "drain_v1" },
      profile: CONTACT_HURT_PROFILE,
      recover: () => null,
    });
    expect(verdicts).toEqual([
      { kind: "drained", source: "contact", remaining: 0 },
      { kind: "ended", source: "contact" },
    ]);
    expect(vitals.depletedThisFrame).toBe(true);
  });

  test("the clock is converted once: steps count seconds, gauges count milliseconds", () => {
    expect(vitalsClockMs(2)).toBe(2000);
  });
});

describe("the block the family gates for itself", () => {
  test("a moved block is refused by name", () => {
    expect(() =>
      parseVitalsBlock(
        { gameplay: "runner-gameplay-block-v2" },
        { block: "gameplay", version: "runner-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as runner-gameplay-block-v2');
  });
});
