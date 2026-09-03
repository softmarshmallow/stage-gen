// Which text colour is readable on a drawn panel.
//
// A HUD's text colour cannot be a constant once the panel behind it is generated art. The
// dialogue panel and the room's narration plate were both authored against a dark fallback
// fill, so their body text is near-white; the moment a package ships a cream plate the body
// text disappears while the speaker name, which happened to be ink, survives. That is a
// legibility bug the producer cannot fix from its side, because the same sheet is legitimate
// art for a dark game and a light one.
//
// So the consumer measures instead of assuming: sample the panel where the words actually go
// and pick the candidate with the better contrast against it. The maths is WCAG 2.1 relative
// luminance, which is the standard the accessibility guidance is written in, and is worth
// preferring over a naive channel average because it weights green the way an eye does.

/** One 8-bit sRGB colour. */
export interface Rgb {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.1 relative luminance, 0 for black and 1 for white. */
export function relativeLuminance({ r, g, b }: Rgb): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG 2.1 contrast ratio, 1 for identical colours and 21 for black on white. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** `#rgb` or `#rrggbb` to channels, or null when the string is not a hex colour. */
export function parseHexColor(value: string): Rgb | null {
  const hex = value.trim().replace(/^#/, "");
  if (hex.length === 3) {
    const [r, g, b] = [...hex].map((d) => Number.parseInt(d + d, 16));
    return Number.isNaN(r) || Number.isNaN(g) || Number.isNaN(b) ? null : { r, g, b };
  }
  if (hex.length !== 6) return null;
  const n = Number.parseInt(hex, 16);
  if (Number.isNaN(n)) return null;
  return { r: (n >> 16) & 0xff, g: (n >> 8) & 0xff, b: n & 0xff };
}

/**
 * The candidate with the best contrast against `background`.
 *
 * Candidates are given in preference order, and a candidate that already clears
 * `minimumRatio` wins before a later one is considered: the point is to keep the authored
 * look wherever it is legible, and only reach for the other end of the range when it is not.
 * WCAG's threshold for body text is 4.5:1, which is the default.
 */
export function mostReadable(
  background: Rgb,
  candidates: readonly string[],
  minimumRatio = 4.5,
): string | null {
  let best: { color: string; ratio: number } | null = null;
  for (const candidate of candidates) {
    const rgb = parseHexColor(candidate);
    if (rgb === null) continue;
    const ratio = contrastRatio(background, rgb);
    if (ratio >= minimumRatio) return candidate;
    if (best === null || ratio > best.ratio) best = { color: candidate, ratio };
  }
  return best?.color ?? null;
}
