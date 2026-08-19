import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { dialogueSceneDemoFixture } from "@/lib/dialogue-scene/demo-fixture";
import DialogueSceneDemo from "./DialogueSceneDemo";

describe("dialogue-scene demo component contract", () => {
  test("renders deterministic status, composition layers, dialogue, and accessible controls", () => {
    const markup = renderToStaticMarkup(
      <DialogueSceneDemo fixture={dialogueSceneDemoFixture} />,
    );

    expect(markup).toContain("Visual Novel Scene Kit · playable romance vignette");
    expect(markup).toContain("deterministic fixture · no generation");
    expect(markup).toContain("15+ slow-burn romance");
    expect(markup).toContain("heroine age 23 · adult cast");
    expect(markup).toContain(dialogueSceneDemoFixture.background.src);
    for (const variant of dialogueSceneDemoFixture.expressionVariants) {
      expect(markup).toContain(variant.src);
    }
    expect(markup).toContain(dialogueSceneDemoFixture.appearance.conceptSrc);
    expect(markup).toContain(dialogueSceneDemoFixture.dialogue[0].text);
    expect(markup).toContain('aria-label="Previous dialogue beat"');
    expect(markup).toContain('aria-label="Next dialogue beat"');
    expect(markup).toContain('aria-controls="dialogue-scene-panel"');
    expect(markup).toContain("Hide dialogue");
    expect(markup).toContain('data-expression-state="neutral"');
    expect(markup).toContain("Expression set");
    expect(markup).toContain("no rig or frame animation");
    expect(markup).toContain('id="dialogue-scene-framing-range"');
    expect(markup).toContain('type="range"');
    expect(markup).toContain('min="25"');
    expect(markup).toContain('max="85"');
    expect(markup).toContain('value="70"');
    expect(markup).toContain('id="dialogue-scene-framing-number"');
    expect(markup).toContain("medium shot");
    expect(markup).toContain("framingZoom 70/100");
    expect(markup).toContain("Coarse-generation prompt for this state");
    expect(markup).toContain("FINAL CANVAS CROP IS MANDATORY");
    expect(markup).toContain("Deterministic presentation crop remains required");
    expect(markup).toContain("explicitly age 23");
    expect(markup).toContain("composed and attentive");
    expect(markup).toContain('data-source-framing-zoom="70"');
    expect(markup).toContain("This upper-body source is authored at ");
    expect(markup).toContain("cannot reveal unauthored anatomy");
    expect(markup).toContain("--sg-dialogue-framing-scale:1");
  });

  test("saturates a valid public fixture value before synchronizing bounded controls", () => {
    const looseFixture = {
      ...dialogueSceneDemoFixture,
      presentation: { ...dialogueSceneDemoFixture.presentation, framingZoom: 0 },
    };
    const markup = renderToStaticMarkup(<DialogueSceneDemo fixture={looseFixture} />);

    expect(markup).toContain("framingZoom 25/100");
    expect(markup).toContain("source-limited");
    expect(markup).toContain("--sg-dialogue-framing-scale:0.308");
    expect(markup.match(/value="25"/g)).toHaveLength(2);
    expect(markup).toContain('aria-invalid="false"');
  });
});
