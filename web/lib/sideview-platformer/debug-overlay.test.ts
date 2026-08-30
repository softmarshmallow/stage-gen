import { describe, expect, test } from "bun:test";
import {
  debugOverlayText,
  debugOverlayToggleRequested,
} from "./debug-overlay-policy";

describe("debug overlay", () => {
  test("toggles only for a fresh Command-modified press", () => {
    expect(
      debugOverlayToggleRequested({ justPressed: true, metaKey: true }),
    ).toBeTrue();
    expect(
      debugOverlayToggleRequested({ justPressed: true, metaKey: false }),
    ).toBeFalse();
    expect(
      debugOverlayToggleRequested({ justPressed: false, metaKey: true }),
    ).toBeFalse();
  });

  test("labels diagnostics and formats only populated inventory entries", () => {
    expect(
      debugOverlayText({
        health: 4,
        maximumHealth: 5,
        inventory: [
          { label: "Bellflower", quantity: 2 },
          { label: "Old Key", quantity: 0 },
        ],
      }),
    ).toBe("DEBUG\nHP 4/5\nBellflower ×2");
    expect(
      debugOverlayText({ health: 5, maximumHealth: 5, inventory: [] }),
    ).toContain("Inventory empty");
  });
});
