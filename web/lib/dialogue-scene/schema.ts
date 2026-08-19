export const DIALOGUE_SCENE_DEMO_SCHEMA_VERSION = 1 as const;
export const DIALOGUE_SCENE_DEMO_MODE = "deterministic-demo" as const;
export const DIALOGUE_SCENE_DEMO_AUTHORSHIP = "caller-authored" as const;
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
}

const DEMO_ASSET_PATH =
  /^\/dialogue-scene\/demo(?:\/[a-z0-9][a-z0-9-]*)*\/[a-z0-9][a-z0-9.-]*\.png$/;
const STABLE_ID = /^[a-z][a-z0-9-]{0,63}$/;

export function parseDialogueSceneDemoFixture(value: unknown): DialogueSceneDemoFixture {
  const root = strictRecord(
    value,
    [
      "schemaVersion",
      "fixtureId",
      "mode",
      "authorship",
      "title",
      "sceneLabel",
      "presentation",
      "background",
      "appearance",
      "expressionVariants",
      "dialogue",
    ],
    "dialogue-scene demo fixture",
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
      return Object.freeze({
        id: stableId(variant.id, `expressionVariants[${index}].id`),
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
        speaker: strictText(beat.speaker, `dialogue[${index}].speaker`, 64),
        text: strictText(beat.text, `dialogue[${index}].text`, 320),
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
    age: strictInteger(appearanceRaw.age, "appearance.age", 21, 120),
    role: strictText(appearanceRaw.role, "appearance.role", 120),
    tagline: strictText(appearanceRaw.tagline, "appearance.tagline", 160),
    description: strictText(appearanceRaw.description, "appearance.description", 280),
    visualIdentity: strictText(
      appearanceRaw.visualIdentity,
      "appearance.visualIdentity",
      320,
    ),
    artDirection: strictText(
      appearanceRaw.artDirection,
      "appearance.artDirection",
      220,
    ),
    conceptSrc: assetPath(appearanceRaw.conceptSrc, "appearance.conceptSrc"),
  });
  if (
    new Set([
      background.src,
      appearance.conceptSrc,
      ...expressionVariants.map((variant) => variant.src),
    ]).size !==
    2 + expressionVariants.length
  ) {
    throw new Error("dialogue-scene demo asset paths must be distinct");
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
  const parsed = strictText(value, label, 160);
  if (!DEMO_ASSET_PATH.test(parsed)) {
    throw new Error(`${label} must be a confined /dialogue-scene/demo/**/*.png path`);
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
