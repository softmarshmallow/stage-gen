// Where the conversation box's parts sit, derived from the frame's measured safe rect.
//
// The frame is generated art whose corner ornament can curl into the interior, so nothing here
// is a screen coordinate: the producer publishes the ornament-free rectangle, the widget projects
// it to the screen, and this function divides it. The knobs are the only per-game tuning surface:
// how much of the safe width the portrait takes, how tall the name row is, and the gaps between.

import type { Rect } from "@/lib/shell/hud-geometry";

export type DialogueBoxKnobs = Readonly<{
  /** Width reserved on the left for the speaker's portrait, in screen px. */
  portraitSlotWidth: number;
  /** Space between the portrait slot and the text column, in screen px. */
  columnGap: number;
  /** Height of the speaker-name row above the line text, in screen px. */
  nameRowHeight: number;
  /** Space between the name row and the line text, in screen px. */
  rowGap: number;
  /** Inner padding inside the safe rect on every side, in screen px. */
  padding: number;
}>;

export const DEFAULT_DIALOGUE_BOX_KNOBS: DialogueBoxKnobs = Object.freeze({
  portraitSlotWidth: 210,
  columnGap: 24,
  nameRowHeight: 34,
  rowGap: 10,
  padding: 8,
});

export type DialogueBoxLayout = Readonly<{
  /** Portrait anchor: horizontal centre of its slot, and the slot's bottom edge (origin 0.5, 1). */
  portrait: Readonly<{ centerX: number; bottomY: number; height: number }>;
  /** Top-left of the speaker name. */
  name: Readonly<{ x: number; y: number }>;
  /** Top-left of the line text and the width it wraps at. */
  text: Readonly<{ x: number; y: number; wrapWidth: number }>;
}>;

/** Divide the frame's safe rect into a portrait slot and a two-row text column. */
export function dialogueBoxLayout(
  safe: Rect,
  knobs: DialogueBoxKnobs = DEFAULT_DIALOGUE_BOX_KNOBS,
): DialogueBoxLayout {
  const inner = {
    x: safe.x + knobs.padding,
    y: safe.y + knobs.padding,
    width: safe.width - 2 * knobs.padding,
    height: safe.height - 2 * knobs.padding,
  };
  if (inner.width <= knobs.portraitSlotWidth + knobs.columnGap || inner.height <= knobs.nameRowHeight) {
    throw new Error("dialogue box safe rect is too small for its layout");
  }
  const textX = inner.x + knobs.portraitSlotWidth + knobs.columnGap;
  return Object.freeze({
    portrait: Object.freeze({
      centerX: inner.x + knobs.portraitSlotWidth / 2,
      bottomY: inner.y + inner.height,
      height: inner.height,
    }),
    name: Object.freeze({ x: textX, y: inner.y }),
    text: Object.freeze({
      x: textX,
      y: inner.y + knobs.nameRowHeight + knobs.rowGap,
      wrapWidth: inner.x + inner.width - textX,
    }),
  });
}
