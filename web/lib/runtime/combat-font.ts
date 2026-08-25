/** Static browser font used by the optional demo's floating combat text. */
export const COMBAT_TEXT_FONT_FAMILY = "Stage Gen Fredoka";
export const COMBAT_TEXT_FONT_URL = "/fonts/fredoka/fredoka-variable.ttf";

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

function browserEnvironment(): CombatFontEnvironment | null {
  if (
    typeof FontFace === "undefined" ||
    typeof document === "undefined" ||
    !document.fonts
  ) {
    return null;
  }
  return {
    createFace: () =>
      new FontFace(
        COMBAT_TEXT_FONT_FAMILY,
        `url(${JSON.stringify(COMBAT_TEXT_FONT_URL)}) format("truetype")`,
        { style: "normal", weight: "300 700" },
      ),
    addFace: (face) => document.fonts.add(face),
    check: () =>
      document.fonts.check(`700 30px ${JSON.stringify(COMBAT_TEXT_FONT_FAMILY)}`, "0123456789"),
    awaitUsable: () =>
      document.fonts.load(
        `700 30px ${JSON.stringify(COMBAT_TEXT_FONT_FAMILY)}`,
        "0123456789",
      ),
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
  environment: CombatFontEnvironment | null = browserEnvironment(),
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

/** One shared in-flight load per browser document. */
export function loadBrowserCombatTextFont(): Promise<CombatFontLoadResult> {
  browserLoad ??= loadCombatTextFont();
  return browserLoad;
}
