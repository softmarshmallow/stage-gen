import { describe, expect, test } from "bun:test";

import {
  dialogueChoiceForKey,
  dialogueChoicePrompt,
  MAX_DIALOGUE_CHOICES,
} from "./dialogue-choices";
import type { ScenarioChoiceOption } from "@/lib/scenario/program";

function options(...texts: readonly string[]): readonly ScenarioChoiceOption[] {
  return texts.map((text, index) =>
    Object.freeze({ text, target: `target_${index}`, condition: null }),
  );
}

describe("rendering a choice into the dialogue panel", () => {
  test("options are numbered from one, the way the keys are labelled", () => {
    expect(dialogueChoicePrompt(options("Ask about the road.", "Say nothing."))).toBe(
      "1. Ask about the road.\n2. Say nothing.",
    );
  });

  test("a single option still reads as a choice rather than a line", () => {
    expect(dialogueChoicePrompt(options("Go on."))).toBe("1. Go on.");
  });

  test("it stops at the last option a number key can reach", () => {
    const many = options(...Array.from({ length: 12 }, (_, index) => `Option ${index}`));
    const rendered = dialogueChoicePrompt(many);
    expect(rendered.split("\n")).toHaveLength(MAX_DIALOGUE_CHOICES);
    expect(rendered).not.toContain("Option 8");
  });
});

describe("selecting by number key", () => {
  test("the visible numbering is the index the reducer expects", () => {
    // The runtime hands over only the options whose flags hold, so what the
    // player counts on screen is what `choose` counts.
    const offered = options("First.", "Second.");
    expect(dialogueChoiceForKey(offered, 0)?.text).toBe("First.");
    expect(dialogueChoiceForKey(offered, 1)?.text).toBe("Second.");
  });

  test("a key past the offered options selects nothing", () => {
    const offered = options("Only one.");
    expect(dialogueChoiceForKey(offered, 1)).toBeNull();
    expect(dialogueChoiceForKey(offered, -1)).toBeNull();
  });

  test("a key past what the panel can show selects nothing, not a hidden option", () => {
    const many = options(...Array.from({ length: 12 }, (_, index) => `Option ${index}`));
    expect(dialogueChoiceForKey(many, MAX_DIALOGUE_CHOICES)).toBeNull();
  });
});
