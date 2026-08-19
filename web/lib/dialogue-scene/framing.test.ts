import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";
import {
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN,
  mapDialogueSceneFraming,
  normalizeDialogueSceneFramingScale,
} from "./framing";

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

describe("dialogue-scene evidence-backed framing mapper", () => {
  test("reproduces the exact tested crop-first prompts", () => {
    expect(sha256(mapDialogueSceneFraming(60).prompt.text)).toBe(
      "aaabbe85d5d6e1a8828b9384e334318784a308810eda36274cb6bcbea328daa5",
    );
    expect(sha256(mapDialogueSceneFraming(85).prompt.text)).toBe(
      "86dc758f8a94cf8ef2f8f71f80a927a5042683f2000213ad74a661a3be3a22f0",
    );
  });

  test("interpolates audit bands and uses the tighter semantic tier on ties", () => {
    const lowerTie = mapDialogueSceneFraming(42.5);
    expect(lowerTie.semanticTier).toBe("waist-up");
    expect(lowerTie.cameraTerm).toBe("medium shot");
    expect(lowerTie.bands.faceHeightPercent).toEqual([12.5, 18.5]);
    expect(lowerTie.bands.headroomPercent).toEqual([4, 8]);

    const upperTie = mapDialogueSceneFraming(72.5);
    expect(upperTie.semanticTier).toBe("head-and-shoulders");
    expect(upperTie.cameraTerm).toBe("close-up");
    expect(upperTie.bands.faceHeightPercent).toEqual([26, 36]);
    expect(upperTie.bands.headroomPercent).toEqual([3.5, 7.5]);
  });

  test("saturates unsupported generation geometry while retaining the public clamp", () => {
    const loose = mapDialogueSceneFraming(-20);
    expect(loose.clampedZoom).toBe(0);
    expect(loose.effectiveZoom).toBe(DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN);
    expect(loose.saturated).toBeTrue();
    expect(loose.semanticTier).toBe("full-body");
    expect(loose.prompt.text).toContain("framingZoom=0/100");

    const tight = mapDialogueSceneFraming(140);
    expect(tight.clampedZoom).toBe(100);
    expect(tight.effectiveZoom).toBe(DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX);
    expect(tight.saturated).toBeTrue();
    expect(tight.semanticTier).toBe("head-and-shoulders");
    expect(tight.prompt.text).toContain("framingZoom=100/100");
  });

  test("marks prompts as coarse guidance and returns a deterministic final crop", () => {
    const framing = mapDialogueSceneFraming(70);
    expect(framing.effectiveZoom).toBe(70);
    expect(framing.saturated).toBeFalse();
    expect(framing.cameraTerm).toBe("medium shot");
    expect(framing.bands.faceHeightPercent).toEqual([24.4, 34]);
    expect(framing.bands.headroomPercent).toEqual([3.6, 7.6]);
    expect(framing.prompt).toMatchObject({
      method: "hybrid-crop-first-v2",
      role: "coarse-generation-guidance",
      requiresDeterministicFinalCrop: true,
    });
    expect(framing.presentation).toEqual({
      scale: 3.244,
      position: { xPercent: 58, yPercent: 5.6 },
      transformOrigin: "top center",
    });
    expect(Object.isFrozen(framing)).toBeTrue();
    expect(Object.isFrozen(framing.presentation.position)).toBeTrue();
  });

  test("rejects non-finite inputs", () => {
    expect(() => mapDialogueSceneFraming(Number.NaN)).toThrow("finite number");
    expect(() => mapDialogueSceneFraming(Number.POSITIVE_INFINITY)).toThrow(
      "finite number",
    );
    expect(() => mapDialogueSceneFraming(Number.NEGATIVE_INFINITY)).toThrow(
      "finite number",
    );
  });

  test("accepts fixture-specific identity, style, and expression prompt context", () => {
    const result = mapDialogueSceneFraming(70, {
      identity: ["one original adult heroine, age 23", "same star hairpin"],
      style: ["original polished 2D anime game art"],
      expression: "warmly flustered with a shy half-smile",
      tierOverrides: {
        "waist-up": {
          cropDirective: "bottom edge crosses the natural waist below the cardigan",
          visibleAnatomy: "head, shoulders, torso, and upper arms",
        },
      },
    });

    expect(result.prompt.text).toContain("one original adult heroine, age 23");
    expect(result.prompt.text).toContain("same star hairpin");
    expect(result.prompt.text).toContain("original polished 2D anime game art");
    expect(result.prompt.text).toContain("warmly flustered with a shy half-smile");
    expect(result.prompt.text).toContain(
      "bottom edge crosses the natural waist below the cardigan",
    );
    expect(result.cropDirective).toBe(
      "bottom edge crosses the natural waist below the cardigan",
    );
    expect(result.presentation.scale).toBe(3.244);

    expect(() =>
      mapDialogueSceneFraming(70, {
        identity: [],
        style: ["original polished 2D anime game art"],
        expression: "neutral",
      }),
    ).toThrow("non-empty trimmed identity, style, and expression text");
  });

  test("normalizes presentation scale to an authored source-framing baseline", () => {
    const baseline = mapDialogueSceneFraming(70);
    expect(
      normalizeDialogueSceneFramingScale(
        mapDialogueSceneFraming(70).presentation.scale,
        baseline.presentation.scale,
      ),
    ).toBe(1);
    expect(
      normalizeDialogueSceneFramingScale(
        mapDialogueSceneFraming(25).presentation.scale,
        baseline.presentation.scale,
      ),
    ).toBe(0.308);
    expect(
      normalizeDialogueSceneFramingScale(
        mapDialogueSceneFraming(85).presentation.scale,
        baseline.presentation.scale,
      ),
    ).toBe(1.37);
    expect(() => normalizeDialogueSceneFramingScale(1, 0)).toThrow(
      "finite positive numbers",
    );
  });
});
