import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { dialogueSceneDemoFixture } from "@/lib/dialogue-scene/demo-fixture";
import DialogueSceneDemo, { DialogueSceneAdvanceButton } from "./DialogueSceneDemo";

describe("dialogue-scene demo component contract", () => {
  test("renders a game-first scene with accessible controls and no demo dossier", () => {
    const markup = renderToStaticMarkup(
      <DialogueSceneDemo fixture={dialogueSceneDemoFixture} />,
    );

    expect(markup).toContain('class="sg-dialogue-game-shell"');
    expect(markup).toContain('aria-label="Leave dialogue scene"');
    expect(markup).toContain("← Exit");
    expect(markup).toContain(dialogueSceneDemoFixture.title);
    expect(markup).toContain(dialogueSceneDemoFixture.sceneLabel);
    expect(markup).toContain(dialogueSceneDemoFixture.background.alt);
    expect(markup).toContain(dialogueSceneDemoFixture.background.src);
    expect(markup).toContain(dialogueSceneDemoFixture.expressionVariants[0].src);
    expect(markup).toContain(dialogueSceneDemoFixture.dialogue[0].text);
    expect(markup).toContain('aria-label="Previous dialogue beat"');
    expect(markup).toContain('aria-label="Next dialogue beat"');
    expect(markup).toContain('class="sg-btn sg-dialogue-advance"');
    expect(markup).toContain('data-control-state="advance"');
    expect(markup).toContain('aria-controls="dialogue-scene-panel"');
    expect(markup).toContain("Hide dialogue");
    expect(markup).toContain('data-expression-state="neutral"');
    expect(markup).toContain('aria-label="Dialogue navigation"');
    expect(markup).toContain("Display options");
    expect(markup).toContain("Character framing");
    expect(markup).toContain('id="dialogue-scene-framing-range"');
    expect(markup).toContain('type="range"');
    expect(markup).toContain('min="25"');
    expect(markup).toContain('max="85"');
    expect(markup).toContain('value="70"');
    expect(markup).toContain('id="dialogue-scene-framing-number"');
    expect(markup).toContain("medium shot");
    expect(markup).toContain("Character framing:");
    expect(markup).toContain('data-source-framing-zoom="70"');
    expect(markup).toContain("--sg-dialogue-framing-scale:1");
    expect(markup).not.toContain("technology demo");
    expect(markup).not.toContain("static fixture");
    expect(markup).not.toContain("Demo character");
    expect(markup).not.toContain("Expression switching");
    expect(markup).not.toContain("Show framing prompt");
    expect(markup).not.toContain("Show demo assets");
    expect(markup).not.toContain(dialogueSceneDemoFixture.appearance.conceptSrc);
  });

  test("renders an accessible restart action for the completed sequence", () => {
    const markup = renderToStaticMarkup(
      <DialogueSceneAdvanceButton complete onAction={() => undefined} />,
    );

    expect(markup).toContain('data-control-state="restart"');
    expect(markup).toContain('aria-label="Restart dialogue from first beat"');
    expect(markup).toContain("↻ Restart");
    expect(markup).not.toContain("disabled");
  });

  test("locks a readable focused primary-control treatment", () => {
    const css = readFileSync(path.resolve(import.meta.dir, "../../globals.css"), "utf8");
    expect(css).toContain(
      ".sg-dialogue-controls .sg-dialogue-advance:focus-visible:not(:disabled)",
    );
    expect(css).toMatch(
      /\.sg-dialogue-controls \.sg-dialogue-advance:focus-visible:not\(:disabled\)\s*\{[^}]*background: linear-gradient\(100deg, #f29abb[^}]*color: var\(--vn-ink\)/s,
    );
  });

  test("saturates a valid public fixture value before synchronizing bounded controls", () => {
    const looseFixture = {
      ...dialogueSceneDemoFixture,
      presentation: { ...dialogueSceneDemoFixture.presentation, framingZoom: 0 },
    };
    const markup = renderToStaticMarkup(<DialogueSceneDemo fixture={looseFixture} />);

    expect(markup).toContain("Character framing:");
    expect(markup).toContain("limited by source");
    expect(markup).toContain("--sg-dialogue-framing-scale:0.308");
    expect(markup.match(/value="25"/g)).toHaveLength(2);
    expect(markup).toContain('aria-invalid="false"');
  });
});
