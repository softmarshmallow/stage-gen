export const DIALOGUE_SCENE_DEMO_SCHEMA_VERSION = 1 as const;
export const DIALOGUE_SCENE_DEMO_MODE = "deterministic-demo" as const;
export const DIALOGUE_SCENE_DEMO_AUTHORSHIP = "caller-authored" as const;
export const DIALOGUE_SCENE_THEME_FIXTURE_SCHEMA_VERSION = 1 as const;
export const DIALOGUE_SCENE_THEME_FIXTURE_KIND =
  "dialogue-scene-theme-fixture-v1" as const;
export const DIALOGUE_SCENE_EXPRESSION_STATES = Object.freeze([
  "neutral",
  "delighted",
  "flustered",
  "concerned",
] as const);

export type DialogueSceneExpressionState =
  (typeof DIALOGUE_SCENE_EXPRESSION_STATES)[number];

export interface DialogueSceneDemoAsset {
  readonly id: string;
  readonly src: string;
  readonly alt: string;
}

export interface DialogueSceneDemoAppearance {
  readonly id: string;
  readonly label: string;
  readonly age: number;
  readonly role: string;
  readonly tagline: string;
  readonly description: string;
  readonly visualIdentity: string;
  readonly artDirection: string;
  readonly conceptSrc: string;
}

export interface DialogueSceneDemoExpressionVariant extends DialogueSceneDemoAsset {
  readonly appearanceId: string;
  readonly state: DialogueSceneExpressionState;
  readonly label: string;
  readonly description: string;
  readonly slot: "right";
}

export interface DialogueSceneDemoBeat {
  readonly id: string;
  readonly speaker: string;
  readonly text: string;
  readonly expressionState: DialogueSceneExpressionState;
}

export interface DialogueSceneDemoPresentation {
  readonly framingZoom: number;
  readonly sourceFramingZoom: number;
}

export interface DialogueSceneDemoFixture {
  readonly schemaVersion: typeof DIALOGUE_SCENE_DEMO_SCHEMA_VERSION;
  readonly fixtureId: string;
  readonly mode: typeof DIALOGUE_SCENE_DEMO_MODE;
  readonly authorship: typeof DIALOGUE_SCENE_DEMO_AUTHORSHIP;
  readonly title: string;
  readonly sceneLabel: string;
  readonly presentation: DialogueSceneDemoPresentation;
  readonly background: DialogueSceneDemoAsset;
  readonly appearance: DialogueSceneDemoAppearance;
  readonly expressionVariants: readonly DialogueSceneDemoExpressionVariant[];
  readonly dialogue: readonly DialogueSceneDemoBeat[];
  readonly profileIdentity: {
    readonly profileId: string;
    readonly revision: number;
  };
}

export interface DialogueSceneThemeFixtureV1 {
  readonly schema_version: typeof DIALOGUE_SCENE_THEME_FIXTURE_SCHEMA_VERSION;
  readonly kind: typeof DIALOGUE_SCENE_THEME_FIXTURE_KIND;
  readonly fixture_id: string;
  readonly mode: typeof DIALOGUE_SCENE_DEMO_MODE;
  readonly authorship: typeof DIALOGUE_SCENE_DEMO_AUTHORSHIP;
  readonly title: string;
  readonly scene_label: string;
  readonly profile_identity: {
    readonly profile_id: string;
    readonly revision: number;
  };
  readonly presentation: {
    readonly framing_zoom: number;
    readonly source_framing_zoom: number;
  };
  readonly background: DialogueSceneDemoAsset;
  readonly appearance: Readonly<{
    id: string;
    label: string;
    age: number;
    role: string;
    tagline: string;
    description: string;
    visual_identity: string;
    art_direction: string;
    concept_src: string;
  }>;
  readonly expression_variants: readonly Readonly<{
    id: string;
    src: string;
    alt: string;
    appearance_id: string;
    state: DialogueSceneExpressionState;
    label: string;
    description: string;
    slot: "right";
  }>[];
  readonly dialogue: readonly Readonly<{
    id: string;
    speaker: string;
    text: string;
    expression_state: DialogueSceneExpressionState;
  }>[];
}

const DEMO_ASSET_PATH =
  /^\/dialogue-scene\/demo(?:\/[a-z0-9][a-z0-9-]*)*\/[a-z0-9][a-z0-9.-]*\.png$/;
const INSTALLED_THEME_ASSET_PATH =
  /^\/dialogue-scene\/themes\/([a-f0-9]{64})\/assets\/[a-f0-9]{64}\.png$/;
// A run played in place, streamed from out/<tag>/ through the per-tag asset API.
// Installing a scene as the site's active theme is a separate, deliberate act;
// this is the shape you get when you open the run you just generated.
const RUN_ASSET_PATH =
  /^\/api\/assets\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/assets\/[A-Za-z0-9][A-Za-z0-9._-]*\.png$/;
const STABLE_ID = /^[a-z][a-z0-9-]{0,63}$/;

/** Validate the camelCase runtime/UI projection; this is not a persisted parser. */
export function validateDialogueSceneRuntimeFixture(
  value: unknown,
): DialogueSceneDemoFixture {
  const root = strictRecord(
    value,
    [
      "schemaVersion",
      "fixtureId",
      "mode",
      "authorship",
      "title",
      "sceneLabel",
      "profileIdentity",
      "presentation",
      "background",
      "appearance",
      "expressionVariants",
      "dialogue",
    ],
    "dialogue-scene runtime fixture",
  );

  if (root.schemaVersion !== DIALOGUE_SCENE_DEMO_SCHEMA_VERSION) {
    throw new Error("dialogue-scene demo fixture schemaVersion must be 1");
  }
  if (root.mode !== DIALOGUE_SCENE_DEMO_MODE) {
    throw new Error('dialogue-scene demo fixture mode must be "deterministic-demo"');
  }
  if (root.authorship !== DIALOGUE_SCENE_DEMO_AUTHORSHIP) {
    throw new Error('dialogue-scene demo fixture authorship must be "caller-authored"');
  }

  const presentationRaw = strictRecord(
    root.presentation,
    ["framingZoom", "sourceFramingZoom"],
    "dialogue-scene demo presentation",
  );
  const profileIdentityRaw = strictRecord(
    root.profileIdentity,
    ["profileId", "revision"],
    "dialogue-scene runtime profile identity",
  );
  const profileIdentity = Object.freeze({
    profileId: stableId(
      profileIdentityRaw.profileId,
      "profileIdentity.profileId",
    ),
    revision: strictInteger(
      profileIdentityRaw.revision,
      "profileIdentity.revision",
      1,
      2147483647,
    ),
  });

  const backgroundRaw = strictRecord(
    root.background,
    ["id", "src", "alt"],
    "dialogue-scene demo background",
  );
  const appearanceRaw = strictRecord(
    root.appearance,
    [
      "id",
      "label",
      "age",
      "role",
      "tagline",
      "description",
      "visualIdentity",
      "artDirection",
      "conceptSrc",
    ],
    "dialogue-scene demo appearance",
  );

  const appearanceId = stableId(appearanceRaw.id, "appearance.id");
  if (
    !Array.isArray(root.expressionVariants) ||
    root.expressionVariants.length !== DIALOGUE_SCENE_EXPRESSION_STATES.length
  ) {
    throw new Error(
      "dialogue-scene demo expressionVariants must contain the four required expression states",
    );
  }

  const variantStates = new Set<DialogueSceneExpressionState>();
  const variantIds = new Set<string>();
  const expressionVariants = Object.freeze(
    root.expressionVariants.map((rawVariant, index) => {
      const variant = strictRecord(
        rawVariant,
        [
          "id",
          "src",
          "alt",
          "appearanceId",
          "state",
          "label",
          "description",
          "slot",
        ],
        `dialogue-scene demo expressionVariants[${index}]`,
      );
      if (variant.slot !== "right") {
        throw new Error(
          `dialogue-scene demo expressionVariants[${index}].slot must be "right"`,
        );
      }
      const variantAppearanceId = stableId(
        variant.appearanceId,
        `expressionVariants[${index}].appearanceId`,
      );
      if (variantAppearanceId !== appearanceId) {
        throw new Error(
          "dialogue-scene demo expression variant must reference appearance.id",
        );
      }
      const state = expressionState(
        variant.state,
        `expressionVariants[${index}].state`,
      );
      if (variantStates.has(state)) {
        throw new Error(`dialogue-scene demo expression state is duplicated: ${state}`);
      }
      variantStates.add(state);
      const id = stableId(variant.id, `expressionVariants[${index}].id`);
      if (variantIds.has(id)) {
        throw new Error(`dialogue-scene demo expression variant id is duplicated: ${id}`);
      }
      variantIds.add(id);
      return Object.freeze({
        id,
        src: assetPath(variant.src, `expressionVariants[${index}].src`),
        alt: strictText(variant.alt, `expressionVariants[${index}].alt`, 160),
        appearanceId: variantAppearanceId,
        state,
        label: strictText(variant.label, `expressionVariants[${index}].label`, 64),
        description: strictText(
          variant.description,
          `expressionVariants[${index}].description`,
          220,
        ),
        slot: "right" as const,
      });
    }),
  );
  for (const requiredState of DIALOGUE_SCENE_EXPRESSION_STATES) {
    if (!variantStates.has(requiredState)) {
      throw new Error(`dialogue-scene demo expression state is missing: ${requiredState}`);
    }
  }

  if (
    !Array.isArray(root.dialogue) ||
    root.dialogue.length < 1 ||
    root.dialogue.length > 12
  ) {
    throw new Error("dialogue-scene demo dialogue must contain 1 to 12 beats");
  }
  const beatIds = new Set<string>();
  const dialogue = Object.freeze(
    root.dialogue.map((rawBeat, index) => {
      const beat = strictRecord(
        rawBeat,
        ["id", "speaker", "text", "expressionState"],
        `dialogue-scene demo dialogue[${index}]`,
      );
      const id = stableId(beat.id, `dialogue[${index}].id`);
      if (beatIds.has(id)) {
        throw new Error(`dialogue-scene demo dialogue id is duplicated: ${id}`);
      }
      beatIds.add(id);
      return Object.freeze({
        id,
        speaker: strictText(beat.speaker, `dialogue[${index}].speaker`, 80),
        text: strictText(beat.text, `dialogue[${index}].text`, 1000),
        expressionState: expressionState(
          beat.expressionState,
          `dialogue[${index}].expressionState`,
        ),
      });
    }),
  );

  const background = Object.freeze({
    id: stableId(backgroundRaw.id, "background.id"),
    src: assetPath(backgroundRaw.src, "background.src"),
    alt: strictText(backgroundRaw.alt, "background.alt", 160),
  });
  const appearance = Object.freeze({
    id: appearanceId,
    label: strictText(appearanceRaw.label, "appearance.label", 96),
    age: strictInteger(appearanceRaw.age, "appearance.age", 18, 120),
    role: strictText(appearanceRaw.role, "appearance.role", 160),
    tagline: strictText(appearanceRaw.tagline, "appearance.tagline", 160),
    description: strictText(appearanceRaw.description, "appearance.description", 3000),
    visualIdentity: strictText(
      appearanceRaw.visualIdentity,
      "appearance.visualIdentity",
      3000,
    ),
    artDirection: strictText(
      appearanceRaw.artDirection,
      "appearance.artDirection",
      220,
    ),
    conceptSrc: assetPath(appearanceRaw.conceptSrc, "appearance.conceptSrc"),
  });
  if (profileIdentity.profileId !== appearance.id) {
    throw new Error("dialogue-scene profile identity must reference appearance.id");
  }
  const assetPaths = [
    background.src,
    appearance.conceptSrc,
    ...expressionVariants.map((variant) => variant.src),
  ];
  if (
    new Set(assetPaths).size !==
    2 + expressionVariants.length
  ) {
    throw new Error("dialogue-scene demo asset paths must be distinct");
  }
  const installedBundleIds = assetPaths.map(
    (assetPathValue) => INSTALLED_THEME_ASSET_PATH.exec(assetPathValue)?.[1] ?? null,
  );
  const installedCount = installedBundleIds.filter(
    (bundleId): bundleId is string => bundleId !== null,
  ).length;
  if (installedCount !== 0 && installedCount !== assetPaths.length) {
    throw new Error(
      "dialogue-scene fixture assets must all use the committed demo or one installed bundle",
    );
  }
  const installedBundleIdValues = installedBundleIds.filter(
    (bundleId): bundleId is string => bundleId !== null,
  );
  if (
    installedCount > 0 &&
    new Set(installedBundleIdValues).size !== 1
  ) {
    throw new Error("dialogue-scene installed fixture assets must share one bundle id");
  }
  // A fixture assembled from two runs is two scenes wearing one name.
  const runTags = assetPaths.map(
    (assetPathValue) => RUN_ASSET_PATH.exec(assetPathValue)?.[1] ?? null,
  );
  const runTagValues = runTags.filter((tag): tag is string => tag !== null);
  if (runTagValues.length !== 0 && runTagValues.length !== assetPaths.length) {
    throw new Error(
      "dialogue-scene fixture assets must all use the committed demo, one installed bundle, or one run",
    );
  }
  if (runTagValues.length > 0 && new Set(runTagValues).size !== 1) {
    throw new Error("dialogue-scene run fixture assets must share one run tag");
  }
  const presentation = Object.freeze({
    framingZoom: strictFiniteNumber(
      presentationRaw.framingZoom,
      "presentation.framingZoom",
      0,
      100,
    ),
    sourceFramingZoom: strictFiniteNumber(
      presentationRaw.sourceFramingZoom,
      "presentation.sourceFramingZoom",
      0,
      100,
    ),
  });

  return Object.freeze({
    schemaVersion: DIALOGUE_SCENE_DEMO_SCHEMA_VERSION,
    fixtureId: stableId(root.fixtureId, "fixtureId"),
    mode: DIALOGUE_SCENE_DEMO_MODE,
    authorship: DIALOGUE_SCENE_DEMO_AUTHORSHIP,
    title: strictText(root.title, "title", 96),
    sceneLabel: strictText(root.sceneLabel, "sceneLabel", 160),
    presentation,
    background,
    appearance,
    expressionVariants,
    dialogue,
    profileIdentity,
  });
}

/** Parse the one current persisted/public theme fixture and adapt it to the UI shape. */
export function parseDialogueSceneThemeFixture(
  value: unknown,
): DialogueSceneDemoFixture {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "fixture_id",
      "mode",
      "authorship",
      "title",
      "scene_label",
      "profile_identity",
      "presentation",
      "background",
      "appearance",
      "expression_variants",
      "dialogue",
    ],
    "dialogue-scene theme fixture",
  );
  if (root.schema_version !== DIALOGUE_SCENE_THEME_FIXTURE_SCHEMA_VERSION) {
    throw new Error("dialogue-scene theme fixture schema_version must be 1");
  }
  if (root.kind !== DIALOGUE_SCENE_THEME_FIXTURE_KIND) {
    throw new Error(
      `dialogue-scene theme fixture kind must be ${DIALOGUE_SCENE_THEME_FIXTURE_KIND}`,
    );
  }
  const profile = strictRecord(
    root.profile_identity,
    ["profile_id", "revision"],
    "dialogue-scene theme fixture profile_identity",
  );
  const presentation = strictRecord(
    root.presentation,
    ["framing_zoom", "source_framing_zoom"],
    "dialogue-scene theme fixture presentation",
  );
  const background = strictRecord(
    root.background,
    ["id", "src", "alt"],
    "dialogue-scene theme fixture background",
  );
  const appearance = strictRecord(
    root.appearance,
    [
      "id",
      "label",
      "age",
      "role",
      "tagline",
      "description",
      "visual_identity",
      "art_direction",
      "concept_src",
    ],
    "dialogue-scene theme fixture appearance",
  );
  if (!Array.isArray(root.expression_variants)) {
    throw new Error("dialogue-scene theme fixture expression_variants must be an array");
  }
  const variants = root.expression_variants.map((value, index) => {
    const variant = strictRecord(
      value,
      [
        "id",
        "src",
        "alt",
        "appearance_id",
        "state",
        "label",
        "description",
        "slot",
      ],
      `dialogue-scene theme fixture expression_variants[${index}]`,
    );
    return {
      id: variant.id,
      src: variant.src,
      alt: variant.alt,
      appearanceId: variant.appearance_id,
      state: variant.state,
      label: variant.label,
      description: variant.description,
      slot: variant.slot,
    };
  });
  if (!Array.isArray(root.dialogue)) {
    throw new Error("dialogue-scene theme fixture dialogue must be an array");
  }
  const dialogue = root.dialogue.map((value, index) => {
    const beat = strictRecord(
      value,
      ["id", "speaker", "text", "expression_state"],
      `dialogue-scene theme fixture dialogue[${index}]`,
    );
    return {
      id: beat.id,
      speaker: beat.speaker,
      text: beat.text,
      expressionState: beat.expression_state,
    };
  });
  return validateDialogueSceneRuntimeFixture({
    schemaVersion: DIALOGUE_SCENE_DEMO_SCHEMA_VERSION,
    fixtureId: root.fixture_id,
    mode: root.mode,
    authorship: root.authorship,
    title: root.title,
    sceneLabel: root.scene_label,
    profileIdentity: {
      profileId: profile.profile_id,
      revision: profile.revision,
    },
    presentation: {
      framingZoom: presentation.framing_zoom,
      sourceFramingZoom: presentation.source_framing_zoom,
    },
    background,
    appearance: {
      id: appearance.id,
      label: appearance.label,
      age: appearance.age,
      role: appearance.role,
      tagline: appearance.tagline,
      description: appearance.description,
      visualIdentity: appearance.visual_identity,
      artDirection: appearance.art_direction,
      conceptSrc: appearance.concept_src,
    },
    expressionVariants: variants,
    dialogue,
  });
}

/** Project the internal UI fixture to the one current persisted/public contract. */
export function serializeDialogueSceneThemeFixture(
  fixture: DialogueSceneDemoFixture,
): DialogueSceneThemeFixtureV1 {
  const parsed = validateDialogueSceneRuntimeFixture(fixture);
  return Object.freeze({
    schema_version: DIALOGUE_SCENE_THEME_FIXTURE_SCHEMA_VERSION,
    kind: DIALOGUE_SCENE_THEME_FIXTURE_KIND,
    fixture_id: parsed.fixtureId,
    mode: parsed.mode,
    authorship: parsed.authorship,
    title: parsed.title,
    scene_label: parsed.sceneLabel,
    profile_identity: Object.freeze({
      profile_id: parsed.profileIdentity.profileId,
      revision: parsed.profileIdentity.revision,
    }),
    presentation: Object.freeze({
      framing_zoom: parsed.presentation.framingZoom,
      source_framing_zoom: parsed.presentation.sourceFramingZoom,
    }),
    background: Object.freeze({ ...parsed.background }),
    appearance: Object.freeze({
      id: parsed.appearance.id,
      label: parsed.appearance.label,
      age: parsed.appearance.age,
      role: parsed.appearance.role,
      tagline: parsed.appearance.tagline,
      description: parsed.appearance.description,
      visual_identity: parsed.appearance.visualIdentity,
      art_direction: parsed.appearance.artDirection,
      concept_src: parsed.appearance.conceptSrc,
    }),
    expression_variants: Object.freeze(
      parsed.expressionVariants.map((variant) =>
        Object.freeze({
          id: variant.id,
          src: variant.src,
          alt: variant.alt,
          appearance_id: variant.appearanceId,
          state: variant.state,
          label: variant.label,
          description: variant.description,
          slot: variant.slot,
        }),
      ),
    ),
    dialogue: Object.freeze(
      parsed.dialogue.map((beat) =>
        Object.freeze({
          id: beat.id,
          speaker: beat.speaker,
          text: beat.text,
          expression_state: beat.expressionState,
        }),
      ),
    ),
  });
}

function strictRecord(
  value: unknown,
  expectedKeys: readonly string[],
  label: string,
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const expected = new Set(expectedKeys);
  const missing = expectedKeys.filter(
    (key) => !Object.prototype.hasOwnProperty.call(record, key),
  );
  const extra = Object.keys(record).filter((key) => !expected.has(key));
  if (missing.length > 0 || extra.length > 0) {
    throw new Error(
      `${label} keys must match the schema` +
        `${missing.length > 0 ? `; missing ${missing.join(", ")}` : ""}` +
        `${extra.length > 0 ? `; unexpected ${extra.join(", ")}` : ""}`,
    );
  }
  return record;
}

function strictText(value: unknown, label: string, maxLength: number): string {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > maxLength ||
    value !== value.trim()
  ) {
    throw new Error(`${label} must be a non-empty trimmed string up to ${maxLength} characters`);
  }
  return value;
}

function strictFiniteNumber(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(`${label} must be a finite number from ${minimum} to ${maximum}`);
  }
  return value;
}

function strictInteger(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(`${label} must be an integer from ${minimum} to ${maximum}`);
  }
  return value;
}

function stableId(value: unknown, label: string): string {
  const parsed = strictText(value, label, 64);
  if (!STABLE_ID.test(parsed)) {
    throw new Error(`${label} must be a stable lowercase kebab-case id`);
  }
  return parsed;
}

function assetPath(value: unknown, label: string): string {
  const parsed = strictText(value, label, 240);
  if (
    !DEMO_ASSET_PATH.test(parsed) &&
    !INSTALLED_THEME_ASSET_PATH.test(parsed) &&
    !RUN_ASSET_PATH.test(parsed)
  ) {
    throw new Error(
      `${label} must be a confined dialogue-scene demo, installed-theme, or run PNG path`,
    );
  }
  return parsed;
}

function expressionState(value: unknown, label: string): DialogueSceneExpressionState {
  const parsed = strictText(value, label, 32);
  if (
    !DIALOGUE_SCENE_EXPRESSION_STATES.includes(
      parsed as DialogueSceneExpressionState,
    )
  ) {
    throw new Error(
      `${label} must be one of ${DIALOGUE_SCENE_EXPRESSION_STATES.join(", ")}`,
    );
  }
  return parsed as DialogueSceneExpressionState;
}
