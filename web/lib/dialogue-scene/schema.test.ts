import { describe, expect, test } from "bun:test";
import rawFixture from "./demo-fixture.json";
import { dialogueSceneDemoFixture } from "./demo-fixture";
import {
  DIALOGUE_SCENE_THEME_FIXTURE_KIND,
  parseDialogueSceneThemeFixture,
  serializeDialogueSceneThemeFixture,
  validateDialogueSceneRuntimeFixture,
} from "./schema";

function mutableFixture(): Record<string, unknown> {
  return structuredClone(rawFixture) as unknown as Record<string, unknown>;
}

describe("dialogue-scene deterministic fixture schema", () => {
  test("parses and freezes the committed caller-authored fixture", () => {
    expect(dialogueSceneDemoFixture.schemaVersion).toBe(1);
    expect(dialogueSceneDemoFixture.mode).toBe("deterministic-demo");
    expect(dialogueSceneDemoFixture.authorship).toBe("caller-authored");
    expect(dialogueSceneDemoFixture.background.src).toBe(
      "/dialogue-scene/demo/anime/background.png",
    );
    expect(dialogueSceneDemoFixture.expressionVariants.map((variant) => variant.state)).toEqual([
      "neutral",
      "delighted",
      "flustered",
      "concerned",
    ]);
    expect(dialogueSceneDemoFixture.expressionVariants[0].src).toBe(
      "/dialogue-scene/demo/anime/heroine-neutral.png",
    );
    expect(dialogueSceneDemoFixture.appearance.conceptSrc).toBe(
      "/dialogue-scene/demo/anime/concept-key-art.png",
    );
    expect(dialogueSceneDemoFixture.appearance.age).toBe(23);
    expect(dialogueSceneDemoFixture.presentation.framingZoom).toBe(70);
    expect(dialogueSceneDemoFixture.presentation.sourceFramingZoom).toBe(70);
    expect(dialogueSceneDemoFixture.dialogue).toHaveLength(8);
    expect(Object.isFrozen(dialogueSceneDemoFixture)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.presentation)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.expressionVariants)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.expressionVariants[0])).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.dialogue)).toBeTrue();
    expect(Object.isFrozen(dialogueSceneDemoFixture.dialogue[0])).toBeTrue();
  });

  test("rejects unknown fields and paths outside the demo asset root", () => {
    const unknownField = mutableFixture();
    unknownField.unexpected = true;
    expect(() => parseDialogueSceneThemeFixture(unknownField)).toThrow(
      "unexpected unexpected",
    );

    const escapedPath = mutableFixture();
    (escapedPath.background as Record<string, unknown>).src = "../background.png";
    expect(() => parseDialogueSceneThemeFixture(escapedPath)).toThrow(
      "confined dialogue-scene demo, installed-theme, or run PNG path",
    );
  });

  test("accepts only content-addressed installed-theme asset paths", () => {
    const installed = mutableFixture();
    const digest = "a".repeat(64);
    (installed.background as Record<string, unknown>).src =
      `/dialogue-scene/themes/${digest}/assets/${"1".repeat(64)}.png`;
    (installed.appearance as Record<string, unknown>).concept_src =
      `/dialogue-scene/themes/${digest}/assets/${"2".repeat(64)}.png`;
    const variants = installed.expression_variants as Record<string, unknown>[];
    variants.forEach((variant, index) => {
      variant.src =
        `/dialogue-scene/themes/${digest}/assets/${String(index + 3).repeat(64)}.png`;
    });
    expect(parseDialogueSceneThemeFixture(installed).background.src).toContain(digest);

    variants[0].src = `/dialogue-scene/themes/latest/assets/${"3".repeat(64)}.png`;
    expect(() => parseDialogueSceneThemeFixture(installed)).toThrow(
      "confined dialogue-scene demo, installed-theme, or run PNG path",
    );
  });

  test("binds every installed asset path to one immutable bundle", () => {
    const installed = mutableFixture();
    const firstBundle = "a".repeat(64);
    const secondBundle = "b".repeat(64);
    const assetPath = (bundleId: string, marker: string) =>
      `/dialogue-scene/themes/${bundleId}/assets/${marker.repeat(64)}.png`;
    (installed.background as Record<string, unknown>).src = assetPath(
      firstBundle,
      "1",
    );
    (installed.appearance as Record<string, unknown>).concept_src = assetPath(
      firstBundle,
      "2",
    );
    const variants = installed.expression_variants as Record<string, unknown>[];
    variants.forEach((variant, index) => {
      variant.src = assetPath(firstBundle, String(index + 3));
    });
    expect(parseDialogueSceneThemeFixture(installed).background.src).toContain(
      firstBundle,
    );

    variants[0].src = assetPath(secondBundle, "3");
    expect(() => parseDialogueSceneThemeFixture(installed)).toThrow(
      "installed fixture assets must share one bundle id",
    );

    variants[0].src = rawFixture.expression_variants[0].src;
    expect(() => parseDialogueSceneThemeFixture(installed)).toThrow(
      "must all use the committed demo or one installed bundle",
    );
  });

  test("binds every expression variant to one adult appearance identity", () => {
    const mismatch = mutableFixture();
    const variants = mismatch.expression_variants as Record<string, unknown>[];
    variants[0].appearance_id = "another-appearance";
    expect(() => parseDialogueSceneThemeFixture(mismatch)).toThrow(
      "expression variant must reference appearance.id",
    );

    const minor = mutableFixture();
    (minor.appearance as Record<string, unknown>).age = 17;
    expect(() => parseDialogueSceneThemeFixture(minor)).toThrow(
      "appearance.age must be an integer from 18 to 120",
    );

    const profileMismatch = mutableFixture();
    (profileMismatch.profile_identity as Record<string, unknown>).profile_id =
      "another-appearance";
    expect(() => parseDialogueSceneThemeFixture(profileMismatch)).toThrow(
      "profile identity must reference appearance.id",
    );

    const duplicatedId = mutableFixture();
    const duplicateVariants = duplicatedId.expression_variants as Record<
      string,
      unknown
    >[];
    duplicateVariants[1].id = duplicateVariants[0].id;
    expect(() => parseDialogueSceneThemeFixture(duplicatedId)).toThrow(
      "expression variant id is duplicated",
    );
  });

  test("requires one of each expression state and binds every beat to the vocabulary", () => {
    const duplicatedState = mutableFixture();
    const variants = duplicatedState.expression_variants as Record<string, unknown>[];
    variants[1].state = "neutral";
    expect(() => parseDialogueSceneThemeFixture(duplicatedState)).toThrow(
      "expression state is duplicated: neutral",
    );

    const unknownBeatState = mutableFixture();
    const dialogue = unknownBeatState.dialogue as Record<string, unknown>[];
    dialogue[0].expression_state = "surprised";
    expect(() => parseDialogueSceneThemeFixture(unknownBeatState)).toThrow(
      "must be one of neutral, delighted, flustered, concerned",
    );
  });

  test("requires a finite public framing value from 0 through 100", () => {
    for (const invalid of [Number.NaN, Number.POSITIVE_INFINITY, -0.1, 100.1, "70"]) {
      const fixture = mutableFixture();
      (fixture.presentation as Record<string, unknown>).framing_zoom = invalid;
      expect(() => parseDialogueSceneThemeFixture(fixture)).toThrow(
        "presentation.framingZoom must be a finite number from 0 to 100",
      );
    }

    const invalidBaseline = mutableFixture();
    (invalidBaseline.presentation as Record<string, unknown>).source_framing_zoom = 101;
    expect(() => parseDialogueSceneThemeFixture(invalidBaseline)).toThrow(
      "presentation.sourceFramingZoom must be a finite number from 0 to 100",
    );
  });

  test("accepts only safe profile identity facts in the persisted fixture", () => {
    const fixture = mutableFixture();
    expect(parseDialogueSceneThemeFixture(fixture).profileIdentity).toEqual({
      profileId: "mio-amamiya",
      revision: 4,
    });

    (fixture.profile_identity as Record<string, unknown>).source_path =
      "/private/profile.toml";
    expect(() => parseDialogueSceneThemeFixture(fixture)).toThrow(
      "profile_identity keys must match the schema",
    );
  });

  test("round-trips the exact current persisted theme fixture at the UI boundary", () => {
    const fixture = parseDialogueSceneThemeFixture(mutableFixture());
    const persisted = serializeDialogueSceneThemeFixture(fixture);

    expect(persisted.schema_version).toBe(1);
    expect(persisted.kind).toBe(DIALOGUE_SCENE_THEME_FIXTURE_KIND);
    expect(persisted.profile_identity).toEqual({
      profile_id: "mio-amamiya",
      revision: 4,
    });
    expect("schemaVersion" in persisted).toBeFalse();
    expect("profileIdentity" in persisted).toBeFalse();
    expect(persisted as unknown).toEqual(rawFixture);
    expect(parseDialogueSceneThemeFixture(persisted)).toEqual(fixture);
  });

  test("rejects aliases, unknown fields, and prior persisted theme fixtures", () => {
    const current = mutableFixture();

    const camel = structuredClone(current);
    camel.profileIdentity = camel.profile_identity;
    delete camel.profile_identity;
    expect(() => parseDialogueSceneThemeFixture(camel)).toThrow(
      "dialogue-scene theme fixture keys must match the schema",
    );

    const unknown = structuredClone(current);
    unknown.legacy = true;
    expect(() => parseDialogueSceneThemeFixture(unknown)).toThrow(
      "dialogue-scene theme fixture keys must match the schema",
    );

    const prior = structuredClone(current);
    prior.schema_version = 0;
    prior.kind = "dialogue-scene-theme-fixture-v0";
    expect(() => parseDialogueSceneThemeFixture(prior)).toThrow(
      "dialogue-scene theme fixture schema_version must be 1",
    );
  });
});

describe("run-played fixtures", () => {
  const runSrc = (name: string) => `/api/assets/larkfield/assets/${name}.png`;

  function runFixture(): Record<string, unknown> {
    const base = structuredClone(dialogueSceneDemoFixture) as unknown as Record<
      string,
      unknown
    >;
    const appearance = base.appearance as Record<string, unknown>;
    return {
      ...base,
      background: { ...(base.background as object), src: runSrc("background") },
      appearance: { ...appearance, conceptSrc: runSrc("concept") },
      expressionVariants: (
        base.expressionVariants as { state: string }[]
      ).map((variant) => ({ ...variant, src: runSrc(`expression-${variant.state}`) })),
    };
  }

  test("accepts a fixture streamed from one run", () => {
    const fixture = validateDialogueSceneRuntimeFixture(runFixture());
    expect(fixture.background.src).toBe(runSrc("background"));
  });

  test("refuses a fixture assembled from two runs", () => {
    const mixed = runFixture();
    mixed.background = {
      ...(mixed.background as object),
      src: "/api/assets/other-run/assets/background.png",
    };
    expect(() => validateDialogueSceneRuntimeFixture(mixed)).toThrow(
      "must share one run tag",
    );
  });

  test("refuses a fixture that mixes a run with the committed demo", () => {
    const mixed = runFixture();
    mixed.background = {
      ...(mixed.background as object),
      src: (dialogueSceneDemoFixture.background as { src: string }).src,
    };
    expect(() => validateDialogueSceneRuntimeFixture(mixed)).toThrow(
      "one installed bundle, or one run",
    );
  });
});
