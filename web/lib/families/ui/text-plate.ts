// The `ui` family's `text-plate` port: words inside a generated frame.
//
// The composition table names three "speaker + body + portrait in a rect"
// layouts and asks for a port. Two of the three are the same function with
// different numbers in it:
//
//   - the platformer's conversation box — a portrait slot on the left, a
//     speaker-name row above the line, everything measured off the frame's
//     published ornament-free rectangle;
//   - the room's narration plate — no portrait, no speaker, and asymmetric
//     padding, which is the *whole* of the difference.
//
// So the plate below has both, and the room is the instantiation with the
// portrait slot and the name row set to zero. That is not a degenerate case
// dressed up as a family: a plate with no portrait is a plate, and the arithmetic
// that puts the text where it goes is the same arithmetic either way.
//
// Nothing here is a screen coordinate. The frame is generated art whose corner
// ornament can curl into the interior, so the producer publishes the
// ornament-free rectangle, the widget projects it, and this divides it.

import type { Rect } from "@/lib/shell/hud-geometry";

export type TextPlateKnobs = Readonly<{
  /** Width reserved on the left for a portrait, or zero for a plate with none. */
  portraitSlotWidth: number;
  /** Space between the portrait slot and the text column. Meaningless at zero width. */
  columnGap: number;
  /** Height of a speaker-name row above the body, or zero for a plate with none. */
  nameRowHeight: number;
  /** Space between the name row and the body. Meaningless at zero height. */
  rowGap: number;
  /** Inner padding inside the safe rect, left and right. */
  paddingX: number;
  /** Inner padding inside the safe rect, top and bottom. */
  paddingY: number;
}>;

export type TextPlateLayout = Readonly<{
  /** Portrait anchor: horizontal centre of its slot, and the slot's bottom edge (origin 0.5, 1). */
  portrait: Readonly<{ centerX: number; bottomY: number; height: number }>;
  /** Top-left of the speaker name. */
  name: Readonly<{ x: number; y: number }>;
  /** Top-left of the body text and the width it wraps at. */
  text: Readonly<{ x: number; y: number; wrapWidth: number }>;
}>;

/**
 * Divide a frame's safe rect into a portrait slot and a text column.
 *
 * A caller that draws no portrait and no speaker still gets both back and
 * ignores them, rather than the port growing two nullable halves that every
 * consumer then has to test. What it does not get is a plate that does not fit:
 * a safe rect too small for the slots it was asked for is refused rather than
 * laid out into negative widths.
 */
export function textPlateLayout(safe: Rect, knobs: TextPlateKnobs): TextPlateLayout {
  const inner = {
    x: safe.x + knobs.paddingX,
    y: safe.y + knobs.paddingY,
    width: safe.width - 2 * knobs.paddingX,
    height: safe.height - 2 * knobs.paddingY,
  };
  if (
    inner.width <= knobs.portraitSlotWidth + knobs.columnGap ||
    inner.height <= knobs.nameRowHeight
  ) {
    throw new Error("text plate safe rect is too small for its layout");
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
      wrapWidth: Math.max(1, inner.width - knobs.portraitSlotWidth - knobs.columnGap),
    }),
  });
}
