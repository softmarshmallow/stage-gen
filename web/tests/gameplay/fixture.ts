import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { deflateSync } from "node:zlib";
import {
  GAMEPLAY_AUTOMATION_VERSION,
  GAMEPLAY_FIXTURE_METADATA_FILE,
  gameplayRequiredAssetKeys,
  type GameplayFixture,
} from "./contracts";
import { runtimeRoleOwnsScaleReference } from "../../lib/runtime/sprite-scale";
import {
  RECIPE_RUN_KIND,
  RECIPE_RUN_SCHEMA_VERSION,
} from "../../lib/shell/run-summary";

export {
  GAMEPLAY_AUTOMATION_VERSION,
  GAMEPLAY_FIXTURE_METADATA_FILE,
  type GameplayFixture,
} from "./contracts";

export const GAMEPLAY_PROMPT = "original deterministic gameplay showcase";
export const GAMEPLAY_TRANSPARENCY_MODE = "chroma" as const;
export const GAMEPLAY_TAG =
  "original-deterministic-gameplay-showcase-532c8ee7-chroma";

const WORLD_NAME = "Geometric Relay Range";

const LAYERS = Object.freeze([
  {
    id: "sky",
    title: "Geometric sky",
    z_index: 0,
    parallax: 0,
    opaque: true,
    paint_region: "full canvas",
    description: "Opaque geometric color bands.",
  },
  {
    id: "ridges",
    title: "Geometric ridges",
    z_index: 10,
    parallax: 0.35,
    opaque: false,
    paint_region: "lower two thirds",
    description: "Transparent rectangular ridges.",
  },
  {
    id: "foreground",
    title: "Geometric foreground",
    z_index: 20,
    parallax: 1.8,
    opaque: false,
    paint_region: "lower quarter",
    description: "Transparent foreground markers.",
  },
]);

export const GAMEPLAY_REQUIRED_ASSET_KEYS = gameplayRequiredAssetKeys(
  WORLD_NAME,
  { includePlayerHurt: true },
);

export const GAMEPLAY_PNG_DIMENSIONS = Object.freeze({
  [`concept_${GAMEPLAY_TAG}.png`]: [1280, 720],
  [`layer_${GAMEPLAY_TAG}_sky.png`]: [1280, 720],
  [`layer_${GAMEPLAY_TAG}_ridges.png`]: [1280, 720],
  [`layer_${GAMEPLAY_TAG}_foreground.png`]: [1280, 720],
  [`tileset_${GAMEPLAY_TAG}.png`]: [384, 128],
  [`ladder_${GAMEPLAY_TAG}.png`]: [128, 256],
  [`character_concept_${GAMEPLAY_TAG}.png`]: [128, 192],
  [`character_${GAMEPLAY_TAG}-fromcombined_idle.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}-fromcombined_walk.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}-fromcombined_run.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}-fromcombined_jump.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}-fromcombined_climb.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}-fromcombined_crawl.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}_attack.png`]: [256, 128],
  [`character_${GAMEPLAY_TAG}_hurt.png`]: [256, 128],
  [`mob_concept_${GAMEPLAY_TAG}_0.png`]: [128, 128],
  [`mob_${GAMEPLAY_TAG}_0_idle.png`]: [256, 128],
  [`mob_${GAMEPLAY_TAG}_0_hurt.png`]: [256, 128],
  [`items_${GAMEPLAY_TAG}.png`]: [256, 128],
  [`inventory_${GAMEPLAY_TAG}.png`]: [512, 320],
  [`portal_${GAMEPLAY_TAG}.png`]: [256, 192],
} satisfies Record<string, readonly [number, number]>);

export const GAMEPLAY_FIXTURE_FILES = Object.freeze([
  ...Object.keys(GAMEPLAY_PNG_DIMENSIONS).flatMap((filename) => [
    filename,
    `${filename}.meta.json`,
  ]),
  `world_spec_${GAMEPLAY_TAG}.json`,
  `world_spec_${GAMEPLAY_TAG}.json.meta.json`,
  `manifest_${GAMEPLAY_TAG}.json`,
  "run.json",
  GAMEPLAY_FIXTURE_METADATA_FILE,
].sort());

type FixtureRuntimeAsset = Readonly<{
  role: string;
  path: string;
  rows: number;
  columns: number;
  alphaExpectation: "opaque" | "transparent";
}>;

const GAMEPLAY_RUNTIME_ASSETS: readonly FixtureRuntimeAsset[] = Object.freeze([
  { role: "concept", path: `concept_${GAMEPLAY_TAG}.png`, rows: 1, columns: 1, alphaExpectation: "opaque" },
  { role: "layer-sky", path: `layer_${GAMEPLAY_TAG}_sky.png`, rows: 1, columns: 1, alphaExpectation: "opaque" },
  { role: "layer-ridges", path: `layer_${GAMEPLAY_TAG}_ridges.png`, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { role: "layer-foreground", path: `layer_${GAMEPLAY_TAG}_foreground.png`, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { role: "tileset", path: `tileset_${GAMEPLAY_TAG}.png`, rows: 4, columns: 12, alphaExpectation: "transparent" },
  { role: "ladder", path: `ladder_${GAMEPLAY_TAG}.png`, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { role: "character-concept", path: `character_concept_${GAMEPLAY_TAG}.png`, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { role: "character-idle", path: `character_${GAMEPLAY_TAG}-fromcombined_idle.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-walk", path: `character_${GAMEPLAY_TAG}-fromcombined_walk.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-run", path: `character_${GAMEPLAY_TAG}-fromcombined_run.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-jump", path: `character_${GAMEPLAY_TAG}-fromcombined_jump.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-crawl", path: `character_${GAMEPLAY_TAG}-fromcombined_crawl.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-climb", path: `character_${GAMEPLAY_TAG}-fromcombined_climb.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-attack", path: `character_${GAMEPLAY_TAG}_attack.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "character-hurt", path: `character_${GAMEPLAY_TAG}_hurt.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "mob-concept-0", path: `mob_concept_${GAMEPLAY_TAG}_0.png`, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { role: "mob-0-idle", path: `mob_${GAMEPLAY_TAG}_0_idle.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "mob-0-hurt", path: `mob_${GAMEPLAY_TAG}_0_hurt.png`, rows: 1, columns: 4, alphaExpectation: "transparent" },
  { role: "items", path: `items_${GAMEPLAY_TAG}.png`, rows: 2, columns: 4, alphaExpectation: "transparent" },
  { role: "inventory", path: `inventory_${GAMEPLAY_TAG}.png`, rows: 1, columns: 1, alphaExpectation: "transparent" },
  { role: "portal", path: `portal_${GAMEPLAY_TAG}.png`, rows: 1, columns: 2, alphaExpectation: "transparent" },
]);

type Rgba = readonly [number, number, number, number];
type Raster = { width: number; height: number; data: Uint8Array };

const COLORS = Object.freeze({
  navy: [15, 27, 52, 255] as Rgba,
  blue: [38, 90, 146, 255] as Rgba,
  cyan: [60, 190, 204, 255] as Rgba,
  green: [52, 154, 104, 255] as Rgba,
  amber: [239, 178, 67, 255] as Rgba,
  coral: [230, 92, 86, 255] as Rgba,
  violet: [135, 93, 181, 255] as Rgba,
  cream: [244, 231, 190, 255] as Rgba,
  clear: [0, 0, 0, 0] as Rgba,
});

function raster(width: number, height: number, fill: Rgba): Raster {
  const data = new Uint8Array(width * height * 4);
  for (let offset = 0; offset < data.length; offset += 4) {
    data[offset] = fill[0];
    data[offset + 1] = fill[1];
    data[offset + 2] = fill[2];
    data[offset + 3] = fill[3];
  }
  return { width, height, data };
}

function rect(
  image: Raster,
  x: number,
  y: number,
  width: number,
  height: number,
  color: Rgba,
): void {
  const left = Math.max(0, Math.floor(x));
  const top = Math.max(0, Math.floor(y));
  const right = Math.min(image.width, Math.ceil(x + width));
  const bottom = Math.min(image.height, Math.ceil(y + height));
  for (let py = top; py < bottom; py += 1) {
    for (let px = left; px < right; px += 1) {
      const offset = (py * image.width + px) * 4;
      image.data[offset] = color[0];
      image.data[offset + 1] = color[1];
      image.data[offset + 2] = color[2];
      image.data[offset + 3] = color[3];
    }
  }
}

function opaqueBackdrop(): Raster {
  const image = raster(1280, 720, COLORS.navy);
  rect(image, 0, 160, 1280, 560, COLORS.blue);
  rect(image, 0, 390, 1280, 330, COLORS.green);
  for (let x = 0; x < 1280; x += 160) {
    rect(image, x + 24, 96 + ((x / 160) % 3) * 22, 80, 80, COLORS.amber);
  }
  return image;
}

function transparentLayer(kind: "ridges" | "foreground"): Raster {
  const image = raster(1280, 720, COLORS.clear);
  const baseY = kind === "ridges" ? 340 : 570;
  const color = kind === "ridges" ? COLORS.violet : COLORS.cyan;
  const step = kind === "ridges" ? 128 : 96;
  for (let x = 0; x < 1280; x += step) {
    const rise = ((x / step) % 4) * 28;
    rect(image, x + 8, baseY - rise, step - 16, 720 - baseY + rise, color);
  }
  return image;
}

function tileset(): Raster {
  const image = raster(384, 128, COLORS.clear);
  const palette = [COLORS.green, COLORS.blue, COLORS.amber, COLORS.violet];
  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 12; col += 1) {
      const color = palette[(row + col) % palette.length];
      rect(image, col * 32, row * 32, 32, 32, color);
      rect(image, col * 32 + 4, row * 32 + 4, 24, 6, COLORS.cream);
    }
  }
  return image;
}

function conceptSprite(width: number, height: number, color: Rgba): Raster {
  const image = raster(width, height, COLORS.clear);
  rect(image, width * 0.3, height * 0.12, width * 0.4, height * 0.23, COLORS.cream);
  rect(image, width * 0.22, height * 0.34, width * 0.56, height * 0.5, color);
  rect(image, width * 0.12, height * 0.47, width * 0.76, height * 0.16, color);
  return image;
}

function frameStrip(color: Rgba, pose: number): Raster {
  const image = raster(256, 128, COLORS.clear);
  for (let frame = 0; frame < 4; frame += 1) {
    const x = frame * 64;
    const bob = (frame + pose) % 3;
    rect(image, x + 22, 14 + bob * 2, 20, 22, COLORS.cream);
    rect(image, x + 16, 36 + bob * 2, 32, 54, color);
    rect(image, x + 10 + ((frame + pose) % 2) * 5, 88, 18, 26, color);
    rect(image, x + 36 - ((frame + pose) % 2) * 5, 88, 18, 26, color);
  }
  return image;
}

function itemSheet(): Raster {
  const image = raster(256, 128, COLORS.clear);
  const palette = [
    COLORS.amber,
    COLORS.cyan,
    COLORS.coral,
    COLORS.violet,
    COLORS.green,
    COLORS.blue,
    COLORS.cream,
    COLORS.navy,
  ];
  for (let index = 0; index < 8; index += 1) {
    const col = index % 4;
    const row = Math.floor(index / 4);
    rect(image, col * 64 + 14, row * 64 + 14, 36, 36, palette[index]);
    rect(image, col * 64 + 25, row * 64 + 6, 14, 52, palette[index]);
  }
  return image;
}

function inventoryPanel(): Raster {
  const image = raster(512, 320, COLORS.clear);
  rect(image, 8, 8, 496, 304, COLORS.navy);
  rect(image, 20, 20, 472, 280, COLORS.blue);
  for (let row = 0; row < 2; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      rect(image, 36 + col * 112, 44 + row * 120, 88, 88, COLORS.cream);
      rect(image, 42 + col * 112, 50 + row * 120, 76, 76, COLORS.navy);
    }
  }
  return image;
}

function portalSheet(): Raster {
  const image = raster(256, 192, COLORS.clear);
  for (let half = 0; half < 2; half += 1) {
    const x = half * 128;
    const outer = half === 0 ? COLORS.cyan : COLORS.amber;
    rect(image, x + 22, 10, 84, 172, outer);
    rect(image, x + 38, 30, 52, 152, COLORS.violet);
    rect(image, x + 49, 46, 30, 136, COLORS.clear);
  }
  return image;
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let value = 0; value < 256; value += 1) {
    let crc = value;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc & 1) === 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
    }
    table[value] = crc >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Uint8Array): Buffer {
  const typeBytes = Buffer.from(type, "ascii");
  const chunk = Buffer.alloc(12 + data.length);
  chunk.writeUInt32BE(data.length, 0);
  typeBytes.copy(chunk, 4);
  Buffer.from(data).copy(chunk, 8);
  chunk.writeUInt32BE(crc32(chunk.subarray(4, 8 + data.length)), 8 + data.length);
  return chunk;
}

function encodePng(image: Raster): Buffer {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(image.width, 0);
  ihdr.writeUInt32BE(image.height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  const scanlines = Buffer.alloc(image.height * (image.width * 4 + 1));
  for (let y = 0; y < image.height; y += 1) {
    const destination = y * (image.width * 4 + 1);
    scanlines[destination] = 0;
    Buffer.from(image.data.buffer, image.data.byteOffset + y * image.width * 4, image.width * 4).copy(
      scanlines,
      destination + 1,
    );
  }
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(scanlines, { level: 9 })),
    pngChunk("IEND", new Uint8Array()),
  ]);
}

function worldSpec(): object {
  return {
    world: {
      name: WORLD_NAME,
      one_liner: "A deterministic geometric relay range.",
      narrative: "Traverse the range, collect the single drop, and enter the exit portal.",
    },
    mobs: [
      {
        tier_label: "training-0",
        body_plan: "rectangular automaton",
        name: "Relay Block",
        brief: "A one-hit geometric target.",
      },
    ],
    obstacles: [],
    items: Array.from({ length: 8 }, (_, index) => ({
      kind: `token-${index}`,
      name: `Relay Token ${index}`,
      brief: "A deterministic geometric pickup.",
    })),
    layers: LAYERS,
  };
}

function generatedPngs(): Readonly<Record<string, Raster>> {
  return {
    [`concept_${GAMEPLAY_TAG}.png`]: opaqueBackdrop(),
    [`layer_${GAMEPLAY_TAG}_sky.png`]: opaqueBackdrop(),
    [`layer_${GAMEPLAY_TAG}_ridges.png`]: transparentLayer("ridges"),
    [`layer_${GAMEPLAY_TAG}_foreground.png`]: transparentLayer("foreground"),
    [`tileset_${GAMEPLAY_TAG}.png`]: tileset(),
    [`ladder_${GAMEPLAY_TAG}.png`]: conceptSprite(128, 256, COLORS.amber),
    [`character_concept_${GAMEPLAY_TAG}.png`]: conceptSprite(128, 192, COLORS.cyan),
    [`character_${GAMEPLAY_TAG}-fromcombined_idle.png`]: frameStrip(COLORS.cyan, 0),
    [`character_${GAMEPLAY_TAG}-fromcombined_walk.png`]: frameStrip(COLORS.cyan, 1),
    [`character_${GAMEPLAY_TAG}-fromcombined_run.png`]: frameStrip(COLORS.green, 2),
    [`character_${GAMEPLAY_TAG}-fromcombined_jump.png`]: frameStrip(COLORS.amber, 3),
    [`character_${GAMEPLAY_TAG}-fromcombined_climb.png`]: frameStrip(COLORS.cyan, 4),
    [`character_${GAMEPLAY_TAG}-fromcombined_crawl.png`]: frameStrip(COLORS.violet, 4),
    [`character_${GAMEPLAY_TAG}_attack.png`]: frameStrip(COLORS.coral, 5),
    [`character_${GAMEPLAY_TAG}_hurt.png`]: frameStrip(COLORS.violet, 6),
    [`mob_concept_${GAMEPLAY_TAG}_0.png`]: conceptSprite(128, 128, COLORS.coral),
    [`mob_${GAMEPLAY_TAG}_0_idle.png`]: frameStrip(COLORS.coral, 0),
    [`mob_${GAMEPLAY_TAG}_0_hurt.png`]: frameStrip(COLORS.amber, 2),
    [`items_${GAMEPLAY_TAG}.png`]: itemSheet(),
    [`inventory_${GAMEPLAY_TAG}.png`]: inventoryPanel(),
    [`portal_${GAMEPLAY_TAG}.png`]: portalSheet(),
  };
}

function jsonBytes(value: unknown): Buffer {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function localArtifactProvenance(
  artifact: Buffer,
  mediaType: string,
  prompt: string,
  tool: string,
): Buffer {
  const digest = (bytes: Uint8Array | string) =>
    createHash("sha256").update(bytes).digest("hex");
  return jsonBytes({
    schema_version: 2,
    provider: "local",
    model: "deterministic-gameplay-fixture",
    seed: null,
    prompt,
    prompt_sha256: digest(prompt),
    references: [],
    refs: [],
    inputs: [],
    params: { stage: "gameplay-fixture" },
    validation: { deterministic: true },
    component: { name: "@stage-gen/web", version: "0.0.0" },
    tool: { name: tool, version: "1" },
    artifact: {
      sha256: digest(artifact),
      bytes: artifact.byteLength,
      media_type: mediaType,
    },
    ts: "1970-01-01T00:00:00Z",
    attempts: 1,
    retries: 0,
  });
}

function fixtureScaleReference(
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
    evidence: "Deterministic synthetic actor bounds.",
    frame_index: frameIndex,
    cell_width: cellWidth,
    cell_height: cellHeight,
  };
}

function fixtureRuntimeAssets() {
  return GAMEPLAY_RUNTIME_ASSETS.map((asset) => {
    const dimensions = (
      GAMEPLAY_PNG_DIMENSIONS as Readonly<
        Record<string, readonly [number, number]>
      >
    )[asset.path];
    if (!dimensions) throw new Error(`gameplay fixture dimensions missing for ${asset.path}`);
    const [width, height] = dimensions;
    const cellWidth = width / asset.columns;
    const cellHeight = height / asset.rows;
    if (!Number.isSafeInteger(cellWidth) || !Number.isSafeInteger(cellHeight)) {
      throw new Error(`gameplay fixture layout is not integral for ${asset.role}`);
    }
    return {
      id: asset.role,
      runtime_slot: asset.role,
      path: asset.path,
      provenance_path: `${asset.path}.meta.json`,
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
      ...(runtimeRoleOwnsScaleReference(asset.role)
        ? {
            scale_reference: fixtureScaleReference(
              cellWidth,
              cellHeight,
              asset.role.endsWith("-attack") ? 1 : 0,
            ),
          }
        : {}),
    };
  });
}

/** Create a fresh, fully synthetic run directory without reading media files. */
export async function generateGameplayFixture(outRoot: string): Promise<GameplayFixture> {
  if (!path.isAbsolute(outRoot) || outRoot.includes("\0")) {
    throw new Error("gameplay fixture output root must be an absolute path");
  }
  await fs.mkdir(outRoot, { recursive: true, mode: 0o700 });
  const rootStat = await fs.lstat(outRoot);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error("gameplay fixture output root must be a real directory");
  }
  const runDir = path.join(outRoot, GAMEPLAY_TAG);
  await fs.mkdir(runDir, { mode: 0o700 });

  const outputs = new Map<string, Buffer>();
  for (const [filename, image] of Object.entries(generatedPngs())) {
    const bytes = encodePng(image);
    outputs.set(filename, bytes);
    outputs.set(
      `${filename}.meta.json`,
      localArtifactProvenance(
        bytes,
        "image/png",
        `emit deterministic gameplay fixture ${filename}`,
        "gameplay-fixture-raster",
      ),
    );
  }
  const worldSpecPath = `world_spec_${GAMEPLAY_TAG}.json`;
  const worldSpecBytes = jsonBytes(worldSpec());
  outputs.set(worldSpecPath, worldSpecBytes);
  outputs.set(
    `${worldSpecPath}.meta.json`,
    localArtifactProvenance(
      worldSpecBytes,
      "application/json",
      "emit deterministic gameplay fixture world spec",
      "gameplay-fixture-world-spec",
    ),
  );
  // The current runtime requires the one v7 scrolling manifest. Optional subsystems may be
  // absent, but the current core envelope and every published nested key are lower_snake_case.
  outputs.set(
    `manifest_${GAMEPLAY_TAG}.json`,
    jsonBytes({
      schema_version: 7,
      recipe: "scrolling-preview",
      tag: GAMEPLAY_TAG,
      transparency_mode: GAMEPLAY_TRANSPARENCY_MODE,
      artifacts: [...outputs.keys()].sort(),
      canonical_artifacts: [],
      world_spec: {
        path: worldSpecPath,
        provenance_path: `${worldSpecPath}.meta.json`,
      },
      runtime_assets: fixtureRuntimeAssets(),
      image_repeat: { enabled: false, status: "deferred", artifacts: [] },
    }),
  );
  outputs.set(
    "run.json",
    jsonBytes({
      schema_version: RECIPE_RUN_SCHEMA_VERSION,
      kind: RECIPE_RUN_KIND,
      recipe: "scrolling-preview",
      input: {
        prompt: GAMEPLAY_PROMPT,
        transparency_mode: GAMEPLAY_TRANSPARENCY_MODE,
      },
      tag: GAMEPLAY_TAG,
      run_dir: GAMEPLAY_TAG,
      started_at: "1970-01-01T00:00:00Z",
      ended_at: "1970-01-01T00:00:00Z",
      duration_ms: 0,
      ok: true,
      stages: [
        {
          stage: "gameplay-fixture",
          ok: true,
          duration_ms: 0,
          artifacts: [...outputs.keys()].sort(),
        },
      ],
    }),
  );

  const artifactHashes = Object.fromEntries(
    [...outputs.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([filename, bytes]) => [
        filename,
        createHash("sha256").update(bytes).digest("hex"),
      ]),
  );
  outputs.set(
    GAMEPLAY_FIXTURE_METADATA_FILE,
    jsonBytes({
      version: GAMEPLAY_AUTOMATION_VERSION,
      generator: "web/tests/gameplay/fixture.ts",
      original: true,
      prompt: GAMEPLAY_PROMPT,
      tag: GAMEPLAY_TAG,
      transparencyMode: GAMEPLAY_TRANSPARENCY_MODE,
      artifactHashes,
    }),
  );

  for (const [filename, bytes] of [...outputs.entries()].sort(([left], [right]) =>
    left.localeCompare(right),
  )) {
    await fs.writeFile(path.join(runDir, filename), bytes, { flag: "wx", mode: 0o600 });
  }

  const digest = createHash("sha256")
    .update(
      [...outputs.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([filename, bytes]) => `${filename}:${createHash("sha256").update(bytes).digest("hex")}\n`)
        .join(""),
    )
    .digest("hex");
  return Object.freeze({
    outRoot,
    runDir,
    tag: GAMEPLAY_TAG,
    route: `/preview/${GAMEPLAY_TAG}?automation=${GAMEPLAY_AUTOMATION_VERSION}`,
    files: Object.freeze([...outputs.keys()].sort()),
    digest,
  });
}
