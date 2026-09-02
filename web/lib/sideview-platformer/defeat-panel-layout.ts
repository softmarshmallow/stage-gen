// Where the defeat panel's title and button sit, derived from the frame's measured safe rect.
//
// Same discipline as the dialogue box: the producer publishes the ornament-free interior, the
// widget projects it, and this function divides it. The button's size is what the safe rect
// allows, never a fixed number the art may not fit.

import type { Rect, Size } from "@/lib/shell/hud-geometry";

export type DefeatPanelKnobs = Readonly<{
  /** Height of the title row at the top of the safe rect, in screen px. */
  titleRowHeight: number;
  /** Space between the title row and the button, in screen px. */
  rowGap: number;
  /** The button's preferred size; clamped to the safe rect and to the sheet's smallest size. */
  button: Size;
  /** Inner padding inside the safe rect on every side, in screen px. */
  padding: number;
}>;

export const DEFAULT_DEFEAT_PANEL_KNOBS: DefeatPanelKnobs = Object.freeze({
  titleRowHeight: 44,
  rowGap: 18,
  button: Object.freeze({ width: 380, height: 62 }),
  padding: 6,
});

export type DefeatPanelLayout = Readonly<{
  /** Centre of the title row. */
  title: Readonly<{ x: number; y: number }>;
  /** Centre and size of the button. */
  button: Readonly<{ x: number; y: number; width: number; height: number }>;
}>;

/** Divide the safe rect into a title row and a centred button below it. */
export function defeatPanelLayout(
  safe: Rect,
  buttonMinimum: Size,
  knobs: DefeatPanelKnobs = DEFAULT_DEFEAT_PANEL_KNOBS,
): DefeatPanelLayout {
  const inner = {
    x: safe.x + knobs.padding,
    y: safe.y + knobs.padding,
    width: safe.width - 2 * knobs.padding,
    height: safe.height - 2 * knobs.padding,
  };
  const buttonTop = inner.y + knobs.titleRowHeight + knobs.rowGap;
  const room = { width: inner.width, height: inner.y + inner.height - buttonTop };
  const width = Math.min(Math.max(knobs.button.width, buttonMinimum.width), room.width);
  const height = Math.min(Math.max(knobs.button.height, buttonMinimum.height), room.height);
  if (width < buttonMinimum.width || height < buttonMinimum.height) {
    throw new Error("defeat panel safe rect cannot host the button at its smallest size");
  }
  return Object.freeze({
    title: Object.freeze({ x: inner.x + inner.width / 2, y: inner.y + knobs.titleRowHeight / 2 }),
    button: Object.freeze({
      x: inner.x + inner.width / 2,
      y: buttonTop + room.height / 2,
      width,
      height,
    }),
  });
}
