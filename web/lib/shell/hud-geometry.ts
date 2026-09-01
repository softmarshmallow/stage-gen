// Geometry primitives shared by the in-canvas HUDs, kept free of Phaser.
//
// Every genre HUD lays itself out in one fixed design space as pure,
// unit-tested functions, and they all need the same two ideas: an axis-aligned
// rectangle, and "the largest shape of this aspect that fits there". Only that
// genuinely common geometry lives here — where a panel sits, what a press
// means, how a band stacks are genre decisions and stay with each HUD.

export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface Size {
  readonly width: number;
  readonly height: number;
}

/**
 * The largest size of `source`'s aspect that fits inside `bounds`.
 *
 * Aspect-fit rather than stretch, because a sprite drawn into a container of a
 * different shape stops looking like its artwork: a portrait plate stays
 * portrait and is limited by whichever bound it reaches first.
 */
export function containSize(source: Size, bounds: Size): Size {
  const scale = Math.min(bounds.width / source.width, bounds.height / source.height);
  return { width: source.width * scale, height: source.height * scale };
}

/**
 * The largest rectangle of `source`'s aspect that fits inside `outer`, centred.
 *
 * A degenerate source keeps the whole container rather than collapsing to
 * nothing, so an unreadable sprite still occupies its authored region.
 */
export function containRect(outer: Rect, source: Size): Rect {
  if (source.width <= 0 || source.height <= 0) return outer;
  const fitted = containSize(source, outer);
  return {
    x: outer.x + (outer.width - fitted.width) / 2,
    y: outer.y + (outer.height - fitted.height) / 2,
    width: fitted.width,
    height: fitted.height,
  };
}
