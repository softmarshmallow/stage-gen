// Strict consumer boundary for the optional dialogue-character projection in a run manifest.
//
// The persisted document uses lower_snake_case. Everything returned from this module is the
// browser runtime's camelCase shape, frozen so gameplay code cannot accidentally turn reviewed
// dialogue or asset identity into mutable scene state.

import type Phaser from "phaser";
import { copyImageToCanvas } from "@/lib/sideview/image-ops";
import { registerCanvas } from "@/lib/sideview/assets";

export const DIALOGUE_EXPRESSION_STATES = Object.freeze([
  "neutral",
  "delighted",
  "flustered",
  "concerned",
] as const);

export type DialogueExpressionState =
  (typeof DIALOGUE_EXPRESSION_STATES)[number];

export type DialogueCharacterRuntimeAsset = Readonly<{
  state: DialogueExpressionState;
  path: string;
  sha256: string;
  bytes: number;
  mediaType: "image/png";
  width: 1024;
  height: 1536;
  alpha: true;
  provenancePath: string;
  provenanceSha256: string;
}>;

export type DialogueCharacterRuntimeBeat = Readonly<{
  id: string;
  speaker: string;
  text: string;
  expressionState: DialogueExpressionState;
}>;

export type DialogueCharacterRuntimeSpec = Readonly<{
  schemaVersion: 1;
  kind: "dialogue-character-runtime-v1";
  npcSlot: number;
  npcName: string;
  characterId: string;
  sourceBundleSha256: string;
  identitySha256: string;
  availableStates: typeof DIALOGUE_EXPRESSION_STATES;
  assets: readonly DialogueCharacterRuntimeAsset[];
  dialogue: readonly DialogueCharacterRuntimeBeat[];
  review: Readonly<{
    status: "pass";
    usage: "local-demo";
    sourceReviewSha256: string;
  }>;
  rights: Readonly<{
    aggregate: "restricted";
    publicationAuthorized: false;
  }>;
}>;

export type DialogueCharactersManifestParseResult = Readonly<{
  status: "absent" | "valid";
  characters: readonly DialogueCharacterRuntimeSpec[];
  diagnostic: string | null;
}>;

export type DialogueAssetIntegrityExpectation = Readonly<{
  bytes: number;
  sha256: string;
}>;

const EMPTY_CHARACTERS = Object.freeze([] as DialogueCharacterRuntimeSpec[]);
const SHA256 = /^[a-f0-9]{64}$/;
const STABLE_ID = /^[a-z][a-z0-9-]{0,63}$/;
const DIALOGUE_BEAT_ID = /^[a-z][a-z0-9-]{0,47}$/;
const CONTENT_ADDRESSED_PNG = /^dialogue-character-([a-f0-9]{64})\.png$/;
const CONTENT_ADDRESSED_PROVENANCE =
  /^dialogue-character-([a-f0-9]{64})\.png\.meta\.json$/;

/**
 * Parse the optional top-level projection. A declared block is transactional: one malformed
 * character rejects all of it, so gameplay never combines a reviewed asset from one item with
 * dialogue or identity from another.
 */
export function parseDialogueCharactersManifest(
  value: unknown,
): DialogueCharactersManifestParseResult {
  if (!isRecord(value)) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }
  if (value["schema_version"] !== 7) {
    throw new Error("scrolling-preview manifest schema_version must be 7");
  }
  if (!hasOwn(value, "dialogue_characters")) {
    return Object.freeze({
      status: "absent",
      characters: EMPTY_CHARACTERS,
      diagnostic: null,
    });
  }
  const declared = value["dialogue_characters"];
  if (!Array.isArray(declared) || declared.length === 0) {
    throw new Error("dialogue_characters must be a non-empty array");
  }

  const characters = declared.map((item, index) =>
    parseCharacter(item, `dialogue_characters[${index}]`),
  );
  const slots = new Set<number>();
  const characterIds = new Set<string>();
  for (const character of characters) {
    if (slots.has(character.npcSlot)) {
      throw new Error("dialogue_characters contains a duplicate npc_slot");
    }
    if (characterIds.has(character.characterId)) {
      throw new Error("dialogue_characters contains a duplicate character_id");
    }
    slots.add(character.npcSlot);
    characterIds.add(character.characterId);
  }
  return Object.freeze({
    status: "valid",
    characters: Object.freeze(characters),
    diagnostic: null,
  });
}

/** Pure comparison used after hashing fetched bytes and before image decode/registration. */
export function verifyDialogueAssetIntegrity(
  actual: Readonly<{ bytes: number; sha256: string }>,
  expected: DialogueAssetIntegrityExpectation,
): boolean {
  return (
    Number.isSafeInteger(actual.bytes) &&
    actual.bytes === expected.bytes &&
    SHA256.test(actual.sha256) &&
    actual.sha256 === expected.sha256
  );
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

/**
 * Fetch, byte-check, hash-check and decode one declared overlay asset. Registration is last, so
 * no unverified bytes can ever become a Phaser texture. This loader is intentionally unavailable
 * to other asset families: only dialogue-character assets publish this integrity contract.
 */
export async function loadVerifiedDialogueSprite(opts: {
  url: string;
  key: string;
  asset: DialogueCharacterRuntimeAsset;
  textures: Phaser.Textures.TextureManager;
}): Promise<HTMLCanvasElement> {
  const response = await fetch(opts.url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("dialogue character asset fetch failed");
  }
  const encoded = await response.arrayBuffer();
  const actualSha256 = await sha256Hex(encoded);
  if (
    !verifyDialogueAssetIntegrity(
      { bytes: encoded.byteLength, sha256: actualSha256 },
      opts.asset,
    )
  ) {
    throw new Error("dialogue character asset integrity check failed");
  }

  const image = await decodePng(encoded);
  const canvas = copyImageToCanvas(image);
  if (canvas.width !== opts.asset.width || canvas.height !== opts.asset.height) {
    throw new Error("dialogue character asset dimensions do not match manifest");
  }
  if (!canvasHasTransparency(canvas)) {
    throw new Error("dialogue character asset must contain transparent pixels");
  }
  registerCanvas(opts.textures, opts.key, canvas);
  return canvas;
}

function parseCharacter(
  value: unknown,
  label: string,
): DialogueCharacterRuntimeSpec {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "npc_slot",
      "npc_name",
      "character_id",
      "source_bundle_sha256",
      "identity_sha256",
      "available_states",
      "assets",
      "dialogue",
      "review",
      "rights",
    ],
    label,
  );
  // Avoid an invisible/unexpected wire key being accepted as the real contract field.
  if (!hasOwn(root, "dialogue")) {
    throw new Error(`${label} must contain exactly the declared runtime keys`);
  }
  if (root["schema_version"] !== 1) {
    throw new Error(`${label}.schema_version must be 1`);
  }
  if (root["kind"] !== "dialogue-character-runtime-v1") {
    throw new Error(`${label}.kind is unsupported`);
  }
  const availableStates = exactStates(root["available_states"], label);
  const rawAssets = root["assets"];
  if (
    !Array.isArray(rawAssets) ||
    rawAssets.length !== DIALOGUE_EXPRESSION_STATES.length
  ) {
    throw new Error(`${label}.assets must contain exactly four states`);
  }
  const assets = rawAssets.map((asset, index) =>
    parseAsset(asset, `${label}.assets[${index}]`),
  );
  if (
    assets.some(
      (asset, index) => asset.state !== DIALOGUE_EXPRESSION_STATES[index],
    )
  ) {
    throw new Error(`${label}.assets must use the locked state order`);
  }

  const rawDialogue = root["dialogue"];
  if (!Array.isArray(rawDialogue) || rawDialogue.length < 1 || rawDialogue.length > 12) {
    throw new Error(`${label}.dialogue must contain 1 to 12 beats`);
  }
  const dialogue = rawDialogue.map((beat, index) =>
    parseBeat(beat, `${label}.dialogue[${index}]`),
  );
  if (new Set(dialogue.map((beat) => beat.id)).size !== dialogue.length) {
    throw new Error(`${label}.dialogue ids must be unique`);
  }

  const review = strictRecord(
    root["review"],
    ["status", "usage", "source_review_sha256"],
    `${label}.review`,
  );
  if (review["status"] !== "pass" || review["usage"] !== "local-demo") {
    throw new Error(`${label}.review is not approved for local demo use`);
  }
  const rights = strictRecord(
    root["rights"],
    ["aggregate", "publication_authorized"],
    `${label}.rights`,
  );
  if (
    rights["aggregate"] !== "restricted" ||
    rights["publication_authorized"] !== false
  ) {
    throw new Error(`${label}.rights must remain restricted and unpublished`);
  }

  return Object.freeze({
    schemaVersion: 1,
    kind: "dialogue-character-runtime-v1",
    npcSlot: boundedInteger(root["npc_slot"], `${label}.npc_slot`, 0, 3),
    npcName: boundedString(root["npc_name"], `${label}.npc_name`, 96),
    characterId: stableId(root["character_id"], `${label}.character_id`),
    sourceBundleSha256: digest(root["source_bundle_sha256"], `${label}.source_bundle_sha256`),
    identitySha256: digest(root["identity_sha256"], `${label}.identity_sha256`),
    availableStates,
    assets: Object.freeze(assets),
    dialogue: Object.freeze(dialogue),
    review: Object.freeze({
      status: "pass",
      usage: "local-demo",
      sourceReviewSha256: digest(
        review["source_review_sha256"],
        `${label}.review.source_review_sha256`,
      ),
    }),
    rights: Object.freeze({
      aggregate: "restricted",
      publicationAuthorized: false,
    }),
  });
}

function parseAsset(value: unknown, label: string): DialogueCharacterRuntimeAsset {
  const asset = strictRecord(
    value,
    [
      "state",
      "path",
      "sha256",
      "bytes",
      "media_type",
      "width",
      "height",
      "alpha",
      "provenance_path",
      "provenance_sha256",
    ],
    label,
  );
  if (
    asset["media_type"] !== "image/png" ||
    asset["width"] !== 1024 ||
    asset["height"] !== 1536 ||
    asset["alpha"] !== true
  ) {
    throw new Error(`${label} must be a 1024x1536 alpha PNG`);
  }
  const sha256 = digest(asset["sha256"], `${label}.sha256`);
  return Object.freeze({
    state: expressionState(asset["state"], `${label}.state`),
    path: contentAddressedPath(
      asset["path"],
      CONTENT_ADDRESSED_PNG,
      sha256,
      `${label}.path`,
    ),
    sha256,
    bytes: boundedInteger(
      asset["bytes"],
      `${label}.bytes`,
      1,
      Number.MAX_SAFE_INTEGER,
    ),
    mediaType: "image/png",
    width: 1024,
    height: 1536,
    alpha: true,
    provenancePath: contentAddressedPath(
      asset["provenance_path"],
      CONTENT_ADDRESSED_PROVENANCE,
      sha256,
      `${label}.provenance_path`,
    ),
    provenanceSha256: digest(
      asset["provenance_sha256"],
      `${label}.provenance_sha256`,
    ),
  });
}

function parseBeat(value: unknown, label: string): DialogueCharacterRuntimeBeat {
  const beat = strictRecord(
    value,
    ["id", "speaker", "text", "expression_state"],
    label,
  );
  return Object.freeze({
    id: beatId(beat["id"], `${label}.id`),
    speaker: boundedString(beat["speaker"], `${label}.speaker`, 64),
    text: boundedString(beat["text"], `${label}.text`, 320),
    expressionState: expressionState(
      beat["expression_state"],
      `${label}.expression_state`,
    ),
  });
}

function exactStates(value: unknown, label: string): typeof DIALOGUE_EXPRESSION_STATES {
  if (
    !Array.isArray(value) ||
    value.length !== DIALOGUE_EXPRESSION_STATES.length ||
    value.some((state, index) => state !== DIALOGUE_EXPRESSION_STATES[index])
  ) {
    throw new Error(`${label}.available_states must use the canonical order`);
  }
  return DIALOGUE_EXPRESSION_STATES;
}

function expressionState(value: unknown, label: string): DialogueExpressionState {
  if (
    typeof value !== "string" ||
    !DIALOGUE_EXPRESSION_STATES.includes(value as DialogueExpressionState)
  ) {
    throw new Error(`${label} is not a supported expression state`);
  }
  return value as DialogueExpressionState;
}

function strictRecord(
  value: unknown,
  keys: readonly string[],
  label: string,
): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${label} must be an object`);
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (
    actual.length !== expected.length ||
    actual.some((key, index) => key !== expected[index])
  ) {
    throw new Error(`${label} must contain exactly the declared runtime keys`);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOwn(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function digest(value: unknown, label: string): string {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new Error(`${label} must be a lowercase sha256 digest`);
  }
  return value;
}

function boundedInteger(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(
      `${label} must be a safe integer from ${minimum} through ${maximum}`,
    );
  }
  return value;
}

function boundedString(value: unknown, label: string, maximum: number): string {
  if (typeof value !== "string" || value.length < 1 || value.length > maximum) {
    throw new Error(`${label} must contain 1 to ${maximum} characters`);
  }
  return value;
}

function stableId(value: unknown, label: string): string {
  if (typeof value !== "string" || !STABLE_ID.test(value)) {
    throw new Error(`${label} must be a stable id`);
  }
  return value;
}

function beatId(value: unknown, label: string): string {
  if (typeof value !== "string" || !DIALOGUE_BEAT_ID.test(value)) {
    throw new Error(`${label} must be a dialogue beat id`);
  }
  return value;
}

function contentAddressedPath(
  value: unknown,
  pattern: RegExp,
  assetSha256: string,
  label: string,
): string {
  const match = typeof value === "string" ? pattern.exec(value) : null;
  if (match?.[1] !== assetSha256) {
    throw new Error(`${label} must be content-addressed by the asset sha256`);
  }
  return value as string;
}

function decodePng(encoded: ArrayBuffer): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(
      new Blob([encoded], { type: "image/png" }),
    );
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("dialogue character asset PNG decode failed"));
    };
    image.src = objectUrl;
  });
}

function canvasHasTransparency(canvas: HTMLCanvasElement): boolean {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("dialogue character asset requires a 2d canvas");
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  for (let offset = 3; offset < pixels.length; offset += 4) {
    if (pixels[offset] < 255) return true;
  }
  return false;
}
