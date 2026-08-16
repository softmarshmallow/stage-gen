import { createHash } from "node:crypto";
import { promises as fs, type Stats } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";
import {
  GAMEPLAY_AUTOMATION_VERSION,
  GAMEPLAY_FIXTURE_METADATA_FILE,
  gameplayRequiredAssetKeys,
  type GameplayFixture,
} from "./contracts";

const GAMEPLAY_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(GAMEPLAY_DIR, "../../..");
export const GAMEPLAY_DEMO_ROOT = path.join(REPO_ROOT, "fixtures", "gameplay-demo");
export const GAMEPLAY_DEMO_ASSET_MANIFEST = "asset-manifest.json";
export const GAMEPLAY_DEMO_APPROVAL_MANIFEST = "approval-manifest.json";
const MAX_MANIFEST_BYTES = 1_000_000;
const MAX_PNG_BYTES = 20_000_000;
const CELL_GUTTER_PIXELS = 2;
const REQUIRED_GUTTER_ASSET_IDS = new Set(["tileset", "character-attack"]);
const FAL_BACKGROUND_REMOVAL_PROVIDER = "fal";
const FAL_BACKGROUND_REMOVAL_MODEL = "fal-ai/birefnet/v2";
const WORLD_NAME = "Moonlit Overgrown Ruins";

export const GAMEPLAY_MODEL_PROMPT =
  "moonlit overgrown ruins model-generated gameplay showcase";
export const GAMEPLAY_MODEL_TRANSPARENCY_MODE = "ai" as const;
export const GAMEPLAY_MODEL_TAG =
  "moonlit-overgrown-ruins-model-generated-346cf767-ai";
export const GAMEPLAY_MODEL_TERRAIN_SEED = 1_235_206_006;
export const GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS = gameplayRequiredAssetKeys(WORLD_NAME);

type AlphaExpectation = "opaque" | "transparent";

const RUNTIME_SLOTS: Readonly<Record<string, string>> = {
  concept: "concept_<tag>.png",
  "layer-sky": "layer_<tag>_sky.png",
  "layer-ridges": "layer_<tag>_ridges.png",
  "layer-foreground": "layer_<tag>_foreground.png",
  tileset: "tileset_<tag>.png",
  "character-concept": "character_concept_<tag>.png",
  "character-idle": "character_<tag>-fromcombined_idle.png",
  "character-walk": "character_<tag>-fromcombined_walk.png",
  "character-run": "character_<tag>-fromcombined_run.png",
  "character-jump": "character_<tag>-fromcombined_jump.png",
  "character-crawl": "character_<tag>-fromcombined_crawl.png",
  "character-attack": "character_<tag>_attack.png",
  "mob-concept": "mob_concept_<tag>_0.png",
  "mob-idle": "mob_<tag>_0_idle.png",
  "mob-hurt": "mob_<tag>_0_hurt.png",
  items: "items_<tag>.png",
  inventory: "inventory_<tag>.png",
  portal: "portal_<tag>.png",
};

export type GameplayModelAssetContract = Readonly<{
  id: string;
  path: string;
  runtimeSlot: string;
  width: number;
  height: number;
  rows: number;
  columns: number;
  alphaExpectation: AlphaExpectation;
}>;

const GAMEPLAY_MODEL_ASSET_SHAPES: readonly Omit<
  GameplayModelAssetContract,
  "path" | "runtimeSlot"
>[] = [
  { id: "concept", width: 1280, height: 720, rows: 1, columns: 1, alphaExpectation: "opaque" },
  { id: "layer-sky", width: 1280, height: 720, rows: 1, columns: 1, alphaExpectation: "opaque" },
  { id: "layer-ridges", width: 1280, height: 720, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { id: "layer-foreground", width: 1280, height: 720, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { id: "tileset", width: 384, height: 128, rows: 4, columns: 12, alphaExpectation: "transparent" },
  { id: "character-concept", width: 128, height: 192, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { id: "character-idle", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "character-walk", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "character-run", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "character-jump", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "character-crawl", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "character-attack", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "mob-concept", width: 128, height: 128, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { id: "mob-idle", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "mob-hurt", width: 256, height: 128, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { id: "items", width: 256, height: 128, rows: 2, columns: 4, alphaExpectation: "transparent" },
  { id: "inventory", width: 512, height: 320, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { id: "portal", width: 256, height: 192, rows: 1, columns: 2, alphaExpectation: "transparent" },
];

export const GAMEPLAY_MODEL_ASSET_CONTRACTS: readonly GameplayModelAssetContract[] =
  Object.freeze(GAMEPLAY_MODEL_ASSET_SHAPES.map((asset) => {
    return Object.freeze({
      ...asset,
      path: `${asset.id}.png`,
      runtimeSlot: RUNTIME_SLOTS[asset.id],
    });
  }));

const GAMEPLAY_MODEL_TRANSPARENT_ASSET_IDS = Object.freeze(
  GAMEPLAY_MODEL_ASSET_CONTRACTS.filter(
    (asset) => asset.alphaExpectation === "transparent",
  )
    .map((asset) => asset.id)
    .sort(),
);

export const GAMEPLAY_MODEL_FIXTURE_FILES = Object.freeze(
  [
    ...GAMEPLAY_MODEL_ASSET_CONTRACTS.map((asset) =>
      asset.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG),
    ),
    `world_spec_${GAMEPLAY_MODEL_TAG}.json`,
    "run.json",
    GAMEPLAY_FIXTURE_METADATA_FILE,
  ].sort(),
);

type JsonRecord = Record<string, unknown>;

function record(value: unknown, label: string): JsonRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as JsonRecord;
}

function stableText(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value !== value.trim() ||
    value.length > 8_192 ||
    /[\0\r]/.test(value)
  ) {
    throw new Error(`${label} must be stable nonempty text`);
  }
  return value;
}

function safeRelative(value: unknown, label: string): string {
  const candidate = stableText(value, label);
  if (
    candidate.includes("\\") ||
    path.posix.isAbsolute(candidate) ||
    path.posix.normalize(candidate) !== candidate ||
    candidate.split("/").some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error(`${label} must be a canonical relative path`);
  }
  return candidate;
}

function digest(value: unknown, label: string): string {
  if (typeof value !== "string" || !/^[0-9a-f]{64}$/.test(value)) {
    throw new Error(`${label} must be a lowercase SHA-256 digest`);
  }
  return value;
}

function positiveInteger(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) <= 0) {
    throw new Error(`${label} must be a positive integer`);
  }
  return value as number;
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function portableJson(value: unknown, label: string): void {
  const rendered = JSON.stringify(value);
  if (
    !rendered ||
    /(?:file:|data:|\/Users\/|\/private\/tmp\/|\/var\/folders\/)/i.test(rendered) ||
    /\b(?:OPENROUTER_API_KEY|FAL_KEY)\b/.test(rendered)
  ) {
    throw new Error(`${label} contains a non-portable or sensitive value`);
  }
}

async function readRegularWithin(
  root: string,
  relativePath: string,
  label: string,
  maximumBytes: number,
): Promise<Buffer> {
  const absoluteRoot = path.resolve(root);
  const target = path.resolve(absoluteRoot, ...relativePath.split("/"));
  if (!target.startsWith(`${absoluteRoot}${path.sep}`)) {
    throw new Error(`${label} escapes its root`);
  }
  let rootReal: string;
  let stat: Stats;
  try {
    [rootReal, stat] = await Promise.all([fs.realpath(absoluteRoot), fs.lstat(target)]);
  } catch {
    throw new Error(`${label} must be a bounded non-symlink regular file`);
  }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0 || stat.size > maximumBytes) {
    throw new Error(`${label} must be a bounded non-symlink regular file`);
  }
  let real: string;
  try {
    real = await fs.realpath(target);
  } catch {
    throw new Error(`${label} must be a bounded non-symlink regular file`);
  }
  if (!real.startsWith(`${rootReal}${path.sep}`)) throw new Error(`${label} escapes its root`);
  return await fs.readFile(target);
}

function exactPair(value: unknown, width: number, height: number, label: string): void {
  const pair = record(value, label);
  if (pair.width !== width || pair.height !== height) {
    throw new Error(`${label} does not match the gameplay asset contract`);
  }
}

function validateGridPixels(
  decoded: ReturnType<typeof PNG.sync.read>,
  contract: GameplayModelAssetContract,
  cellGutterPixels: number,
): void {
  let transparent = 0;
  let painted = 0;
  let nonOpaque = 0;
  for (let offset = 3; offset < decoded.data.byteLength; offset += 4) {
    if (decoded.data[offset] === 0) transparent += 1;
    else painted += 1;
    if (decoded.data[offset] !== 255) nonOpaque += 1;
  }
  if (contract.alphaExpectation === "opaque" && nonOpaque !== 0) {
    throw new Error(`${contract.id} must be fully opaque`);
  }
  if (contract.alphaExpectation === "transparent" && (transparent === 0 || painted === 0)) {
    throw new Error(`${contract.id} must contain transparent and painted pixels`);
  }
  const cellWidth = contract.width / contract.columns;
  const cellHeight = contract.height / contract.rows;
  const hasCellGutters = cellGutterPixels > 0;
  for (let row = 0; row < contract.rows; row += 1) {
    for (let column = 0; column < contract.columns; column += 1) {
      let cellPainted = false;
      for (let y = row * cellHeight; y < (row + 1) * cellHeight; y += 1) {
        for (let x = column * cellWidth; x < (column + 1) * cellWidth; x += 1) {
          const alpha = decoded.data[(y * contract.width + x) * 4 + 3];
          const localX = x - column * cellWidth;
          const localY = y - row * cellHeight;
          const inGutter =
            hasCellGutters &&
            (localX < cellGutterPixels ||
              localX >= cellWidth - cellGutterPixels ||
              localY < cellGutterPixels ||
              localY >= cellHeight - cellGutterPixels);
          if (inGutter && alpha !== 0) {
            throw new Error(`${contract.id} cell gutters must be transparent`);
          }
          if (!inGutter && alpha !== 0) cellPainted = true;
        }
      }
      if (!cellPainted) throw new Error(`${contract.id} has an empty grid-cell interior`);
    }
  }
  if (contract.id === "tileset") {
    const fillRow = 3;
    const fillColumn = 0;
    for (
      let y = fillRow * cellHeight + cellGutterPixels;
      y < (fillRow + 1) * cellHeight - cellGutterPixels;
      y += 1
    ) {
      for (
        let x = fillColumn * cellWidth + cellGutterPixels;
        x < (fillColumn + 1) * cellWidth - cellGutterPixels;
        x += 1
      ) {
        if (decoded.data[(y * contract.width + x) * 4 + 3] !== 255) {
          throw new Error("tileset ground-fill cell interior must be fully opaque");
        }
      }
    }
  }
}

function decodeAndValidatePng(
  bytes: Buffer,
  contract: GameplayModelAssetContract,
  cellGutterPixels: number,
): void {
  let decoded: ReturnType<typeof PNG.sync.read>;
  try {
    decoded = PNG.sync.read(bytes, { checkCRC: true, skipRescale: false });
  } catch {
    throw new Error(`${contract.id} must be a complete decodable PNG`);
  }
  if (
    decoded.width !== contract.width ||
    decoded.height !== contract.height ||
    decoded.depth !== 8 ||
    !Buffer.isBuffer(decoded.data) ||
    decoded.data.byteLength !== contract.width * contract.height * 4
  ) {
    throw new Error(`${contract.id} has invalid dimensions, depth, or decoded bounds`);
  }
  validateGridPixels(decoded, contract, cellGutterPixels);
}

function assertExactIds(records: readonly JsonRecord[], label: string): Map<string, JsonRecord> {
  const byId = new Map<string, JsonRecord>();
  for (const item of records) {
    const id = stableText(item.id, `${label}.id`);
    if (byId.has(id)) throw new Error(`${label} contains a duplicate id`);
    byId.set(id, item);
  }
  const expected = GAMEPLAY_MODEL_ASSET_CONTRACTS.map((asset) => asset.id).sort();
  if (JSON.stringify([...byId.keys()].sort()) !== JSON.stringify(expected)) {
    throw new Error(`${label} must contain exactly the 18 gameplay asset ids`);
  }
  return byId;
}

function validateProducerAsset(
  value: JsonRecord,
  contract: GameplayModelAssetContract,
): number {
  if (safeRelative(value.path, `${contract.id}.path`) !== contract.path) {
    throw new Error(`${contract.id}.path does not match the fixed asset contract`);
  }
  if (value.runtimeSlot !== contract.runtimeSlot) {
    throw new Error(`${contract.id}.runtimeSlot does not match the runtime contract`);
  }
  exactPair(value.target, contract.width, contract.height, `${contract.id}.target`);
  const layout = record(value.layout, `${contract.id}.layout`);
  if (layout.rows !== contract.rows || layout.columns !== contract.columns) {
    throw new Error(`${contract.id}.layout does not match the runtime grid`);
  }
  if (value.alphaExpectation !== contract.alphaExpectation) {
    throw new Error(`${contract.id}.alphaExpectation does not match the runtime contract`);
  }
  stableText(value.prompt, `${contract.id}.prompt`);
  if (!Array.isArray(value.referenceAssetIds)) {
    throw new Error(`${contract.id}.referenceAssetIds must be an array`);
  }
  const referenceIds = new Set<string>();
  for (const reference of value.referenceAssetIds) {
    if (
      typeof reference !== "string" ||
      !GAMEPLAY_MODEL_ASSET_CONTRACTS.some((asset) => asset.id === reference)
    ) {
      throw new Error(`${contract.id} has an unknown reference asset id`);
    }
    if (reference === contract.id || referenceIds.has(reference)) {
      throw new Error(`${contract.id} has a duplicate or self reference`);
    }
    referenceIds.add(reference);
  }
  if (!value.parameters || typeof value.parameters !== "object" || Array.isArray(value.parameters)) {
    throw new Error(`${contract.id}.parameters must be an object`);
  }
  if (Object.keys(value.parameters).length === 0) {
    throw new Error(`${contract.id}.parameters must not be empty`);
  }
  portableJson(value.parameters, `${contract.id}.parameters`);
  const source = record(value.sourceOutput, `${contract.id}.sourceOutput`);
  const sourceFileName = stableText(source.fileName, `${contract.id}.sourceOutput.fileName`);
  if (sourceFileName.includes("/") || sourceFileName.includes("\\")) {
    throw new Error(`${contract.id}.sourceOutput.fileName must be a portable basename`);
  }
  digest(source.sha256, `${contract.id}.sourceOutput.sha256`);
  positiveInteger(source.width, `${contract.id}.sourceOutput.width`);
  positiveInteger(source.height, `${contract.id}.sourceOutput.height`);
  if (source.mimeType !== "image/png") throw new Error(`${contract.id} source must be PNG`);
  if (!value.postprocess || typeof value.postprocess !== "object" || Array.isArray(value.postprocess)) {
    throw new Error(`${contract.id}.postprocess must be an object`);
  }
  if (Object.keys(value.postprocess).length === 0) {
    throw new Error(`${contract.id}.postprocess must not be empty`);
  }
  const postprocess = value.postprocess as JsonRecord;
  portableJson(postprocess, `${contract.id}.postprocess`);
  if (contract.alphaExpectation === "transparent") {
    const backgroundRemoval = record(
      postprocess.backgroundRemoval,
      `${contract.id}.postprocess.backgroundRemoval`,
    );
    if (
      backgroundRemoval.provider !== FAL_BACKGROUND_REMOVAL_PROVIDER ||
      backgroundRemoval.model !== FAL_BACKGROUND_REMOVAL_MODEL ||
      backgroundRemoval.operation !== "remove-background"
    ) {
      throw new Error(
        `${contract.id}.postprocess.backgroundRemoval must identify the approved FAL BiRefNet operation`,
      );
    }
    digest(
      backgroundRemoval.provenanceSha256,
      `${contract.id}.postprocess.backgroundRemoval.provenanceSha256`,
    );
    positiveInteger(
      backgroundRemoval.attempts,
      `${contract.id}.postprocess.backgroundRemoval.attempts`,
    );
    const backgroundOutput = record(
      backgroundRemoval.output,
      `${contract.id}.postprocess.backgroundRemoval.output`,
    );
    digest(
      backgroundOutput.sha256,
      `${contract.id}.postprocess.backgroundRemoval.output.sha256`,
    );
    positiveInteger(
      backgroundOutput.bytes,
      `${contract.id}.postprocess.backgroundRemoval.output.bytes`,
    );
    positiveInteger(
      backgroundOutput.width,
      `${contract.id}.postprocess.backgroundRemoval.output.width`,
    );
    positiveInteger(
      backgroundOutput.height,
      `${contract.id}.postprocess.backgroundRemoval.output.height`,
    );
    if (backgroundOutput.mimeType !== "image/png") {
      throw new Error(`${contract.id} background-removal output must be PNG`);
    }
  }
  const declaresCellGutter = Object.hasOwn(postprocess, "cellGutterPixels");
  const supportsCellGutter =
    contract.alphaExpectation === "transparent" &&
    (contract.rows > 1 || contract.columns > 1);
  if (
    declaresCellGutter &&
    (!supportsCellGutter || postprocess.cellGutterPixels !== CELL_GUTTER_PIXELS)
  ) {
    throw new Error(
      `${contract.id}.postprocess.cellGutterPixels must be the exact 2-pixel atlas gutter`,
    );
  }
  if (REQUIRED_GUTTER_ASSET_IDS.has(contract.id) && !declaresCellGutter) {
    throw new Error(`${contract.id}.postprocess must declare cellGutterPixels: 2`);
  }
  const output = record(value.output, `${contract.id}.output`);
  digest(output.sha256, `${contract.id}.output.sha256`);
  exactPair(output, contract.width, contract.height, `${contract.id}.output`);
  if (output.mimeType !== "image/png") throw new Error(`${contract.id} output must be PNG`);
  if (value.reviewStatus !== "pending-independent-review") {
    throw new Error(`${contract.id} producer reviewStatus must remain pending-independent-review`);
  }
  return declaresCellGutter ? CELL_GUTTER_PIXELS : 0;
}

function validateApprovalAsset(
  value: JsonRecord,
  producer: JsonRecord,
  contract: GameplayModelAssetContract,
): void {
  if (safeRelative(value.path, `${contract.id}.approval.path`) !== contract.path) {
    throw new Error(`${contract.id} approval path does not match the fixed asset contract`);
  }
  const producerOutput = record(producer.output, `${contract.id}.output`);
  if (digest(value.sha256, `${contract.id}.approval.sha256`) !== producerOutput.sha256) {
    throw new Error(`${contract.id} approval digest does not match the producer output`);
  }
  positiveInteger(value.bytes, `${contract.id}.approval.bytes`);
  const visual = record(value.visualReview, `${contract.id}.visualReview`);
  if (visual.status !== "approved" || visual.result !== "pass" || visual.independent !== true) {
    throw new Error(`${contract.id} requires an independent passing visual approval`);
  }
  const attestation = stableText(visual.attestationId, `${contract.id}.visualReview.attestationId`);
  for (const field of ["reviewedBy", "authorityBasis", "reviewedAt", "attestedAt"] as const) {
    stableText(visual[field], `${contract.id}.visualReview.${field}`);
  }
  const rights = record(value.rights, `${contract.id}.rights`);
  if (rights.status !== "redistribution-approved" || !Array.isArray(rights.basis)) {
    throw new Error(`${contract.id} requires an explicit redistribution approval basis`);
  }
  const basis = rights.basis.map((item, index) =>
    stableText(item, `${contract.id}.rights.basis[${index}]`),
  );
  if (new Set(basis).size !== basis.length || !basis.includes(attestation)) {
    throw new Error(`${contract.id} rights basis must include its visual attestation`);
  }
}

function worldSpec(): object {
  return {
    terrain_seed: GAMEPLAY_MODEL_TERRAIN_SEED,
    world: {
      name: WORLD_NAME,
      one_liner: "A moonlit path through hand-painted overgrown ruins.",
      narrative: "Cross the ancient ruins, face their corrupted guardian, and reach the portal.",
    },
    mobs: [
      {
        tier_label: "training-0",
        body_plan: "single original creature",
        name: "Corrupted Stone Guardian",
        brief: "A one-hit guardian represented by the approved model-generated demo art.",
      },
    ],
    obstacles: [],
    items: Array.from({ length: 8 }, (_, index) => ({
      kind: `ruin-relic-${index}`,
      name: `Ruin Relic ${index}`,
      brief: "An original collectible from the moonlit ruins.",
    })),
    layers: [
      { id: "sky", title: "Sky", z_index: 0, parallax: 0, opaque: true, paint_region: "full canvas", description: "Approved opaque backdrop." },
      { id: "ridges", title: "Ridges", z_index: 10, parallax: 0.35, opaque: false, paint_region: "lower two thirds", description: "Approved transparent middle depth." },
      { id: "foreground", title: "Foreground", z_index: 20, parallax: 1.2, opaque: false, paint_region: "lower quarter", description: "Approved transparent foreground depth." },
    ],
  };
}

function jsonBytes(value: unknown): Buffer {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export type GameplayModelAdapterOptions = Readonly<{
  sourceRoot?: string;
}>;

/**
 * Promote independently approved model assets into an isolated runtime fixture.
 * This adapter performs no visual judgment and never rewrites approved PNG bytes.
 */
export async function generateApprovedModelGameplayFixture(
  outRoot: string,
  options: GameplayModelAdapterOptions = {},
): Promise<GameplayFixture> {
  if (!path.isAbsolute(outRoot) || outRoot.includes("\0")) {
    throw new Error("gameplay fixture output root must be an absolute path");
  }
  const requestedSourceRoot = options.sourceRoot ?? GAMEPLAY_DEMO_ROOT;
  if (!path.isAbsolute(requestedSourceRoot) || requestedSourceRoot.includes("\0")) {
    throw new Error("gameplay demo source root must be an absolute path");
  }
  const sourceRoot = path.resolve(requestedSourceRoot);
  let sourceStat: Stats;
  try {
    sourceStat = await fs.lstat(sourceRoot);
  } catch {
    throw new Error("gameplay demo source root must be a real directory");
  }
  if (!sourceStat.isDirectory() || sourceStat.isSymbolicLink()) {
    throw new Error("gameplay demo source root must be a real directory");
  }
  const assetManifestBytes = await readRegularWithin(
    sourceRoot,
    GAMEPLAY_DEMO_ASSET_MANIFEST,
    "gameplay asset manifest",
    MAX_MANIFEST_BYTES,
  );
  const approvalManifestBytes = await readRegularWithin(
    sourceRoot,
    GAMEPLAY_DEMO_APPROVAL_MANIFEST,
    "gameplay approval manifest",
    MAX_MANIFEST_BYTES,
  );
  let assetManifestValue: unknown;
  let approvalManifestValue: unknown;
  try {
    assetManifestValue = JSON.parse(assetManifestBytes.toString("utf8"));
    approvalManifestValue = JSON.parse(approvalManifestBytes.toString("utf8"));
  } catch {
    throw new Error("gameplay demo manifests must be valid UTF-8 JSON");
  }
  portableJson(assetManifestValue, "gameplay asset manifest");
  portableJson(approvalManifestValue, "gameplay approval manifest");
  const assetManifest = record(assetManifestValue, "gameplay asset manifest");
  const approvalManifest = record(approvalManifestValue, "gameplay approval manifest");
  if (assetManifest.schemaVersion !== 1 || approvalManifest.schemaVersion !== 1) {
    throw new Error("gameplay demo manifest schemaVersion must be 1");
  }
  const artDirection = record(assetManifest.artDirection, "artDirection");
  if (Object.keys(artDirection).length === 0) throw new Error("artDirection must not be empty");
  portableJson(artDirection, "artDirection");
  const generator = record(assetManifest.generator, "generator");
  if (
    generator.tool !== "image_gen.imagegen" ||
    generator.mode !== "built-in" ||
    generator.model !== "unavailable"
  ) {
    throw new Error("generator identity must match the built-in image generation contract");
  }
  const seed = record(generator.seed, "generator.seed");
  if (seed.available !== false || seed.value !== null) {
    throw new Error("generator seed must explicitly record provider unavailability");
  }
  stableText(seed.reason, "generator.seed.reason");
  if (!Array.isArray(assetManifest.assets) || !Array.isArray(approvalManifest.assets)) {
    throw new Error("gameplay demo manifests must contain asset arrays");
  }
  const producerById = assertExactIds(
    assetManifest.assets.map((item, index) => record(item, `assets[${index}]`)),
    "producer assets",
  );
  const approvalById = assertExactIds(
    approvalManifest.assets.map((item, index) => record(item, `assets[${index}]`)),
    "approval assets",
  );
  const sourceManifest = record(approvalManifest.sourceManifest, "sourceManifest");
  if (
    sourceManifest.path !== GAMEPLAY_DEMO_ASSET_MANIFEST ||
    sourceManifest.sha256 !== sha256(assetManifestBytes) ||
    sourceManifest.bytes !== assetManifestBytes.byteLength
  ) {
    throw new Error("approval manifest is not bound to the exact producer manifest");
  }
  const setReview = record(approvalManifest.setReview, "setReview");
  if (setReview.status !== "approved" || setReview.result !== "pass" || setReview.independent !== true) {
    throw new Error("gameplay demo requires an independent cohesive-set approval");
  }
  const setAttestation = stableText(setReview.attestationId, "setReview.attestationId");
  for (const field of ["reviewedBy", "authorityBasis", "reviewedAt", "attestedAt"] as const) {
    stableText(setReview[field], `setReview.${field}`);
  }

  const outputs = new Map<string, Buffer>();
  const sourceAssetHashes: Record<string, string> = {};
  for (const contract of GAMEPLAY_MODEL_ASSET_CONTRACTS) {
    const producer = producerById.get(contract.id)!;
    const approval = approvalById.get(contract.id)!;
    const cellGutterPixels = validateProducerAsset(producer, contract);
    validateApprovalAsset(approval, producer, contract);
    const rights = record(approval.rights, `${contract.id}.rights`);
    if (!(rights.basis as unknown[]).includes(setAttestation)) {
      throw new Error(`${contract.id} rights basis must include the cohesive-set attestation`);
    }
    const bytes = await readRegularWithin(
      sourceRoot,
      contract.path,
      `${contract.id} final PNG`,
      MAX_PNG_BYTES,
    );
    if (sha256(bytes) !== approval.sha256 || bytes.byteLength !== approval.bytes) {
      throw new Error(`${contract.id} bytes do not match their approved digest and size`);
    }
    decodeAndValidatePng(bytes, contract, cellGutterPixels);
    const runtimeName = contract.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG);
    outputs.set(runtimeName, bytes);
    sourceAssetHashes[contract.id] = sha256(bytes);
  }

  outputs.set(`world_spec_${GAMEPLAY_MODEL_TAG}.json`, jsonBytes(worldSpec()));
  outputs.set(
    "run.json",
    jsonBytes({
      schemaVersion: 2,
      ok: true,
      input: {
        recipe: "scrolling-preview",
        prompt: GAMEPLAY_MODEL_PROMPT,
        transparencyMode: GAMEPLAY_MODEL_TRANSPARENCY_MODE,
      },
    }),
  );
  const artifactHashes = Object.fromEntries(
    [...outputs.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([filename, bytes]) => [filename, sha256(bytes)]),
  );
  outputs.set(
    GAMEPLAY_FIXTURE_METADATA_FILE,
    jsonBytes({
      version: GAMEPLAY_AUTOMATION_VERSION,
      generator: "web/tests/gameplay/model-assets.ts",
      original: true,
      prompt: GAMEPLAY_MODEL_PROMPT,
      tag: GAMEPLAY_MODEL_TAG,
      transparencyMode: GAMEPLAY_MODEL_TRANSPARENCY_MODE,
      generationProvenance: {
        tool: generator.tool,
        mode: generator.mode,
        model: generator.model,
        seed,
      },
      transparencyProvenance: {
        mode: GAMEPLAY_MODEL_TRANSPARENCY_MODE,
        canonicalAlpha: true,
        provider: FAL_BACKGROUND_REMOVAL_PROVIDER,
        model: FAL_BACKGROUND_REMOVAL_MODEL,
        assetIds: GAMEPLAY_MODEL_TRANSPARENT_ASSET_IDS,
        sourceManifest: {
          path: "fixtures/gameplay-demo/asset-manifest.json",
          sha256: sha256(assetManifestBytes),
          bytes: assetManifestBytes.byteLength,
        },
        approvalManifest: {
          path: "fixtures/gameplay-demo/approval-manifest.json",
          sha256: sha256(approvalManifestBytes),
          bytes: approvalManifestBytes.byteLength,
        },
      },
      sourceManifest: {
        path: "fixtures/gameplay-demo/asset-manifest.json",
        sha256: sha256(assetManifestBytes),
        bytes: assetManifestBytes.byteLength,
      },
      approvalManifest: {
        path: "fixtures/gameplay-demo/approval-manifest.json",
        sha256: sha256(approvalManifestBytes),
        bytes: approvalManifestBytes.byteLength,
      },
      sourceAssetHashes,
      artifactHashes,
    }),
  );

  await fs.mkdir(outRoot, { recursive: true, mode: 0o700 });
  const outStat = await fs.lstat(outRoot);
  if (!outStat.isDirectory() || outStat.isSymbolicLink()) {
    throw new Error("gameplay fixture output root must be a real directory");
  }
  const runDir = path.join(outRoot, GAMEPLAY_MODEL_TAG);
  await fs.mkdir(runDir, { mode: 0o700 });
  for (const [filename, bytes] of [...outputs.entries()].sort(([left], [right]) =>
    left.localeCompare(right),
  )) {
    await fs.writeFile(path.join(runDir, filename), bytes, { flag: "wx", mode: 0o600 });
  }
  const fixtureDigest = sha256(
    Buffer.from(
      [...outputs.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([filename, bytes]) => `${filename}:${sha256(bytes)}\n`)
        .join(""),
      "utf8",
    ),
  );
  return Object.freeze({
    outRoot,
    runDir,
    tag: GAMEPLAY_MODEL_TAG,
    route: `/preview/${GAMEPLAY_MODEL_TAG}?automation=${GAMEPLAY_AUTOMATION_VERSION}`,
    files: Object.freeze([...outputs.keys()].sort()),
    digest: fixtureDigest,
  });
}
