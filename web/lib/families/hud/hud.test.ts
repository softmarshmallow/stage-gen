import { describe, expect, test } from "bun:test";
import { gaugeBarFillWidth, gaugeBarRevealedByChange, GAUGE_BAR_DIMMED_ALPHA } from "./gauge-bar";
import { silentReadout, type HudReadout } from "./readout";
import { parseHudBlock } from "./manifest";

// --- E4: one capsule, two places a bounded resource is read off ------------------------------

describe("E4: the gauge bar instantiated into two placements", () => {
  const runnerStyle = { width: 220, height: 14 } as const;
  const actorStyle = { width: 64, height: 8 } as const;

  test("a runner-shaped bar: screen furniture, and a fraction of a fixed width", () => {
    // The bar is pinned to the canvas and its width is the readout rect's.
    expect(gaugeBarFillWidth({ value: 3, max: 3, style: runnerStyle })).toBe(220);
    expect(gaugeBarFillWidth({ value: 0, max: 3, style: runnerStyle })).toBe(0);
    expect(gaugeBarFillWidth({ value: 1.5, max: 3, style: runnerStyle })).toBe(110);
  });

  test("a platformer-shaped bar: the same capsule under a body, at a smaller size", () => {
    // Placement, scroll factor and depth are the caller's; the drawing is not.
    expect(gaugeBarFillWidth({ value: 3, max: 12, style: actorStyle })).toBe(16);
    // Out-of-range readings are clamped rather than drawn past the capsule,
    // because a bar is a picture of a gauge and a gauge cannot read past full.
    expect(gaugeBarFillWidth({ value: 99, max: 12, style: actorStyle })).toBe(64);
    expect(gaugeBarFillWidth({ value: -1, max: 12, style: actorStyle })).toBe(0);
    // And a sliver never collapses below the capsule's own end caps.
    expect(gaugeBarFillWidth({ value: 0.01, max: 12, style: actorStyle })).toBe(8);
  });

  test("an undamaged actor's bar reports that nothing has happened", () => {
    // Which is why a stage carrying a dozen of them is not a dozen readouts
    // competing with the bodies they belong to.
    expect(gaugeBarRevealedByChange({ value: 3, max: 3 })).toBe(false);
    expect(gaugeBarRevealedByChange({ value: 2, max: 3 })).toBe(true);
    expect(gaugeBarRevealedByChange({ value: 1, max: 0 })).toBe(false);
    expect(GAUGE_BAR_DIMMED_ALPHA).toBeLessThan(1);
  });
});

// --- the readout port ---------------------------------------------------------------------------

type World = Readonly<{ hp: number }>;

describe("a readout is a view over slices and owns none of them", () => {
  test("it is handed the world rather than a view-model, deliberately", () => {
    // A readout that took a prepared model would need something to build the
    // model, and that something is a second place where what is true is decided.
    const seen: number[] = [];
    const readout: HudReadout<World> = { sync: (world) => seen.push(world.hp) };
    readout.sync({ hp: 6 });
    readout.sync({ hp: 5 });
    expect(seen).toEqual([6, 5]);
  });

  test("hiding is optional, because a readout with nothing to hide is an answer", () => {
    const readout: HudReadout<World> = { sync: () => undefined };
    expect(readout.hide).toBeUndefined();
  });

  test("E7: a HUD with nothing drawing it draws nothing and changes nothing", () => {
    const silent = silentReadout<World>();
    expect(() => {
      silent.sync({ hp: 1 });
      silent.hide?.();
    }).not.toThrow();
  });
});

describe("the block the family gates for itself", () => {
  test("it is `gameplay` and not `ui`, which is art direction the runner never publishes", () => {
    expect(
      parseHudBlock(
        { gameplay: "platformer-gameplay-block-v1" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ).published,
    ).toBe(true);
    expect(() =>
      parseHudBlock(
        { gameplay: "runner-gameplay-block-v2" },
        { block: "gameplay", version: "runner-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as runner-gameplay-block-v2');
  });
});
