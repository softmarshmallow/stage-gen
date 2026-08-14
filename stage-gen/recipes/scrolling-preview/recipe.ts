import { tagFor } from "../../src/tag.ts";
import type { Recipe } from "../../src/types.ts";
import { STAGES } from "./src/stages.ts";

/** Recipe-local input. It does not leak into generic orchestration. */
export interface ScrollingPreviewInput extends Record<string, unknown> {
  prompt: string;
}

export const scrollingPreviewRecipe: Recipe<ScrollingPreviewInput> = {
  id: "scrolling-preview",
  description: "Reference 2D scrolling preview asset pipeline",
  requiredCapabilities: ["structured-generation", "image-generation"],
  parseInput(value: unknown): ScrollingPreviewInput {
    if (typeof value === "string") {
      const prompt = value.trim();
      if (prompt) return { prompt };
    }
    if (value && typeof value === "object" && "prompt" in value) {
      const prompt = String((value as { prompt?: unknown }).prompt ?? "").trim();
      if (prompt) return { prompt };
    }
    throw new Error("scrolling-preview input requires a non-empty prompt");
  },
  tagFor(input) {
    return tagFor(input.prompt);
  },
  stages: STAGES,
};
