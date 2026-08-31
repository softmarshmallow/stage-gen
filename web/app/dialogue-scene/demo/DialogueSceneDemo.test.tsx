import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { dialogueSceneDemoFixture } from "@/lib/dialogue-scene/demo-fixture";
import DialogueSceneDemo, { DialogueSceneAdvanceButton } from "./DialogueSceneDemo";

describe("dialogue-scene demo component contract", () => {
  test("the committed demo is a branching scenario, not a straight line", () => {
    const { scenario } = dialogueSceneDemoFixture;
    const choices = scenario.blocks.flatMap((block) =>
      block.statements.filter((statement) => statement.kind === "choice"),
    );
    expect(choices.length).toBeGreaterThan(0);
    expect(scenario.endings.length).toBeGreaterThan(1);
    // Every choice option has to name a block that exists, or the demo route
    // would offer the player a dead end.
    const labels = new Set(scenario.blocks.map((block) => block.label));
    for (const choice of choices) {
      if (choice.kind !== "choice") continue;
      for (const option of choice.options) expect(labels.has(option.target)).toBeTrue();
    }
  });

  test("renders a game-first scene with accessible controls and no demo dossier", () => {
    const markup = renderToStaticMarkup(
      <DialogueSceneDemo fixture={dialogueSceneDemoFixture} />,
    );

    expect(markup).toContain("data-vn-game-shell");
    expect(markup).toContain('aria-label="Leave dialogue scene"');
    expect(markup).toContain("← Exit");
    expect(markup).toContain(dialogueSceneDemoFixture.title);
    expect(markup).toContain(dialogueSceneDemoFixture.sceneLabel);
    expect(markup).toContain(dialogueSceneDemoFixture.background.alt);
    expect(markup).toContain(dialogueSceneDemoFixture.background.src);
    expect(markup).toContain(dialogueSceneDemoFixture.expressionVariants[0].src);
    const opening = dialogueSceneDemoFixture.scenario.blocks[0]!.statements.find(
      (statement) => statement.kind === "line",
    );
    expect(opening?.kind).toBe("line");
    if (opening?.kind === "line") expect(markup).toContain(opening.text);
    expect(markup).toContain('aria-label="Previous dialogue beat"');
    expect(markup).toContain('aria-label="Next dialogue beat"');
    expect(markup).toContain('data-primary="true"');
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
    expect(markup).not.toContain('disabled="');
  });

  test("locks a readable focused primary-control treatment", () => {
    // Focus must not strip the fill off the one loud control: a focused
    // advance button keeps its gradient and dark ink, and gains a ring that
    // reads against the night sky rather than disappearing into it.
    const markup = renderToStaticMarkup(
      <DialogueSceneAdvanceButton complete={false} onAction={() => undefined} />,
    );

    expect(markup).toContain(
      "enabled:bg-[linear-gradient(100deg,#f29abb,#f7bfd3_56%,#ffd69b)]",
    );
    expect(markup).toContain("enabled:text-vn-ink");
    expect(markup).toContain("enabled:focus-visible:border-[#fff4f8]");
    expect(markup).toContain(
      "enabled:focus-visible:shadow-[0_0_0_2px_var(--color-vn-night),0_9px_28px_rgba(203,112,166,0.32)]",
    );
    expect(markup).toContain("focus-visible:outline-vn-teal");
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
