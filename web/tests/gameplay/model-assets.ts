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
import { runtimeRoleOwnsScaleReference } from "../../lib/runtime/sprite-scale";

const GAMEPLAY_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(GAMEPLAY_DIR, "../../..");
export const GAMEPLAY_DEMO_ROOT = path.join(
  REPO_ROOT,
  "fixtures",
  "gameplay-demo",
);
export const GAMEPLAY_DEMO_ASSET_MANIFEST = "asset-manifest.json";
export const GAMEPLAY_DEMO_APPROVAL_MANIFEST = "approval-manifest.json";
const MAX_MANIFEST_BYTES = 1_000_000;
const MAX_PNG_BYTES = 20_000_000;
const CELL_GUTTER_PIXELS = 2;
const REQUIRED_GUTTER_ASSET_IDS = new Set([
  "tileset",
  "character-attack",
  "character-climb",
]);
const FAL_BACKGROUND_REMOVAL_PROVIDER = "fal";
const FAL_BACKGROUND_REMOVAL_MODEL = "fal-ai/birefnet/v2";
const WORLD_NAME = "Moonlit Overgrown Ruins";
const LADDER_REVIEW_REPORT_SHA256 =
  "a4aea48b569cd5d29d322ac8705177506c1910b6a9bceed4220ab9f8bf0397b8";
const LADDER_RUNTIME_WIDTH = 80;
const LADDER_RUNTIME_HEIGHT = 320;
const GAMEPLAY_DEMO_REPOSITORY_PREFIX = "fixtures/gameplay-demo/";
const CHARACTER_CLIMB_ID = "character-climb";
const CHARACTER_CLIMB_SHA256 =
  "782fcda99a7296ab746c21d05014214503d4af280541b1f115031cf4d70dc56e";
const CHARACTER_CLIMB_BYTES = 39_677;
const CHARACTER_CLIMB_GENERATION_PATH =
  "fixtures/gameplay-demo/sources/character-climb/generation.json";
const CHARACTER_CLIMB_GENERATION_SHA256 =
  "59504ed6731c851d3a3d87e91eaff139f1c7ecf7e4dee22cee1e2cf3f9d7b9bc";
const CHARACTER_CLIMB_GENERATION_BYTES = 14_947;
const CHARACTER_CLIMB_SOURCE_SHA256 =
  "2d2e67b3750a0d0f1fa315e9a23c8fd7af3c2b75c472fdd661f4dfe897b4dbd2";
const CHARACTER_CLIMB_EXTRACTION_PATH =
  "fixtures/gameplay-demo/sources/character-climb/character-climb-local-extracted.png.meta.json";
const CHARACTER_CLIMB_EXTRACTION_SHA256 =
  "c7887efbf5cea15679137c8e70a73665c273376fc7781dc1507fcfe41da0018a";
const CHARACTER_CLIMB_EXTRACTION_BYTES = 1_840;
const CHARACTER_CLIMB_EXTRACTED_SHA256 =
  "4e23bc7690662429c2d52c88d90020c3dd5176f0e18b047d88a59d60a3040df5";
const CHARACTER_CLIMB_EXTRACTED_BYTES = 830_149;
const CHARACTER_CLIMB_REVIEW_PATH =
  "fixtures/gameplay-demo/sources/character-climb/visual-review.md";
const CHARACTER_CLIMB_REVIEW_SHA256 =
  "b0e492daa55778ac99ae5b8ef5fec114455bf74e0240bb5b4f9557eacbab7c05";
const CHARACTER_CLIMB_REVIEW_BYTES = 752;

export const GAMEPLAY_MODEL_PROMPT =
  "moonlit overgrown ruins model-generated gameplay showcase";
export const GAMEPLAY_MODEL_TRANSPARENCY_MODE = "ai" as const;
export const GAMEPLAY_MODEL_TAG =
  "moonlit-overgrown-ruins-model-generated-346cf767-ai";
export const GAMEPLAY_MODEL_TERRAIN_SEED = 1_235_206_006;
export const GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS =
  gameplayRequiredAssetKeys(WORLD_NAME);

type AlphaExpectation = "opaque" | "transparent";

const RUNTIME_SLOTS: Readonly<Record<string, string>> = {
  concept: "concept_<tag>.png",
  "layer-sky": "layer_<tag>_sky.png",
  "layer-ridges": "layer_<tag>_ridges.png",
  "layer-foreground": "layer_<tag>_foreground.png",
  tileset: "tileset_<tag>.png",
  ladder: "ladder_<tag>.png",
  "character-concept": "character_concept_<tag>.png",
  "character-idle": "character_<tag>-fromcombined_idle.png",
  "character-walk": "character_<tag>-fromcombined_walk.png",
  "character-run": "character_<tag>-fromcombined_run.png",
  "character-jump": "character_<tag>-fromcombined_jump.png",
  "character-climb": "character_<tag>-fromcombined_climb.png",
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
  {
    id: "concept",
    width: 1280,
    height: 720,
    rows: 1,
    columns: 1,
    alphaExpectation: "opaque",
  },
  {
    id: "layer-sky",
    width: 1280,
    height: 720,
    rows: 1,
    columns: 1,
    alphaExpectation: "opaque",
  },
  {
    id: "layer-ridges",
    width: 1280,
    height: 720,
    rows: 1,
    columns: 1,
    alphaExpectation: "transparent",
  },
  {
    id: "layer-foreground",
    width: 1280,
    height: 720,
    rows: 1,
    columns: 1,
    alphaExpectation: "transparent",
  },
  {
    id: "tileset",
    width: 384,
    height: 128,
    rows: 4,
    columns: 12,
    alphaExpectation: "transparent",
  },
  {
    id: "ladder",
    width: 256,
    height: 1024,
    rows: 1,
    columns: 1,
    alphaExpectation: "transparent",
  },
  {
    id: "character-concept",
    width: 128,
    height: 192,
    rows: 1,
    columns: 1,
    alphaExpectation: "transparent",
  },
  {
    id: "character-idle",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "character-walk",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "character-run",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "character-jump",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "character-crawl",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "character-attack",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "mob-concept",
    width: 128,
    height: 128,
    rows: 1,
    columns: 1,
    alphaExpectation: "transparent",
  },
  {
    id: "mob-idle",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "mob-hurt",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "items",
    width: 256,
    height: 128,
    rows: 2,
    columns: 4,
    alphaExpectation: "transparent",
  },
  {
    id: "inventory",
    width: 512,
    height: 320,
    rows: 1,
    columns: 1,
    alphaExpectation: "transparent",
  },
  {
    id: "portal",
    width: 256,
    height: 192,
    rows: 1,
    columns: 2,
    alphaExpectation: "transparent",
  },
  {
    id: "character-climb",
    width: 256,
    height: 128,
    rows: 1,
    columns: 4,
    alphaExpectation: "transparent",
  },
];

export const GAMEPLAY_MODEL_ASSET_CONTRACTS: readonly GameplayModelAssetContract[] =
  Object.freeze(
    GAMEPLAY_MODEL_ASSET_SHAPES.map((asset) => {
      return Object.freeze({
        ...asset,
        path: `${asset.id}.png`,
        runtimeSlot: RUNTIME_SLOTS[asset.id],
      });
    }),
  );

const GAMEPLAY_MODEL_TRANSPARENT_ASSET_IDS = Object.freeze(
  GAMEPLAY_MODEL_ASSET_CONTRACTS.filter(
    (asset) => asset.alphaExpectation === "transparent",
  )
    .map((asset) => asset.id)
    .sort(),
);

export const GAMEPLAY_MODEL_FIXTURE_FILES = Object.freeze(
  [
    ...GAMEPLAY_MODEL_ASSET_CONTRACTS.flatMap((asset) => {
      const filename = asset.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG);
      return [filename, `${filename}.meta.json`];
    }),
    `world_spec_${GAMEPLAY_MODEL_TAG}.json`,
    `world_spec_${GAMEPLAY_MODEL_TAG}.json.meta.json`,
    `manifest_${GAMEPLAY_MODEL_TAG}.json`,
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
    candidate
      .split("/")
      .some((part) => part === "" || part === "." || part === "..")
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
    /(?:file:|data:|\/Users\/|\/private\/tmp\/|\/var\/folders\/)/i.test(
      rendered,
    ) ||
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
    [rootReal, stat] = await Promise.all([
      fs.realpath(absoluteRoot),
      fs.lstat(target),
    ]);
  } catch {
    throw new Error(`${label} must be a bounded non-symlink regular file`);
  }
  if (
    !stat.isFile() ||
    stat.isSymbolicLink() ||
    stat.size <= 0 ||
    stat.size > maximumBytes
  ) {
    throw new Error(`${label} must be a bounded non-symlink regular file`);
  }
  let real: string;
  try {
    real = await fs.realpath(target);
  } catch {
    throw new Error(`${label} must be a bounded non-symlink regular file`);
  }
  if (!real.startsWith(`${rootReal}${path.sep}`))
    throw new Error(`${label} escapes its root`);
  return await fs.readFile(target);
}

function exactPair(
  value: unknown,
  width: number,
  height: number,
  label: string,
): void {
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
  if (
    contract.alphaExpectation === "transparent" &&
    (transparent === 0 || painted === 0)
  ) {
    throw new Error(
      `${contract.id} must contain transparent and painted pixels`,
    );
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
      if (!cellPainted)
        throw new Error(`${contract.id} has an empty grid-cell interior`);
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
          throw new Error(
            "tileset ground-fill cell interior must be fully opaque",
          );
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
    throw new Error(
      `${contract.id} has invalid dimensions, depth, or decoded bounds`,
    );
  }
  validateGridPixels(decoded, contract, cellGutterPixels);
}

function assertExactIds(
  records: readonly JsonRecord[],
  label: string,
): Map<string, JsonRecord> {
  const byId = new Map<string, JsonRecord>();
  for (const item of records) {
    const id = stableText(item.id, `${label}.id`);
    if (byId.has(id)) throw new Error(`${label} contains a duplicate id`);
    byId.set(id, item);
  }
  const expected = GAMEPLAY_MODEL_ASSET_CONTRACTS.map(
    (asset) => asset.id,
  ).sort();
  if (JSON.stringify([...byId.keys()].sort()) !== JSON.stringify(expected)) {
    throw new Error(
      `${label} must contain exactly the ${GAMEPLAY_MODEL_ASSET_CONTRACTS.length} gameplay asset ids`,
    );
  }
  return byId;
}

function validateCharacterClimbProducer(
  value: JsonRecord,
  postprocess: JsonRecord,
): void {
  const layout = record(value.layout, "character-climb.layout");
  if (layout.cellWidth !== 64 || layout.cellHeight !== 128) {
    throw new Error("character-climb must bind four exact 64x128 cells");
  }
  const parameters = record(value.parameters, "character-climb.parameters");
  const parameterProvenance = record(
    parameters.generationProvenance,
    "character-climb.parameters.generationProvenance",
  );
  const producerProvenance = record(
    postprocess.producerProvenance,
    "character-climb.postprocess.producerProvenance",
  );
  for (const [label, provenance] of [
    ["parameter", parameterProvenance],
    ["producer", producerProvenance],
  ] as const) {
    if (
      safeRelative(provenance.path, `character-climb.${label}.path`) !==
        CHARACTER_CLIMB_GENERATION_PATH ||
      digest(provenance.sha256, `character-climb.${label}.sha256`) !==
        CHARACTER_CLIMB_GENERATION_SHA256 ||
      provenance.bytes !== CHARACTER_CLIMB_GENERATION_BYTES ||
      provenance.attempts !== 5 ||
      provenance.selectedAttempt !== 2
    ) {
      throw new Error(
        "character-climb must bind its exact five-attempt ImageGen provenance",
      );
    }
  }
  if (
    producerProvenance.tool !== "image_gen.imagegen" ||
    producerProvenance.mode !== "built-in"
  ) {
    throw new Error("character-climb producer provenance must identify ImageGen");
  }
  const source = record(value.sourceOutput, "character-climb.sourceOutput");
  if (source.sha256 !== CHARACTER_CLIMB_SOURCE_SHA256) {
    throw new Error("character-climb must bind the selected ImageGen source");
  }
  const extraction = record(
    postprocess.backgroundExtraction,
    "character-climb.postprocess.backgroundExtraction",
  );
  const extractedOutput = record(
    extraction.output,
    "character-climb.postprocess.backgroundExtraction.output",
  );
  if (
    extraction.tool !== "Pillow" ||
    extraction.operation !==
      "local-checkerboard-to-alpha-and-edge-decontamination" ||
    extraction.inputSha256 !== CHARACTER_CLIMB_SOURCE_SHA256 ||
    safeRelative(
      extraction.provenancePath,
      "character-climb.postprocess.backgroundExtraction.provenancePath",
    ) !== CHARACTER_CLIMB_EXTRACTION_PATH ||
    extraction.provenanceSha256 !== CHARACTER_CLIMB_EXTRACTION_SHA256 ||
    extraction.provenanceBytes !== CHARACTER_CLIMB_EXTRACTION_BYTES ||
    extraction.externalUploadPerformed !== false ||
    extractedOutput.sha256 !== CHARACTER_CLIMB_EXTRACTED_SHA256 ||
    extractedOutput.bytes !== CHARACTER_CLIMB_EXTRACTED_BYTES ||
    extractedOutput.width !== 1774 ||
    extractedOutput.height !== 887 ||
    extractedOutput.mimeType !== "image/png"
  ) {
    throw new Error(
      "character-climb must bind its exact local alpha-extraction provenance",
    );
  }
  const normalization = record(
    postprocess.normalization,
    "character-climb.postprocess.normalization",
  );
  if (
    normalization.sourceSha256 !== CHARACTER_CLIMB_EXTRACTED_SHA256 ||
    normalization.transparentGutterPixelsPerCellEdge !== CELL_GUTTER_PIXELS
  ) {
    throw new Error(
      "character-climb normalization must bind the extracted source and 2-pixel gutters",
    );
  }
  const output = record(value.output, "character-climb.output");
  if (
    output.sha256 !== CHARACTER_CLIMB_SHA256 ||
    output.bytes !== CHARACTER_CLIMB_BYTES
  ) {
    throw new Error("character-climb must bind the exact approved PNG bytes");
  }
}

function validateProducerAsset(
  value: JsonRecord,
  contract: GameplayModelAssetContract,
): number {
  if (safeRelative(value.path, `${contract.id}.path`) !== contract.path) {
    throw new Error(
      `${contract.id}.path does not match the fixed asset contract`,
    );
  }
  if (value.runtimeSlot !== contract.runtimeSlot) {
    throw new Error(
      `${contract.id}.runtimeSlot does not match the runtime contract`,
    );
  }
  exactPair(
    value.target,
    contract.width,
    contract.height,
    `${contract.id}.target`,
  );
  const layout = record(value.layout, `${contract.id}.layout`);
  if (layout.rows !== contract.rows || layout.columns !== contract.columns) {
    throw new Error(`${contract.id}.layout does not match the runtime grid`);
  }
  if (value.alphaExpectation !== contract.alphaExpectation) {
    throw new Error(
      `${contract.id}.alphaExpectation does not match the runtime contract`,
    );
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
  if (
    !value.parameters ||
    typeof value.parameters !== "object" ||
    Array.isArray(value.parameters)
  ) {
    throw new Error(`${contract.id}.parameters must be an object`);
  }
  if (Object.keys(value.parameters).length === 0) {
    throw new Error(`${contract.id}.parameters must not be empty`);
  }
  portableJson(value.parameters, `${contract.id}.parameters`);
  const source = record(value.sourceOutput, `${contract.id}.sourceOutput`);
  const sourceFileName = stableText(
    source.fileName,
    `${contract.id}.sourceOutput.fileName`,
  );
  if (sourceFileName.includes("/") || sourceFileName.includes("\\")) {
    throw new Error(
      `${contract.id}.sourceOutput.fileName must be a portable basename`,
    );
  }
  digest(source.sha256, `${contract.id}.sourceOutput.sha256`);
  positiveInteger(source.width, `${contract.id}.sourceOutput.width`);
  positiveInteger(source.height, `${contract.id}.sourceOutput.height`);
  if (source.mimeType !== "image/png")
    throw new Error(`${contract.id} source must be PNG`);
  if (
    !value.postprocess ||
    typeof value.postprocess !== "object" ||
    Array.isArray(value.postprocess)
  ) {
    throw new Error(`${contract.id}.postprocess must be an object`);
  }
  if (Object.keys(value.postprocess).length === 0) {
    throw new Error(`${contract.id}.postprocess must not be empty`);
  }
  const postprocess = value.postprocess as JsonRecord;
  portableJson(postprocess, `${contract.id}.postprocess`);
  if (contract.alphaExpectation === "transparent") {
    if (contract.id === CHARACTER_CLIMB_ID) {
      validateCharacterClimbProducer(value, postprocess);
    } else {
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
    throw new Error(
      `${contract.id}.postprocess must declare cellGutterPixels: 2`,
    );
  }
  const output = record(value.output, `${contract.id}.output`);
  digest(output.sha256, `${contract.id}.output.sha256`);
  exactPair(output, contract.width, contract.height, `${contract.id}.output`);
  if (output.mimeType !== "image/png")
    throw new Error(`${contract.id} output must be PNG`);
  if (value.reviewStatus !== "pending-independent-review") {
    throw new Error(
      `${contract.id} producer reviewStatus must remain pending-independent-review`,
    );
  }
  return declaresCellGutter ? CELL_GUTTER_PIXELS : 0;
}

function validateApprovalAsset(
  value: JsonRecord,
  producer: JsonRecord,
  contract: GameplayModelAssetContract,
  setAttestation: string,
  sourceManifest: JsonRecord,
): void {
  if (
    safeRelative(value.path, `${contract.id}.approval.path`) !== contract.path
  ) {
    throw new Error(
      `${contract.id} approval path does not match the fixed asset contract`,
    );
  }
  const producerOutput = record(producer.output, `${contract.id}.output`);
  if (
    digest(value.sha256, `${contract.id}.approval.sha256`) !==
    producerOutput.sha256
  ) {
    throw new Error(
      `${contract.id} approval digest does not match the producer output`,
    );
  }
  positiveInteger(value.bytes, `${contract.id}.approval.bytes`);
  const visual = record(value.visualReview, `${contract.id}.visualReview`);
  if (
    visual.status !== "approved" ||
    visual.result !== "pass" ||
    visual.independent !== true
  ) {
    throw new Error(
      `${contract.id} requires an independent passing visual approval`,
    );
  }
  const attestation = stableText(
    visual.attestationId,
    `${contract.id}.visualReview.attestationId`,
  );
  for (const field of [
    "reviewedBy",
    "authorityBasis",
    "reviewedAt",
    "attestedAt",
  ] as const) {
    stableText(visual[field], `${contract.id}.visualReview.${field}`);
  }
  const rights = record(value.rights, `${contract.id}.rights`);
  if (
    rights.status !== "redistribution-approved" ||
    !Array.isArray(rights.basis)
  ) {
    throw new Error(
      `${contract.id} requires an explicit redistribution approval basis`,
    );
  }
  const basis = rights.basis.map((item, index) =>
    stableText(item, `${contract.id}.rights.basis[${index}]`),
  );
  if (new Set(basis).size !== basis.length || !basis.includes(attestation)) {
    throw new Error(
      `${contract.id} rights basis must include its visual attestation`,
    );
  }
  if (contract.id === "ladder") {
    validateLadderApproval(
      value,
      producer,
      contract,
      visual,
      attestation,
      setAttestation,
    );
  }
  if (contract.id === CHARACTER_CLIMB_ID) {
    validateCharacterClimbApproval(
      value,
      producer,
      contract,
      visual,
      attestation,
      setAttestation,
      sourceManifest,
    );
  }
}

function validateLadderApproval(
  value: JsonRecord,
  producer: JsonRecord,
  contract: GameplayModelAssetContract,
  visual: JsonRecord,
  attestation: string,
  setAttestation: string,
): void {
  exactPair(
    value.dimensions,
    contract.width,
    contract.height,
    "ladder.approval.dimensions",
  );
  if (value.alphaExpectation !== "transparent") {
    throw new Error("ladder approval must bind the transparent-alpha contract");
  }
  const style = record(value.styleReview, "ladder.styleReview");
  if (
    style.status !== "approved" ||
    style.result !== "pass" ||
    style.independent !== true ||
    style.artDirection !== WORLD_NAME ||
    style.cohesiveWithApprovedSet !== true ||
    JSON.stringify(style.referenceAssetIds) !==
      JSON.stringify(["tileset", "concept"])
  ) {
    throw new Error("ladder requires an independent cohesive style approval");
  }
  const runtime = record(value.runtimeScaleReview, "ladder.runtimeScaleReview");
  if (runtime.status !== "approved" || runtime.result !== "pass") {
    throw new Error("ladder runtime scale must be explicitly approved");
  }
  exactPair(
    runtime.source,
    contract.width,
    contract.height,
    "ladder.runtimeScaleReview.source",
  );
  exactPair(
    runtime.display,
    LADDER_RUNTIME_WIDTH,
    LADDER_RUNTIME_HEIGHT,
    "ladder.runtimeScaleReview.display",
  );
  if (runtime.uniformScale !== LADDER_RUNTIME_WIDTH / contract.width) {
    throw new Error(
      "ladder runtime scale must preserve the approved aspect ratio",
    );
  }
  const report = record(visual.report, "ladder.visualReview.report");
  if (
    report.recordId !== "stage-gen-ladder-visual-review" ||
    digest(report.sha256, "ladder.visualReview.report.sha256") !==
      LADDER_REVIEW_REPORT_SHA256
  ) {
    throw new Error(
      "ladder approval must bind the exact independent visual report",
    );
  }
  positiveInteger(report.bytes, "ladder.visualReview.report.bytes");
  const provenance = record(value.provenance, "ladder.provenance");
  const producerManifest = record(
    provenance.producerManifest,
    "ladder.provenance.producerManifest",
  );
  if (
    safeRelative(
      producerManifest.path,
      "ladder.provenance.producerManifest.path",
    ) !== GAMEPLAY_DEMO_ASSET_MANIFEST ||
    digest(
      producerManifest.sha256,
      "ladder.provenance.producerManifest.sha256",
    ).length !== 64 ||
    positiveInteger(
      producerManifest.bytes,
      "ladder.provenance.producerManifest.bytes",
    ) < 1 ||
    provenance.producerAssetId !== "ladder"
  ) {
    throw new Error(
      "ladder provenance must bind its historical producer manifest and asset",
    );
  }
  const producerPostprocess = record(
    producer.postprocess,
    "ladder.postprocess",
  );
  const producerRecord = record(
    producerPostprocess.producerProvenance,
    "ladder.postprocess.producerProvenance",
  );
  const generation = record(
    provenance.generationRecord,
    "ladder.provenance.generationRecord",
  );
  if (
    safeRelative(generation.path, "ladder.provenance.generationRecord.path") !==
      producerRecord.path ||
    digest(generation.sha256, "ladder.provenance.generationRecord.sha256") !==
      producerRecord.sha256
  ) {
    throw new Error("ladder approval must bind its exact generation record");
  }
  positiveInteger(generation.bytes, "ladder.provenance.generationRecord.bytes");
  const backgroundRemoval = record(
    producerPostprocess.backgroundRemoval,
    "ladder.postprocess.backgroundRemoval",
  );
  if (
    digest(
      provenance.backgroundRemovalProvenanceSha256,
      "ladder.provenance.backgroundRemovalProvenanceSha256",
    ) !== backgroundRemoval.provenanceSha256
  ) {
    throw new Error("ladder approval must bind background-removal provenance");
  }
  const cohesiveSet = record(value.cohesiveSet, "ladder.cohesiveSet");
  if (
    cohesiveSet.member !== true ||
    cohesiveSet.setAttestationId !== setAttestation ||
    cohesiveSet.extensionAttestationId !== attestation
  ) {
    throw new Error("ladder approval must bind its cohesive-set membership");
  }
}

function validateCharacterClimbApproval(
  value: JsonRecord,
  producer: JsonRecord,
  contract: GameplayModelAssetContract,
  visual: JsonRecord,
  attestation: string,
  setAttestation: string,
  sourceManifest: JsonRecord,
): void {
  exactPair(
    value.dimensions,
    contract.width,
    contract.height,
    "character-climb.approval.dimensions",
  );
  if (value.alphaExpectation !== "transparent") {
    throw new Error(
      "character-climb approval must bind the transparent-alpha contract",
    );
  }
  const layout = record(value.layout, "character-climb.approval.layout");
  if (
    layout.rows !== 1 ||
    layout.columns !== 4 ||
    layout.cellWidth !== 64 ||
    layout.cellHeight !== 128 ||
    layout.transparentGutterPixelsPerCellEdge !== CELL_GUTTER_PIXELS
  ) {
    throw new Error(
      "character-climb approval must bind four 64x128 cells with 2-pixel gutters",
    );
  }
  const style = record(value.styleReview, "character-climb.styleReview");
  if (
    style.status !== "approved" ||
    style.result !== "pass" ||
    style.independent !== true ||
    style.artDirection !== WORLD_NAME ||
    style.cohesiveWithApprovedSet !== true ||
    JSON.stringify(style.referenceAssetIds) !==
      JSON.stringify([
        "character-concept",
        "character-idle",
        "character-jump",
        "ladder",
      ])
  ) {
    throw new Error(
      "character-climb requires an independent cohesive style approval",
    );
  }
  const runtime = record(value.runtimeOutput, "character-climb.runtimeOutput");
  const frame = record(runtime.frame, "character-climb.runtimeOutput.frame");
  if (
    runtime.slot !== contract.runtimeSlot ||
    runtime.textureKey !== "character_climb" ||
    frame.width !== 64 ||
    frame.height !== 128 ||
    frame.count !== 4
  ) {
    throw new Error(
      "character-climb approval must bind the exact runtime output and frame contract",
    );
  }
  const report = record(visual.report, "character-climb.visualReview.report");
  if (
    report.recordId !== "stage-gen-character-climb-visual-review" ||
    safeRelative(report.path, "character-climb.visualReview.report.path") !==
      CHARACTER_CLIMB_REVIEW_PATH ||
    digest(report.sha256, "character-climb.visualReview.report.sha256") !==
      CHARACTER_CLIMB_REVIEW_SHA256 ||
    report.bytes !== CHARACTER_CLIMB_REVIEW_BYTES
  ) {
    throw new Error(
      "character-climb approval must bind the exact independent visual report",
    );
  }
  const provenance = record(value.provenance, "character-climb.provenance");
  const producerManifest = record(
    provenance.producerManifest,
    "character-climb.provenance.producerManifest",
  );
  if (
    producerManifest.path !== sourceManifest.path ||
    producerManifest.sha256 !== sourceManifest.sha256 ||
    producerManifest.bytes !== sourceManifest.bytes ||
    provenance.producerAssetId !== CHARACTER_CLIMB_ID
  ) {
    throw new Error(
      "character-climb provenance must bind the exact current producer manifest and asset",
    );
  }
  const producerPostprocess = record(
    producer.postprocess,
    "character-climb.postprocess",
  );
  const producerGeneration = record(
    producerPostprocess.producerProvenance,
    "character-climb.postprocess.producerProvenance",
  );
  const generation = record(
    provenance.generationRecord,
    "character-climb.provenance.generationRecord",
  );
  if (
    generation.path !== producerGeneration.path ||
    generation.sha256 !== producerGeneration.sha256 ||
    generation.bytes !== producerGeneration.bytes ||
    generation.attempts !== 5 ||
    generation.selectedAttempt !== 2
  ) {
    throw new Error(
      "character-climb approval must bind its five-attempt generation record",
    );
  }
  const producerExtraction = record(
    producerPostprocess.backgroundExtraction,
    "character-climb.postprocess.backgroundExtraction",
  );
  const extraction = record(
    provenance.localExtractionRecord,
    "character-climb.provenance.localExtractionRecord",
  );
  if (
    extraction.path !== producerExtraction.provenancePath ||
    extraction.sha256 !== producerExtraction.provenanceSha256 ||
    extraction.bytes !== producerExtraction.provenanceBytes ||
    extraction.outputSha256 !== CHARACTER_CLIMB_EXTRACTED_SHA256 ||
    extraction.externalUploadPerformed !== false
  ) {
    throw new Error(
      "character-climb approval must bind the exact local extraction record",
    );
  }
  const cohesiveSet = record(value.cohesiveSet, "character-climb.cohesiveSet");
  if (
    cohesiveSet.member !== true ||
    cohesiveSet.setAttestationId !== setAttestation ||
    cohesiveSet.extensionAttestationId !== attestation
  ) {
    throw new Error(
      "character-climb approval must bind its cohesive-set membership",
    );
  }
}

function worldSpec(): object {
  return {
    terrain_seed: GAMEPLAY_MODEL_TERRAIN_SEED,
    world: {
      name: WORLD_NAME,
      one_liner: "A moonlit path through hand-painted overgrown ruins.",
      narrative:
        "Cross the ancient ruins, face their corrupted guardian, and reach the portal.",
    },
    mobs: [
      {
        tier_label: "training-0",
        body_plan: "single original creature",
        name: "Corrupted Stone Guardian",
        brief:
          "A one-hit guardian represented by the approved model-generated demo art.",
      },
    ],
    obstacles: [],
    items: Array.from({ length: 8 }, (_, index) => ({
      kind: `ruin-relic-${index}`,
      name: `Ruin Relic ${index}`,
      brief: "An original collectible from the moonlit ruins.",
    })),
    layers: [
      {
        id: "sky",
        title: "Sky",
        z_index: 0,
        parallax: 0,
        opaque: true,
        paint_region: "full canvas",
        description: "Approved opaque backdrop.",
      },
      {
        id: "ridges",
        title: "Ridges",
        z_index: 10,
        parallax: 0.35,
        opaque: false,
        paint_region: "lower two thirds",
        description: "Approved transparent middle depth.",
      },
      {
        id: "foreground",
        title: "Foreground",
        z_index: 20,
        parallax: 1.8,
        opaque: false,
        paint_region: "lower quarter",
        description: "Approved transparent foreground depth.",
      },
    ],
  };
}

function jsonBytes(value: unknown): Buffer {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function localArtifactProvenance(
  artifact: Buffer,
  mediaType: string,
  prompt: string,
): Buffer {
  return jsonBytes({
    schema_version: 2,
    provider: "local",
    model: "approved-gameplay-fixture-adapter",
    seed: null,
    prompt,
    prompt_sha256: sha256(Buffer.from(prompt, "utf8")),
    references: [],
    refs: [],
    inputs: [],
    params: { stage: "approved-gameplay-fixture-adapter" },
    validation: { deterministic: true },
    component: { name: "@stage-gen/web", version: "0.0.0" },
    tool: { name: "gameplay-model-fixture-adapter", version: "1" },
    artifact: {
      sha256: sha256(artifact),
      bytes: artifact.byteLength,
      media_type: mediaType,
    },
    ts: "1970-01-01T00:00:00Z",
    attempts: 1,
    retries: 0,
  });
}

function modelRuntimeRole(assetId: string): string {
  if (assetId === "mob-concept") return "mob-concept-0";
  if (assetId === "mob-idle") return "mob-0-idle";
  if (assetId === "mob-hurt") return "mob-0-hurt";
  return assetId;
}

function modelScaleReference(
  cellWidth: number,
  cellHeight: number,
  frameIndex: number,
) {
  const top = 0.1;
  const bottom = 0.3;
  const left = 0.2;
  const right = 0.4;
  return {
    part: "head",
    top_fraction: top,
    bottom_fraction: bottom,
    left_fraction: left,
    right_fraction: right,
    extent_pixels:
      Math.round(
        Math.max(
          (bottom - top) * cellHeight,
          (right - left) * cellWidth,
        ) * 1_000,
      ) / 1_000,
    confident: true,
    evidence: "Deterministic approved-fixture actor bounds.",
    frame_index: frameIndex,
    cell_width: cellWidth,
    cell_height: cellHeight,
  };
}

function modelRuntimeAssets() {
  return GAMEPLAY_MODEL_ASSET_CONTRACTS.map((asset) => {
    const role = modelRuntimeRole(asset.id);
    const runtimePath = asset.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG);
    const cellWidth = asset.width / asset.columns;
    const cellHeight = asset.height / asset.rows;
    if (!Number.isSafeInteger(cellWidth) || !Number.isSafeInteger(cellHeight)) {
      throw new Error(`approved gameplay fixture layout is not integral for ${role}`);
    }
    return {
      id: role,
      runtime_slot: role,
      path: runtimePath,
      provenance_path: `${runtimePath}.meta.json`,
      alpha_expectation: asset.alphaExpectation,
      layout: {
        topology: asset.rows === 1 && asset.columns === 1 ? "single" : "grid",
        rows: asset.rows,
        columns: asset.columns,
        cell_width: cellWidth,
        cell_height: cellHeight,
        gutter: 0,
      },
      geometry_validation: {
        exact_dimensions: true,
        alpha_contract: true,
      },
      ...(runtimeRoleOwnsScaleReference(role)
        ? {
            scale_reference: modelScaleReference(
              cellWidth,
              cellHeight,
              role.endsWith("-attack") ? 1 : 0,
            ),
          }
        : {}),
    };
  });
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
  if (
    !path.isAbsolute(requestedSourceRoot) ||
    requestedSourceRoot.includes("\0")
  ) {
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
  const approvalManifest = record(
    approvalManifestValue,
    "gameplay approval manifest",
  );
  if (
    assetManifest.schemaVersion !== 1 ||
    approvalManifest.schemaVersion !== 1
  ) {
    throw new Error("gameplay demo manifest schemaVersion must be 1");
  }
  const artDirection = record(assetManifest.artDirection, "artDirection");
  if (Object.keys(artDirection).length === 0)
    throw new Error("artDirection must not be empty");
  portableJson(artDirection, "artDirection");
  const generator = record(assetManifest.generator, "generator");
  if (
    generator.tool !== "image_gen.imagegen" ||
    generator.mode !== "built-in" ||
    generator.model !== "unavailable"
  ) {
    throw new Error(
      "generator identity must match the built-in image generation contract",
    );
  }
  const seed = record(generator.seed, "generator.seed");
  if (seed.available !== false || seed.value !== null) {
    throw new Error(
      "generator seed must explicitly record provider unavailability",
    );
  }
  stableText(seed.reason, "generator.seed.reason");
  if (
    !Array.isArray(assetManifest.assets) ||
    !Array.isArray(approvalManifest.assets)
  ) {
    throw new Error("gameplay demo manifests must contain asset arrays");
  }
  const producerById = assertExactIds(
    assetManifest.assets.map((item, index) => record(item, `assets[${index}]`)),
    "producer assets",
  );
  const approvalById = assertExactIds(
    approvalManifest.assets.map((item, index) =>
      record(item, `assets[${index}]`),
    ),
    "approval assets",
  );
  const sourceManifest = record(
    approvalManifest.sourceManifest,
    "sourceManifest",
  );
  if (
    sourceManifest.path !== GAMEPLAY_DEMO_ASSET_MANIFEST ||
    sourceManifest.sha256 !== sha256(assetManifestBytes) ||
    sourceManifest.bytes !== assetManifestBytes.byteLength
  ) {
    throw new Error(
      "approval manifest is not bound to the exact producer manifest",
    );
  }
  const setReview = record(approvalManifest.setReview, "setReview");
  if (
    setReview.status !== "approved" ||
    setReview.result !== "pass" ||
    setReview.independent !== true
  ) {
    throw new Error(
      "gameplay demo requires an independent cohesive-set approval",
    );
  }
  const setAttestation = stableText(
    setReview.attestationId,
    "setReview.attestationId",
  );
  for (const field of [
    "reviewedBy",
    "authorityBasis",
    "reviewedAt",
    "attestedAt",
  ] as const) {
    stableText(setReview[field], `setReview.${field}`);
  }

  const outputs = new Map<string, Buffer>();
  const sourceAssetHashes: Record<string, string> = {};
  for (const contract of GAMEPLAY_MODEL_ASSET_CONTRACTS) {
    const producer = producerById.get(contract.id)!;
    const approval = approvalById.get(contract.id)!;
    const cellGutterPixels = validateProducerAsset(producer, contract);
    validateApprovalAsset(
      approval,
      producer,
      contract,
      setAttestation,
      sourceManifest,
    );
    const rights = record(approval.rights, `${contract.id}.rights`);
    if (!(rights.basis as unknown[]).includes(setAttestation)) {
      throw new Error(
        `${contract.id} rights basis must include the cohesive-set attestation`,
      );
    }
    const bytes = await readRegularWithin(
      sourceRoot,
      contract.path,
      `${contract.id} final PNG`,
      MAX_PNG_BYTES,
    );
    if (
      sha256(bytes) !== approval.sha256 ||
      bytes.byteLength !== approval.bytes
    ) {
      throw new Error(
        `${contract.id} bytes do not match their approved digest and size`,
      );
    }
    if (contract.id === "ladder") {
      const provenance = record(approval.provenance, "ladder.provenance");
      const generation = record(
        provenance.generationRecord,
        "ladder.provenance.generationRecord",
      );
      const generationPath = safeRelative(
        generation.path,
        "ladder.provenance.generationRecord.path",
      );
      if (!generationPath.startsWith(GAMEPLAY_DEMO_REPOSITORY_PREFIX)) {
        throw new Error(
          "ladder generation record must use the fixed repository fixture prefix",
        );
      }
      const generationBytes = await readRegularWithin(
        sourceRoot,
        generationPath.slice(GAMEPLAY_DEMO_REPOSITORY_PREFIX.length),
        "ladder generation record",
        MAX_MANIFEST_BYTES,
      );
      if (
        sha256(generationBytes) !== generation.sha256 ||
        generationBytes.byteLength !== generation.bytes
      ) {
        throw new Error(
          "ladder generation record does not match its approved provenance",
        );
      }
    }
    if (contract.id === CHARACTER_CLIMB_ID) {
      const provenance = record(
        approval.provenance,
        "character-climb.provenance",
      );
      const generation = record(
        provenance.generationRecord,
        "character-climb.provenance.generationRecord",
      );
      const extraction = record(
        provenance.localExtractionRecord,
        "character-climb.provenance.localExtractionRecord",
      );
      const visual = record(
        approval.visualReview,
        "character-climb.visualReview",
      );
      const report = record(
        visual.report,
        "character-climb.visualReview.report",
      );
      for (const [recordValue, label] of [
        [generation, "character-climb generation record"],
        [extraction, "character-climb extraction record"],
        [report, "character-climb visual review"],
      ] as const) {
        const recordPath = safeRelative(recordValue.path, `${label}.path`);
        if (!recordPath.startsWith(GAMEPLAY_DEMO_REPOSITORY_PREFIX)) {
          throw new Error(`${label} must use the fixed repository fixture prefix`);
        }
        const recordBytes = await readRegularWithin(
          sourceRoot,
          recordPath.slice(GAMEPLAY_DEMO_REPOSITORY_PREFIX.length),
          label,
          MAX_MANIFEST_BYTES,
        );
        if (
          sha256(recordBytes) !== recordValue.sha256 ||
          recordBytes.byteLength !== recordValue.bytes
        ) {
          throw new Error(`${label} does not match its approved provenance`);
        }
        if (recordValue === generation) {
          let generationValue: unknown;
          try {
            generationValue = JSON.parse(recordBytes.toString("utf8"));
          } catch {
            throw new Error("character-climb generation record must be JSON");
          }
          const generationRecord = record(
            generationValue,
            "character-climb generation record",
          );
          const generatorRecord = record(
            generationRecord.generator,
            "character-climb generation record.generator",
          );
          if (
            generatorRecord.tool !== "image_gen.imagegen" ||
            generatorRecord.mode !== "built-in" ||
            !Array.isArray(generationRecord.attempts) ||
            generationRecord.attempts.length !== 5
          ) {
            throw new Error(
              "character-climb generation record must contain five built-in ImageGen attempts",
            );
          }
          const attempts = generationRecord.attempts.map((attempt, index) =>
            record(attempt, `character-climb generation attempt ${index + 1}`),
          );
          if (
            attempts.some((attempt, index) => attempt.attempt !== index + 1) ||
            attempts.filter((attempt) => attempt.status === "selected")
              .length !== 1 ||
            attempts[1]?.status !== "selected"
          ) {
            throw new Error(
              "character-climb generation attempts must bind selected attempt 2",
            );
          }
        }
      }
    }
    decodeAndValidatePng(bytes, contract, cellGutterPixels);
    const runtimeName = contract.runtimeSlot.replace(
      "<tag>",
      GAMEPLAY_MODEL_TAG,
    );
    outputs.set(runtimeName, bytes);
    outputs.set(
      `${runtimeName}.meta.json`,
      localArtifactProvenance(
        bytes,
        "image/png",
        `adapt approved gameplay fixture ${contract.id}`,
      ),
    );
    sourceAssetHashes[contract.id] = sha256(bytes);
  }

  const worldSpecPath = `world_spec_${GAMEPLAY_MODEL_TAG}.json`;
  const worldSpecBytes = jsonBytes(worldSpec());
  outputs.set(worldSpecPath, worldSpecBytes);
  outputs.set(
    `${worldSpecPath}.meta.json`,
    localArtifactProvenance(
      worldSpecBytes,
      "application/json",
      "adapt approved gameplay fixture world spec",
    ),
  );
  // The current runtime requires the one v7 scrolling manifest and its complete measured actor
  // closure. The adapter publishes only current lower_snake_case fields.
  outputs.set(
    `manifest_${GAMEPLAY_MODEL_TAG}.json`,
    jsonBytes({
      schema_version: 7,
      recipe: "scrolling-preview",
      tag: GAMEPLAY_MODEL_TAG,
      transparency_mode: GAMEPLAY_MODEL_TRANSPARENCY_MODE,
      artifacts: [...outputs.keys()].sort(),
      canonical_artifacts: [],
      world_spec: {
        path: worldSpecPath,
        provenance_path: `${worldSpecPath}.meta.json`,
      },
      runtime_assets: modelRuntimeAssets(),
      image_repeat: { enabled: false, status: "deferred", artifacts: [] },
    }),
  );
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
        assetIds: GAMEPLAY_MODEL_TRANSPARENT_ASSET_IDS.filter(
          (assetId) => assetId !== CHARACTER_CLIMB_ID,
        ),
        localExtractionAssetIds: [CHARACTER_CLIMB_ID],
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
  for (const [filename, bytes] of [...outputs.entries()].sort(
    ([left], [right]) => left.localeCompare(right),
  )) {
    await fs.writeFile(path.join(runDir, filename), bytes, {
      flag: "wx",
      mode: 0o600,
    });
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
