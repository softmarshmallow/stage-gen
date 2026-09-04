// Where the conversation box's parts sit: this genre's numbers for the `ui`
// family's text plate.
//
// The arithmetic left. The frame is generated art whose corner ornament can
// curl into the interior, so nothing here is a screen coordinate: the producer
// publishes the ornament-free rectangle, the widget projects it to the screen,
// and `textPlateLayout` divides it. What stays is the only per-game tuning
// surface — how much of the safe width the portrait takes, how tall the name
// row is, and the gaps between — plus the padding, which this genre applies
// equally on every side and the room does not.

import type { Rect } from "@/lib/shell/hud-geometry";
import {
  textPlateLayout,
  type TextPlateLayout,
} from "@/lib/families/ui/text-plate";

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

export type DialogueBoxLayout = TextPlateLayout;

/** Divide the frame's safe rect into a portrait slot and a two-row text column. */
export function dialogueBoxLayout(
  safe: Rect,
  knobs: DialogueBoxKnobs = DEFAULT_DIALOGUE_BOX_KNOBS,
): DialogueBoxLayout {
  return textPlateLayout(safe, {
    portraitSlotWidth: knobs.portraitSlotWidth,
    columnGap: knobs.columnGap,
    nameRowHeight: knobs.nameRowHeight,
    rowGap: knobs.rowGap,
    paddingX: knobs.padding,
    paddingY: knobs.padding,
  });
}
