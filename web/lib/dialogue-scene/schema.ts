// The visual-novel runtime fixture: what one played scene needs, and nothing else.
//
// Validated by hand and strictly, the way every persisted contract in this
// repository is - unknown keys and missing keys are both refused, because a
// fixture that parsed by ignoring a field is a fixture nobody can reason about.
//
// A scene has a cast and a set of stages now. It used to have exactly one
// character and exactly one backdrop, and the shape said so in a dozen places;
// what is left is a list of actors, a list of stages, and the compiled scenario
// that decides which of them is on screen at any moment.

import { parseScenarioProgram, type ScenarioProgram } from "@/lib/scenario/program";

export const DIALOGUE_SCENE_FIXTURE_SCHEMA_VERSION = 1 as const;
export const DIALOGUE_SCENE_EXPRESSION_STATES = Object.freeze([
  "neutral",
  "delighted",
  "flustered",
  "concerned",
] as const);

export type DialogueSceneExpressionState =
  (typeof DIALOGUE_SCENE_EXPRESSION_STATES)[number];

export interface DialogueSceneAsset {
  readonly id: string;
  readonly src: string;
  readonly alt: string;
}

export interface DialogueSceneStage extends DialogueSceneAsset {
  /** The scenario's own `stage_id`, which `stage <id>` switches to. */
  readonly stageId: string;
}

export interface DialogueSceneAppearance {
  readonly id: string;
  readonly label: string;
  readonly age: number;
  readonly role: string;
  readonly description: string;
  readonly visualIdentity: string;
  readonly artDirection: string;
}

export interface DialogueSceneExpressionVariant extends DialogueSceneAsset {
  readonly state: DialogueSceneExpressionState;
  readonly label: string;
  readonly description: string;
}

export interface DialogueSceneActor {
  /** The scenario's own `actor_id`, which `show <id>` names. */
  readonly actorId: string;
  readonly appearance: DialogueSceneAppearance;
  readonly expressions: readonly DialogueSceneExpressionVariant[];
}

export interface DialogueScenePresentation {
  readonly framingZoom: number;
  readonly sourceFramingZoom: number;
}

export interface DialogueSceneTrack {
  readonly trackId: string;
  readonly id: string;
  readonly src: string;
}

export interface DialogueSceneFixture {
  readonly schemaVersion: typeof DIALOGUE_SCENE_FIXTURE_SCHEMA_VERSION;
  readonly fixtureId: string;
  readonly title: string;
  readonly sceneLabel: string;
  readonly presentation: DialogueScenePresentation;
  readonly styleSrc: string;
  readonly stages: readonly DialogueSceneStage[];
  /** Empty when the scenario declares no music; a silent scene is valid. */
  readonly tracks: readonly DialogueSceneTrack[];
  readonly actors: readonly DialogueSceneActor[];
  /** The compiled narrative this scene plays; see `lib/scenario`. */
  readonly scenario: ScenarioProgram;
}

// A run played in place, streamed from out/<tag>/ through the per-tag asset API,
// or a reviewed bundle installed as a theme. Both are digest-addressed; nothing
// else may reach the canvas.
const RUN_ASSET_PATH =
  /^\/api\/assets\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/assets\/[A-Za-z0-9][A-Za-z0-9._-]*\.png$/;
const INSTALLED_THEME_ASSET_PATH =
  /^\/dialogue-scene\/themes\/([a-f0-9]{64})\/assets\/[a-f0-9]{64}\.png$/;
// Audio is confined exactly as art is, in its own pair rather than by loosening
// the image patterns: a backdrop that resolved to an .mp3 should still be refused.
const RUN_AUDIO_PATH =
  /^\/api\/assets\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/assets\/[A-Za-z0-9][A-Za-z0-9._-]*\.mp3$/;
const INSTALLED_THEME_AUDIO_PATH =
  /^\/dialogue-scene\/themes\/([a-f0-9]{64})\/assets\/[a-f0-9]{64}\.mp3$/;
const STABLE_ID = /^[a-z][a-z0-9-]{0,63}$/;
const SNAKE_ID = /^[a-z][a-z0-9_]{0,63}$/;

/**
 * Validate one runtime fixture, including that its art covers its narrative.
 *
 * The cross-check is the point: a scenario may only `stage` and `show` things
 * this fixture has a plate for. Without it a missing texture would be discovered
 * by a player mid-scene rather than by the validator that had every fact needed
 * to refuse it.
 */
export function validateDialogueSceneFixture(value: unknown): DialogueSceneFixture {
  const root = strictRecord(
    value,
    [
      "schemaVersion",
      "fixtureId",
      "title",
      "sceneLabel",
      "presentation",
      "styleSrc",
      "stages",
      "tracks",
      "actors",
      "scenario",
    ],
    "dialogue-scene fixture",
  );
  if (root.schemaVersion !== DIALOGUE_SCENE_FIXTURE_SCHEMA_VERSION) {
    throw new Error("dialogue-scene fixture schemaVersion must be 1");
  }
  const presentationRaw = strictRecord(
    root.presentation,
    ["framingZoom", "sourceFramingZoom"],
    "dialogue-scene fixture presentation",
  );
  const scenario = parseScenarioProgram(root.scenario);

  const stages = Object.freeze(
    list(root.stages, "stages", 1).map((entry, index) => {
      const stage = strictRecord(
        entry,
        ["stageId", "id", "src", "alt"],
        `dialogue-scene fixture stages[${index}]`,
      );
      return Object.freeze({
        stageId: snakeId(stage.stageId, `stages[${index}].stageId`),
        id: stableId(stage.id, `stages[${index}].id`),
        src: assetPath(stage.src, `stages[${index}].src`),
        alt: strictText(stage.alt, `stages[${index}].alt`, 160),
      });
    }),
  );
  const tracks = Object.freeze(
    list(root.tracks, "tracks", 0).map((entry, index) => {
      const track = strictRecord(
        entry,
        ["trackId", "id", "src"],
        `dialogue-scene fixture tracks[${index}]`,
      );
      return Object.freeze({
        trackId: snakeId(track.trackId, `tracks[${index}].trackId`),
        id: stableId(track.id, `tracks[${index}].id`),
        src: audioPath(track.src, `tracks[${index}].src`),
      });
    }),
  );
  const actors = Object.freeze(
    list(root.actors, "actors", 1).map((entry, index) => actor(entry, index)),
  );

  const fixture: DialogueSceneFixture = Object.freeze({
    schemaVersion: DIALOGUE_SCENE_FIXTURE_SCHEMA_VERSION,
    fixtureId: stableId(root.fixtureId, "fixtureId"),
    title: strictText(root.title, "title", 96),
    sceneLabel: strictText(root.sceneLabel, "sceneLabel", 160),
    presentation: Object.freeze({
      framingZoom: framing(presentationRaw.framingZoom, "presentation.framingZoom"),
      sourceFramingZoom: framing(
        presentationRaw.sourceFramingZoom,
        "presentation.sourceFramingZoom",
      ),
    }),
    styleSrc: assetPath(root.styleSrc, "styleSrc"),
    stages,
    tracks,
    actors,
    scenario,
  });

  assertOneOrigin(fixture);
  assertArtCoversNarrative(fixture);
  assertAudioCoversNarrative(fixture);
  return fixture;
}

/** The stage a scenario id names, or null when the fixture has no plate for it. */
export function dialogueSceneStage(
  fixture: DialogueSceneFixture,
  stageId: string,
): DialogueSceneStage | null {
  return fixture.stages.find((stage) => stage.stageId === stageId) ?? null;
}

/** One actor's plate at a given expression, or null when either is unknown. */
export function dialogueSceneExpression(
  fixture: DialogueSceneFixture,
  actorId: string,
  state: string | null,
): DialogueSceneExpressionVariant | null {
  const found = fixture.actors.find((entry) => entry.actorId === actorId);
  if (found === undefined) return null;
  return (
    found.expressions.find((variant) => variant.state === (state ?? "neutral")) ??
    found.expressions[0] ??
    null
  );
}

// ---------------------------------------------------------------- validation

function actor(value: unknown, index: number): DialogueSceneActor {
  const record = strictRecord(
    value,
    ["actorId", "appearance", "expressions"],
    `dialogue-scene fixture actors[${index}]`,
  );
  const appearanceRaw = strictRecord(
    record.appearance,
    ["id", "label", "age", "role", "description", "visualIdentity", "artDirection"],
    `dialogue-scene fixture actors[${index}].appearance`,
  );
  const appearanceId = stableId(appearanceRaw.id, `actors[${index}].appearance.id`);
  const seen = new Set<string>();
  const expressions = list(
    record.expressions,
    `actors[${index}].expressions`,
    1,
  ).map((entry, at) => {
    const variant = strictRecord(
      entry,
      ["id", "src", "alt", "state", "label", "description"],
      `dialogue-scene fixture actors[${index}].expressions[${at}]`,
    );
    const state = expressionState(variant.state, `actors[${index}].expressions[${at}].state`);
    if (seen.has(state)) {
      throw new Error(`dialogue-scene fixture actor ${appearanceId} repeats state ${state}`);
    }
    seen.add(state);
    return Object.freeze({
      id: stableId(variant.id, `actors[${index}].expressions[${at}].id`),
      src: assetPath(variant.src, `actors[${index}].expressions[${at}].src`),
      alt: strictText(variant.alt, `actors[${index}].expressions[${at}].alt`, 160),
      state,
      label: strictText(variant.label, `actors[${index}].expressions[${at}].label`, 96),
      description: strictText(
        variant.description,
        `actors[${index}].expressions[${at}].description`,
        200,
      ),
    });
  });
  return Object.freeze({
    actorId: snakeId(record.actorId, `actors[${index}].actorId`),
    appearance: Object.freeze({
      id: appearanceId,
      label: strictText(appearanceRaw.label, `actors[${index}].appearance.label`, 96),
      age: strictInteger(appearanceRaw.age, `actors[${index}].appearance.age`, 18, 120),
      role: strictText(appearanceRaw.role, `actors[${index}].appearance.role`, 160),
      description: strictText(
        appearanceRaw.description,
        `actors[${index}].appearance.description`,
        3000,
      ),
      visualIdentity: strictText(
        appearanceRaw.visualIdentity,
        `actors[${index}].appearance.visualIdentity`,
        3000,
      ),
      artDirection: strictText(
        appearanceRaw.artDirection,
        `actors[${index}].appearance.artDirection`,
        200,
      ),
    }),
    expressions: Object.freeze(expressions),
  });
}

/**
 * Every asset comes from the same run, or the same installed bundle.
 *
 * A fixture assembled from two runs is two scenes wearing one name: the sprites
 * would be drawn against a plate the backdrop never saw.
 */
function assertOneOrigin(fixture: DialogueSceneFixture): void {
  const paths = [
    fixture.styleSrc,
    ...fixture.stages.map((stage) => stage.src),
    ...fixture.actors.flatMap((entry) => entry.expressions.map((variant) => variant.src)),
    ...fixture.tracks.map((track) => track.src),
  ];
  if (new Set(paths).size !== paths.length) {
    throw new Error("dialogue-scene fixture asset paths must be distinct");
  }
  const origins = new Set(
    paths.map((path) => {
      const run = RUN_ASSET_PATH.exec(path);
      if (run !== null) return `run:${run[1]}`;
      const theme = INSTALLED_THEME_ASSET_PATH.exec(path);
      if (theme !== null) return `theme:${theme[1]}`;
      const runAudio = RUN_AUDIO_PATH.exec(path);
      if (runAudio !== null) return `run:${runAudio[1]}`;
      const themeAudio = INSTALLED_THEME_AUDIO_PATH.exec(path);
      if (themeAudio !== null) return `theme:${themeAudio[1]}`;
      throw new Error(`dialogue-scene fixture asset path is not confined: ${path}`);
    }),
  );
  if (origins.size !== 1) {
    throw new Error("dialogue-scene fixture assets must all share one run or installed bundle");
  }
}

function assertAudioCoversNarrative(fixture: DialogueSceneFixture): void {
  const trackIds = new Set(fixture.tracks.map((track) => track.trackId));
  for (const track of fixture.scenario.tracks) {
    if (!trackIds.has(track.trackId)) {
      throw new Error(`dialogue-scene fixture has no audio for track ${track.trackId}`);
    }
  }
}

function assertArtCoversNarrative(fixture: DialogueSceneFixture): void {
  const stageIds = new Set(fixture.stages.map((stage) => stage.stageId));
  for (const stage of fixture.scenario.stages) {
    if (!stageIds.has(stage.stageId)) {
      throw new Error(
        `dialogue-scene fixture has no backdrop for stage ${stage.stageId}`,
      );
    }
  }
  const byActor = new Map(fixture.actors.map((entry) => [entry.actorId, entry]));
  for (const member of fixture.scenario.cast) {
    if (member.expressions.length === 0) continue;
    const drawn = byActor.get(member.actorId);
    if (drawn === undefined) {
      throw new Error(`dialogue-scene fixture has no plates for actor ${member.actorId}`);
    }
    const states = new Set(drawn.expressions.map((variant) => variant.state));
    for (const expression of member.expressions) {
      if (!states.has(expression as DialogueSceneExpressionState)) {
        throw new Error(
          `dialogue-scene fixture actor ${member.actorId} has no ${expression} plate`,
        );
      }
    }
  }
}

// ------------------------------------------------------------------- scalars

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

function list(value: unknown, label: string, minimum: number): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`dialogue-scene fixture ${label} must be an array`);
  if (value.length < minimum) {
    throw new Error(`dialogue-scene fixture ${label} must contain at least ${minimum} entries`);
  }
  return value;
}

function strictText(value: unknown, label: string, maxLength: number): string {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value) {
    throw new Error(`dialogue-scene fixture ${label} must be a trimmed non-empty string`);
  }
  if (value.length > maxLength) {
    throw new Error(`dialogue-scene fixture ${label} must be at most ${maxLength} characters`);
  }
  return value;
}

function strictInteger(value: unknown, label: string, min: number, max: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < min || (value as number) > max) {
    throw new Error(`dialogue-scene fixture ${label} must be an integer from ${min} to ${max}`);
  }
  return value as number;
}

function framing(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`dialogue-scene fixture ${label} must be a finite value from 0 through 100`);
  }
  return value;
}

function stableId(value: unknown, label: string): string {
  if (typeof value !== "string" || !STABLE_ID.test(value)) {
    throw new Error(`dialogue-scene fixture ${label} must be a stable kebab id`);
  }
  return value;
}

function snakeId(value: unknown, label: string): string {
  if (typeof value !== "string" || !SNAKE_ID.test(value)) {
    throw new Error(`dialogue-scene fixture ${label} must be a lower_snake_case id`);
  }
  return value;
}

function assetPath(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    (!RUN_ASSET_PATH.test(value) && !INSTALLED_THEME_ASSET_PATH.test(value))
  ) {
    throw new Error(
      `dialogue-scene fixture ${label} must be a confined run or installed-theme PNG path`,
    );
  }
  return value;
}

function audioPath(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    (!RUN_AUDIO_PATH.test(value) && !INSTALLED_THEME_AUDIO_PATH.test(value))
  ) {
    throw new Error(
      `dialogue-scene fixture ${label} must be a confined run or installed-theme MP3 path`,
    );
  }
  return value;
}

function expressionState(value: unknown, label: string): DialogueSceneExpressionState {
  if (
    typeof value !== "string" ||
    !(DIALOGUE_SCENE_EXPRESSION_STATES as readonly string[]).includes(value)
  ) {
    throw new Error(
      `dialogue-scene fixture ${label} must be one of ` +
        DIALOGUE_SCENE_EXPRESSION_STATES.join(", "),
    );
  }
  return value as DialogueSceneExpressionState;
}
