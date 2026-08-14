import type { TransparencyMode } from "../../../../src/config.ts";

/**
 * The only mode-specific background instructions used by image prompts in
 * this recipe. Prompt bodies refer to the removable area as BACKGROUND FIELD.
 */
export const TRANSPARENCY_PROMPT_FRAGMENTS: Readonly<
  Record<TransparencyMode, string>
> = {
  ai:
    "TRANSPARENCY BACKGROUND CONTRACT: Fill every BACKGROUND FIELD with one neutral grey, naturally isolated from the foreground subject. Keep it even, flat, and untextured with strong edge separation. Render an opaque image: no transparency, no alpha preview, and no checkerboard. Use only that neutral grey in the background field; do not introduce saturated key colours. Do not place cast shadows, glow, or foreground detail in the BACKGROUND FIELD.",
  chroma:
    "TRANSPARENCY BACKGROUND CONTRACT: Fill every BACKGROUND FIELD with solid exact #FF00FF (RGB 255,0,255). Use no gradients, texture, shadows, glow, antialias haze, or alternate pinks in the BACKGROUND FIELD. Never use #FF00FF anywhere on the foreground subject. Render an opaque image: no transparency, no alpha preview, and no checkerboard.",
};

export function transparencyPromptFragment(mode: TransparencyMode): string {
  return TRANSPARENCY_PROMPT_FRAGMENTS[mode];
}
