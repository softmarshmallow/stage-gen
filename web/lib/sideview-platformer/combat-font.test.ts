import { describe, expect, test } from "bun:test";

import { loadCombatTextFont } from "./combat-font";

describe("combat text font loading", () => {
  test("is a no-op in non-rendering environments", async () => {
    expect(await loadCombatTextFont(null)).toBe("unsupported");
  });

  test("registers its committed face even when browser fallback makes check return true", async () => {
    const face = Object.freeze({}) as FontFace;
    let additions = 0;
    expect(
      await loadCombatTextFont({
        createFace: () => ({ load: async () => face }),
        addFace: (loaded) => {
          expect(loaded).toBe(face);
          additions += 1;
        },
        check: () => true,
        awaitUsable: async () => undefined,
      }),
    ).toBe("loaded");
    expect(additions).toBe(1);
  });

  test("loads, installs, and proves numeric glyphs", async () => {
    let usable = false;
    let additions = 0;
    const face = Object.freeze({}) as FontFace;
    expect(
      await loadCombatTextFont({
        createFace: () => ({ load: async () => face }),
        addFace: (loaded) => {
          expect(loaded).toBe(face);
          additions += 1;
        },
        check: () => usable,
        awaitUsable: async () => {
          usable = true;
        },
      }),
    ).toBe("loaded");
    expect(additions).toBe(1);
  });

  test("fails closed when the browser still cannot use the loaded face", async () => {
    const face = Object.freeze({}) as FontFace;
    expect(
      loadCombatTextFont({
        createFace: () => ({ load: async () => face }),
        addFace: () => undefined,
        check: () => false,
        awaitUsable: async () => undefined,
      }),
    ).rejects.toThrow("not usable for numeric glyphs");
  });
});
