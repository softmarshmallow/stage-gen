/**
 * Static browser fonts used by the optional demo's combat feedback.
 *
 * Two faces, because they are set for two different things. Fredoka is a text face and carries
 * the EXP stat log, which is running words. Damage numbers are numerals inside a heavy double
 * outline, and how thick that outline may be is a property of the typeface: a stroke eats a
 * glyph's counters from both sides, and Fredoka's close up long before the edge reads as arcade
 * weight. Luckiest Guy is drawn with open counters and thick strokes, so it carries one.
 */
export const COMBAT_TEXT_FONT_FAMILY = "Stage Gen Fredoka";
export const COMBAT_TEXT_FONT_URL = "/fonts/fredoka/fredoka-variable.ttf";
/** Weight range the variable Fredoka file carries, and the weight damage feedback asks it for. */
export const COMBAT_TEXT_FONT_WEIGHT = "300 700";
export const COMBAT_TEXT_FONT_LOADED_WEIGHT = 700;

export const DAMAGE_NUMBER_FONT_FAMILY = "Stage Gen Luckiest Guy";
export const DAMAGE_NUMBER_FONT_URL = "/fonts/luckiest-guy/LuckiestGuy-Regular.ttf";
/**
 * A single-weight display face, asked for at exactly the weight it has.
 *
 * Asking a canvas for bold from a face with no bold gets a synthesized one, and the browser
 * decides how much to thicken it. That is a glyph metric decided outside the repository, which is
 * the one thing the committed-font rule exists to prevent.
 */
export const DAMAGE_NUMBER_FONT_WEIGHT = "400";
export const DAMAGE_NUMBER_FONT_LOADED_WEIGHT = 400;

export type CombatFontLoadResult = "loaded" | "unsupported";

type FontFaceLike = Readonly<{
  load: () => Promise<FontFace>;
}>;

type CombatFontEnvironment = Readonly<{
  createFace: () => FontFaceLike;
  addFace: (face: FontFace) => void;
  check: () => boolean;
  awaitUsable: () => Promise<unknown>;
}>;

let browserLoad: Promise<CombatFontLoadResult> | undefined;

type CombatFontFace = Readonly<{
  family: string;
  url: string;
  /** The `font-face` descriptor: a range for the variable file, one number for the static one. */
  weight: string;
  /** The weight the demo actually sets, which is the one readiness is proved at. */
  loadedWeight: number;
}>;

/** Every face the combat feedback commits to, in the order they are loaded. */
export const COMBAT_FONT_FACES: readonly CombatFontFace[] = Object.freeze([
  Object.freeze({
    family: COMBAT_TEXT_FONT_FAMILY,
    url: COMBAT_TEXT_FONT_URL,
    weight: COMBAT_TEXT_FONT_WEIGHT,
    loadedWeight: COMBAT_TEXT_FONT_LOADED_WEIGHT,
  }),
  Object.freeze({
    family: DAMAGE_NUMBER_FONT_FAMILY,
    url: DAMAGE_NUMBER_FONT_URL,
    weight: DAMAGE_NUMBER_FONT_WEIGHT,
    loadedWeight: DAMAGE_NUMBER_FONT_LOADED_WEIGHT,
  }),
]);

function browserEnvironment(face: CombatFontFace): CombatFontEnvironment | null {
  if (
    typeof FontFace === "undefined" ||
    typeof document === "undefined" ||
    !document.fonts
  ) {
    return null;
  }
  const shorthand = `${face.loadedWeight} 30px ${JSON.stringify(face.family)}`;
  return {
    createFace: () =>
      new FontFace(
        face.family,
        `url(${JSON.stringify(face.url)}) format("truetype")`,
        { style: "normal", weight: face.weight },
      ),
    addFace: (loaded) => document.fonts.add(loaded),
    check: () => document.fonts.check(shorthand, "0123456789"),
    awaitUsable: () => document.fonts.load(shorthand, "0123456789"),
  };
}

/**
 * Load and prove the committed combat-number font before Phaser creates text.
 *
 * A missing browser font API is a supported non-rendering environment (SSR and pure unit tests).
 * In a real browser, a rejected or unusable font fails the scene boot rather than silently changing
 * glyph metrics underneath deterministic screenshots.
 */
export async function loadCombatTextFont(
  environment: CombatFontEnvironment | null,
): Promise<CombatFontLoadResult> {
  if (environment === null) return "unsupported";
  const face = await environment.createFace().load();
  environment.addFace(face);
  await environment.awaitUsable();
  if (!environment.check()) {
    throw new Error("combat text font loaded but is not usable for numeric glyphs");
  }
  return "loaded";
}

/**
 * One shared in-flight load per browser document, covering every committed face.
 *
 * Awaited before the game boots rather than left to the browser's own on-demand loading: a Phaser
 * text object rasterises at construction time, so a number drawn before its face is usable is
 * drawn in a fallback and stays that way for its whole life.
 */
export function loadBrowserCombatTextFont(): Promise<CombatFontLoadResult> {
  browserLoad ??= (async () => {
    let result: CombatFontLoadResult = "unsupported";
    for (const face of COMBAT_FONT_FACES) {
      result = await loadCombatTextFont(browserEnvironment(face));
    }
    return result;
  })();
  return browserLoad;
}
