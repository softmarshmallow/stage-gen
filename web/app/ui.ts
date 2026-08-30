// The shell's shared class strings, per DESIGN.md.
//
// A constant here earns its place by being used from more than one file.
// Anything worn once is written on the element that wears it. These are
// values, not a cascade: nothing here overrides anything else, and an
// unused one is a dead export the type checker and bundler can both see.

/** Join class names, dropping the falsy ones. */
export function cx(
  ...parts: readonly (string | false | null | undefined)[]
): string {
  return parts.filter(Boolean).join(" ");
}

/** Centred column with a comfortable maximum width. */
export const page = "mx-auto max-w-[1100px] p-4 max-[480px]:p-3";

/** The one type size above body copy. */
export const h1 = "mb-4 text-[18px] font-semibold";

/** Dim metadata line: tag, status, package digest. */
export const metaLine = "mb-2 text-xs text-dim";

/** Prompt echo and the Play CTA share the top of a page. */
export const headerStrip =
  "mb-3 flex flex-wrap items-start justify-between gap-4";

/** A `─ label ───` divider. No size change, per the visual language. */
export const sectionHeading =
  "mt-4 mb-1.5 flex items-center gap-2 text-dim before:content-['─'] " +
  "after:flex-1 after:overflow-hidden after:tracking-[-2px] after:text-border " +
  "after:content-['─']";

/** `[ label ]` bracket-button. Inactive = dim border, dim text, no fill. */
export const button =
  "inline-block cursor-pointer border border-fg px-3.5 py-1.5 text-fg " +
  "enabled:hover:bg-hover " +
  "disabled:cursor-not-allowed disabled:border-dim disabled:text-dim";

/** The Play CTA before the world has finished cooking. */
export const playIdle =
  "pointer-events-none inline-block border border-dim text-dim no-underline";

/** The one place the accent fills. Activation should feel like an event. */
export const playActive =
  "inline-block border border-accent bg-accent font-semibold text-bg " +
  "no-underline hover:brightness-110";

/** Play CTA sizes: the loud one, and the one that rides in a list row. */
export const playSize = "px-[18px] py-1.5";
export const playSizeCompact = "px-2.5 py-1 text-xs";

/** A compact secondary link beside a compact Play CTA. */
export const linkGhost =
  "border border-border px-2.5 py-1 text-xs text-dim no-underline " +
  "hover:border-fg hover:text-fg";

/** Short preset label, inline-flow, terminal feel. */
export const chip =
  "cursor-pointer border border-border px-2.5 py-1 tracking-[0.02em] " +
  "text-dim hover:border-fg hover:text-fg active:border-accent " +
  "active:text-accent";

/** Bare 1px-bordered text field; the caret is the foreground colour. */
export const input =
  "w-full border border-dim bg-bg px-3 py-2 text-fg caret-fg outline-none " +
  "focus:border-fg";

/** Same, with room to grow downward. */
export const textarea = `${input} min-h-24 resize-y`;

/** One square box per expected artifact. Pair with exactly one state below. */
export const slot =
  "relative flex w-full cursor-pointer flex-col border bg-bg p-0 text-left " +
  "disabled:cursor-not-allowed";
export const slotIdle = "border-border hover:border-fg";
export const slotPresent = "border-accent";
export const slotFailed = "border-error text-error";

/** The square the artwork is drawn inside. Pair with a ground: `bg-well`
 * for opaque artwork, `alpha-checker` when the alpha is the point. */
export const slotInner =
  "relative flex aspect-square w-full items-center justify-center " +
  "overflow-hidden";

/** Artwork is pixel art: never smooth it. */
export const slotImage =
  "max-h-full max-w-full object-contain [image-rendering:pixelated]";

/** One line of label under a slot. */
export const slotLabel = "truncate px-1.5 py-1 text-xs text-dim";

/** Thumbnail grid; slots wrap down to 80px on a phone. */
export const assetGrid =
  "grid grid-cols-[repeat(auto-fill,minmax(110px,1fr))] gap-1.5 " +
  "max-[480px]:grid-cols-[repeat(auto-fill,minmax(80px,1fr))]";

/** Soundtrack cards need room for native transport controls. */
export const audioGrid =
  "grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-1.5";

/** The portable path under a card, elided rather than wrapped. */
export const assetPath = "truncate text-[11px] text-dim";

/** Used sparingly, per the visual language. */
export const errorBanner =
  "my-2 border border-error bg-error/5 px-3 py-2 text-error";
