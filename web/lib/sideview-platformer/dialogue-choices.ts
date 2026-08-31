/**
 * How a scenario choice reads inside the platformer's one-line dialogue panel.
 *
 * The visual novel can afford a button per option; this panel is a fixed strip
 * under a portrait, so the options are numbered text and the player presses a
 * number. Keeping the formatting here rather than inside the Phaser scene is the
 * same rule `scene-hud.ts` follows: the scene draws, and what it draws is a pure
 * function somebody can test.
 */

import type { ScenarioChoiceOption } from "@/lib/scenario/program";

/** Options beyond this cannot be reached by the number keys the scene binds. */
export const MAX_DIALOGUE_CHOICES = 8;

/**
 * Render the offered options as numbered lines.
 *
 * Only the options the runtime offered arrive here - it has already dropped the
 * ones whose flags do not hold - so the numbering a player sees always matches
 * the index the reducer expects.
 */
export function dialogueChoicePrompt(options: readonly ScenarioChoiceOption[]): string {
  return options
    .slice(0, MAX_DIALOGUE_CHOICES)
    .map((option, index) => `${index + 1}. ${option.text}`)
    .join("\n");
}

/**
 * The option a number key selects, or null when it selects nothing offered.
 *
 * Bounds-checked against the offered list rather than the authored one: a key
 * for an option the flags hid must do nothing, not select its neighbour.
 */
export function dialogueChoiceForKey(
  options: readonly ScenarioChoiceOption[],
  index: number,
): ScenarioChoiceOption | null {
  if (index < 0 || index >= Math.min(options.length, MAX_DIALOGUE_CHOICES)) return null;
  return options[index] ?? null;
}
