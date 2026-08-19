import { describe, expect, test } from "bun:test";
import rawFixture from "./demo-fixture.json";
import { dialogueSceneDemoFixture } from "./demo-fixture";
import { parseDialogueSceneDemoFixture } from "./schema";

function mutableFixture(): Record<string, unknown> {
  return structuredClone(rawFixture) as unknown as Record<string, unknown>;
}

describe("dialogue-scene deterministic fixture schema", () => {
  test("parses and freezes the committed caller-authored fixture", () => {
    expect(dialogueSceneDemoFixture.schemaVersion).toBe(1);
    expect(dialogueSceneDemoFixture.mode).toBe("deterministic-demo");
    expect(dialogueSceneDemoFixture.authorship).toBe("caller-authored");
    expect(dialogueSceneDemoFixture.background.src).toBe(
      "/dialogue-scene/demo/anime/background.png",
    );
    expect(dialogueSceneDemoFixture.expressionVariants.map((variant) => variant.state)).toEqual([
      "neutral",
      "delighted",
      "flustered",
      "concerned",
    ]);
    expect(dialogueSceneDemoFixture.expressionVariants[0].src).toBe(
      "/dialogue-scene/demo/anime/heroine-neutral.png",
    );
    expect(dialogueSceneDemoFixture.appearance.conceptSrc).toBe(
      "/dialogue-scene/demo/anime/concept-key-art.png",
    );
    expect(dialogueSceneDemoFixture.appearance.age).toBe(23);
    expect(dialogueSceneDemoFixture.presentation.framingZoom).toBe(70);
    expect(dialogueSceneDemoFixture.presentation.sourceFramingZoom).toBe(70);
    expect(dialogueSceneDemoFixture.dialogue).toHaveLength(8);
    expect(Object.isFrozen(dialogueSceneDemoFixture)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.presentation)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.expressionVariants)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.expressionVariants[0])).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.dialogue)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.dialogue[0])).toBeTrue();
  });

  test("rejects unknown fields and paths outside the demo asset root", () => {
    const unknownField = mutableFixture();
    unknownField.unexpected = true;
    expect(() => parseDialogueSceneDemoFixture(unknownField)).toThrow(
      "unexpected unexpected",
    );

    const escapedPath = mutableFixture();
    (escapedPath.background as Record<string, unknown>).src = "../background.png";
    expect(() => parseDialogueSceneDemoFixture(escapedPath)).toThrow(
      "confined /dialogue-scene/demo/**/*.png path",
    );
  });

  test("binds every expression variant to one adult appearance identity", () => {
    const mismatch = mutableFixture();
    const variants = mismatch.expressionVariants as Record<string, unknown>[];
    variants[0].appearanceId = "another-appearance";
    expect(() => parseDialogueSceneDemoFixture(mismatch)).toThrow(
      "expression variant must reference appearance.id",
    );

    const minor = mutableFixture();
    (minor.appearance as Record<string, unknown>).age = 17;
    expect(() => parseDialogueSceneDemoFixture(minor)).toThrow(
      "appearance.age must be an integer from 21 to 120",
    );
  });

  test("requires one of each expression state and binds every beat to the vocabulary", () => {
    const duplicatedState = mutableFixture();
    const variants = duplicatedState.expressionVariants as Record<string, unknown>[];
    variants[1].state = "neutral";
    expect(() => parseDialogueSceneDemoFixture(duplicatedState)).toThrow(
      "expression state is duplicated: neutral",
    );

    const unknownBeatState = mutableFixture();
    const dialogue = unknownBeatState.dialogue as Record<string, unknown>[];
    dialogue[0].expressionState = "surprised";
    expect(() => parseDialogueSceneDemoFixture(unknownBeatState)).toThrow(
      "must be one of neutral, delighted, flustered, concerned",
    );
  });

  test("requires a finite public framing value from 0 through 100", () => {
    for (const invalid of [Number.NaN, Number.POSITIVE_INFINITY, -0.1, 100.1, "70"]) {
      const fixture = mutableFixture();
      (fixture.presentation as Record<string, unknown>).framingZoom = invalid;
      expect(() => parseDialogueSceneDemoFixture(fixture)).toThrow(
        "presentation.framingZoom must be a finite number from 0 to 100",
      );
    }

    const invalidBaseline = mutableFixture();
    (invalidBaseline.presentation as Record<string, unknown>).sourceFramingZoom = 101;
    expect(() => parseDialogueSceneDemoFixture(invalidBaseline)).toThrow(
      "presentation.sourceFramingZoom must be a finite number from 0 to 100",
    );
  });
});
