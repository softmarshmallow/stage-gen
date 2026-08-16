import { afterEach, describe, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { PNG, type PngWriteInput } from "pngjs";
import { GAMEPLAY_FIXTURE_METADATA_FILE } from "./contracts";
import {
  GAMEPLAY_DEMO_APPROVAL_MANIFEST,
  GAMEPLAY_DEMO_ASSET_MANIFEST,
  GAMEPLAY_MODEL_ASSET_CONTRACTS,
  GAMEPLAY_MODEL_FIXTURE_FILES,
  GAMEPLAY_MODEL_PROMPT,
  GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS,
  GAMEPLAY_MODEL_TAG,
  GAMEPLAY_MODEL_TERRAIN_SEED,
  GAMEPLAY_MODEL_TRANSPARENCY_MODE,
  generateApprovedModelGameplayFixture,
  type GameplayModelAssetContract,
} from "./model-assets";

const temporaryRoots: string[] = [];

type TestProducerAsset = {
  id: string;
  path: string;
  runtimeSlot: string;
  target: { width: number; height: number };
  layout: { rows: number; columns: number };
  alphaExpectation: string;
  prompt: string;
  referenceAssetIds: string[];
  parameters: Record<string, unknown>;
  sourceOutput: {
    fileName: string;
    sha256: string;
    width: number;
    height: number;
    mimeType: string;
  };
  postprocess: Record<string, unknown>;
  output: { sha256: string; width: number; height: number; mimeType: string };
  reviewStatus: string;
};

type TestApprovalAsset = {
  id: string;
  path: string;
  sha256: string;
  bytes: number;
  visualReview: {
    status: string;
    result: string;
    independent: boolean;
    reviewedBy: string;
    authorityBasis: string;
    reviewedAt: string;
    attestationId: string;
    attestedAt: string;
  };
  rights: { status: string; basis: string[] };
};

type TestSource = {
  root: string;
  producer: {
    schemaVersion: number;
    artDirection: Record<string, unknown>;
    generator: Record<string, unknown>;
    assets: TestProducerAsset[];
  };
  approval: {
    schemaVersion: number;
    sourceManifest: { path: string; sha256: string; bytes: number };
    setReview: {
      status: string;
      result: string;
      independent: boolean;
      reviewedBy: string;
      authorityBasis: string;
      reviewedAt: string;
      attestationId: string;
      attestedAt: string;
    };
    assets: TestApprovalAsset[];
  };
};

afterEach(async () => {
  await Promise.all(
    temporaryRoots.splice(0).map((root) => fs.rm(root, { recursive: true, force: true })),
  );
});

async function makeRoot(label: string): Promise<string> {
  const root = await fs.mkdtemp(path.join(tmpdir(), `stage-gen-${label}-`));
  temporaryRoots.push(root);
  return root;
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function jsonBytes(value: unknown): Buffer {
  return Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function paintPixel(png: PngWriteInput, x: number, y: number, channel: number): void {
  const offset = (y * png.width + x) * 4;
  png.data[offset] = 32 + (channel % 160);
  png.data[offset + 1] = 64 + (channel % 128);
  png.data[offset + 2] = 96 + (channel % 96);
  png.data[offset + 3] = 255;
}

function contractPng(
  contract: GameplayModelAssetContract,
  forceOpaque = false,
): Buffer {
  const png: PngWriteInput = {
    width: contract.width,
    height: contract.height,
    data: Buffer.alloc(contract.width * contract.height * 4),
  };
  if (contract.alphaExpectation === "opaque" || forceOpaque) {
    for (let y = 0; y < contract.height; y += 1) {
      for (let x = 0; x < contract.width; x += 1) paintPixel(png, x, y, x + y);
    }
  } else {
    const cellWidth = contract.width / contract.columns;
    const cellHeight = contract.height / contract.rows;
    for (let row = 0; row < contract.rows; row += 1) {
      for (let column = 0; column < contract.columns; column += 1) {
        paintPixel(
          png,
          column * cellWidth + Math.floor(cellWidth / 2),
          row * cellHeight + Math.floor(cellHeight / 2),
          row * contract.columns + column,
        );
      }
    }
    if (contract.id === "tileset") {
      for (let y = 98; y < 126; y += 1) {
        for (let x = 2; x < 30; x += 1) paintPixel(png, x, y, x + y);
      }
    }
  }
  return PNG.sync.write(png, { colorType: 6, inputColorType: 6 });
}

async function persistManifests(source: TestSource): Promise<void> {
  const producerBytes = jsonBytes(source.producer);
  source.approval.sourceManifest = {
    path: GAMEPLAY_DEMO_ASSET_MANIFEST,
    sha256: sha256(producerBytes),
    bytes: producerBytes.byteLength,
  };
  await Promise.all([
    fs.writeFile(path.join(source.root, GAMEPLAY_DEMO_ASSET_MANIFEST), producerBytes),
    fs.writeFile(
      path.join(source.root, GAMEPLAY_DEMO_APPROVAL_MANIFEST),
      jsonBytes(source.approval),
    ),
  ]);
}

async function createApprovedSource(): Promise<TestSource> {
  const root = await makeRoot("model-assets");
  const setAttestation = "cohesive-set-test-attestation";
  const producerAssets: TestProducerAsset[] = [];
  const approvalAssets: TestApprovalAsset[] = [];
  for (const contract of GAMEPLAY_MODEL_ASSET_CONTRACTS) {
    const bytes = contractPng(contract);
    await fs.writeFile(path.join(root, contract.path), bytes);
    const outputDigest = sha256(bytes);
    const assetAttestation = `${contract.id}-test-attestation`;
    producerAssets.push({
      id: contract.id,
      path: contract.path,
      runtimeSlot: contract.runtimeSlot,
      target: { width: contract.width, height: contract.height },
      layout: { rows: contract.rows, columns: contract.columns },
      alphaExpectation: contract.alphaExpectation,
      prompt: `Original contract-test artwork for ${contract.id}.`,
      referenceAssetIds: contract.id.endsWith("concept") ? [] : ["concept"],
      parameters: { numLastImagesToInclude: 0 },
      sourceOutput: {
        fileName: `${contract.id}-source.png`,
        sha256: sha256(Buffer.from(`source:${contract.id}`, "utf8")),
        width: contract.width,
        height: contract.height,
        mimeType: "image/png",
      },
      postprocess: {
        tool: "contract-test",
        operation: "deterministic-fixture",
        ...(contract.alphaExpectation === "transparent"
          ? {
              backgroundRemoval: {
                provider: "fal",
                model: "fal-ai/birefnet/v2",
                operation: "remove-background",
                provenanceSha256: sha256(
                  Buffer.from(`background-removal:${contract.id}`, "utf8"),
                ),
                attempts: 1,
                output: {
                  sha256: outputDigest,
                  bytes: bytes.byteLength,
                  width: contract.width,
                  height: contract.height,
                  mimeType: "image/png",
                },
              },
            }
          : {}),
        ...(["tileset", "character-attack"].includes(contract.id)
          ? { cellGutterPixels: 2 }
          : {}),
      },
      output: {
        sha256: outputDigest,
        width: contract.width,
        height: contract.height,
        mimeType: "image/png",
      },
      reviewStatus: "pending-independent-review",
    });
    approvalAssets.push({
      id: contract.id,
      path: contract.path,
      sha256: outputDigest,
      bytes: bytes.byteLength,
      visualReview: {
        status: "approved",
        result: "pass",
        independent: true,
        reviewedBy: "independent-contract-test-reviewer",
        authorityBasis: "synthetic non-visual contract test",
        reviewedAt: "2026-08-16T00:00:00Z",
        attestationId: assetAttestation,
        attestedAt: "2026-08-16T00:00:00Z",
      },
      rights: {
        status: "redistribution-approved",
        basis: [assetAttestation, setAttestation],
      },
    });
  }
  const source: TestSource = {
    root,
    producer: {
      schemaVersion: 1,
      artDirection: { title: "Original test direction", palette: ["navy", "amber"] },
      generator: {
        tool: "image_gen.imagegen",
        mode: "built-in",
        model: "unavailable",
        seed: {
          available: false,
          value: null,
          reason: "built-in tool did not expose a seed",
        },
      },
      assets: producerAssets,
    },
    approval: {
      schemaVersion: 1,
      sourceManifest: { path: "placeholder", sha256: "0".repeat(64), bytes: 1 },
      setReview: {
        status: "approved",
        result: "pass",
        independent: true,
        reviewedBy: "independent-set-test-reviewer",
        authorityBasis: "synthetic non-visual contract test",
        reviewedAt: "2026-08-16T00:00:00Z",
        attestationId: setAttestation,
        attestedAt: "2026-08-16T00:00:00Z",
      },
      assets: approvalAssets,
    },
  };
  await persistManifests(source);
  return source;
}

async function replaceFinalAsset(
  source: TestSource,
  assetId: string,
  bytes: Buffer,
): Promise<void> {
  const producer = source.producer.assets.find((asset) => asset.id === assetId)!;
  const approval = source.approval.assets.find((asset) => asset.id === assetId)!;
  await fs.writeFile(path.join(source.root, producer.path), bytes);
  producer.output.sha256 = sha256(bytes);
  approval.sha256 = sha256(bytes);
  approval.bytes = bytes.byteLength;
  await persistManifests(source);
}

describe("approved model gameplay fixture adapter", () => {
  test("promotes exact approved bytes into the deterministic runtime contract", async () => {
    const source = await createApprovedSource();
    const first = await generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
      sourceRoot: source.root,
    });
    const second = await generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
      sourceRoot: source.root,
    });

    expect(first.files).toEqual([...GAMEPLAY_MODEL_FIXTURE_FILES].sort());
    expect(first.digest).toBe(second.digest);
    expect(first.tag).toBe(GAMEPLAY_MODEL_TAG);
    for (const contract of GAMEPLAY_MODEL_ASSET_CONTRACTS) {
      const sourceBytes = await fs.readFile(path.join(source.root, contract.path));
      const runtimeName = contract.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG);
      const promotedBytes = await fs.readFile(path.join(first.runDir, runtimeName));
      expect(promotedBytes).toEqual(sourceBytes);
      const stat = await fs.lstat(path.join(first.runDir, runtimeName));
      expect(stat.isFile()).toBe(true);
      expect(stat.isSymbolicLink()).toBe(false);
    }
    const metadata = JSON.parse(
      await fs.readFile(path.join(first.runDir, GAMEPLAY_FIXTURE_METADATA_FILE), "utf8"),
    );
    expect(metadata.generator).toBe("web/tests/gameplay/model-assets.ts");
    expect(metadata.sourceManifest.path).toBe("fixtures/gameplay-demo/asset-manifest.json");
    expect(metadata.approvalManifest.path).toBe("fixtures/gameplay-demo/approval-manifest.json");
    expect(Object.keys(metadata.sourceAssetHashes)).toHaveLength(18);
    expect(metadata.prompt).toBe(GAMEPLAY_MODEL_PROMPT);
    expect(metadata.tag).toBe(GAMEPLAY_MODEL_TAG);
    expect(metadata.transparencyMode).toBe(GAMEPLAY_MODEL_TRANSPARENCY_MODE);
    expect(metadata.generationProvenance).toMatchObject({
      tool: "image_gen.imagegen",
      mode: "built-in",
      model: "unavailable",
      seed: { available: false, value: null },
    });
    expect(metadata.transparencyProvenance).toMatchObject({
      mode: "ai",
      canonicalAlpha: true,
      provider: "fal",
      model: "fal-ai/birefnet/v2",
    });
    expect(metadata.transparencyProvenance.assetIds).toEqual(
      GAMEPLAY_MODEL_ASSET_CONTRACTS.filter(
        (asset) => asset.alphaExpectation === "transparent",
      )
        .map((asset) => asset.id)
        .sort(),
    );

    const run = JSON.parse(await fs.readFile(path.join(first.runDir, "run.json"), "utf8"));
    const spec = JSON.parse(
      await fs.readFile(
        path.join(first.runDir, `world_spec_${GAMEPLAY_MODEL_TAG}.json`),
        "utf8",
      ),
    );
    expect(run.input).toEqual({
      recipe: "scrolling-preview",
      prompt: GAMEPLAY_MODEL_PROMPT,
      transparencyMode: "ai",
    });
    expect(spec.terrain_seed).toBe(GAMEPLAY_MODEL_TERRAIN_SEED);
    expect(spec.world.name).toBe("Moonlit Overgrown Ruins");
    expect(GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS).toContain(
      "spec:Moonlit Overgrown Ruins",
    );
    const emittedText = JSON.stringify({ run, spec, metadata });
    expect(emittedText).not.toContain("Geometric Relay Range");
    expect(emittedText).not.toContain("chroma");
  });

  test("requires truthful FAL background-removal provenance for transparent roles", async () => {
    const source = await createApprovedSource();
    const transparent = source.producer.assets.find(
      (asset) => asset.alphaExpectation === "transparent",
    )!;
    (transparent.postprocess.backgroundRemoval as Record<string, unknown>).provider =
      "unapproved-provider";
    await persistManifests(source);

    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("approved FAL BiRefNet operation");
  });

  test("rejects a producer manifest without an exact independent approval binding", async () => {
    const source = await createApprovedSource();
    source.approval.sourceManifest.sha256 = "f".repeat(64);
    await fs.writeFile(
      path.join(source.root, GAMEPLAY_DEMO_APPROVAL_MANIFEST),
      jsonBytes(source.approval),
    );
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("not bound to the exact producer manifest");
  });

  test("rejects pending set review and non-independent per-asset review", async () => {
    const pending = await createApprovedSource();
    pending.approval.setReview.status = "pending";
    await persistManifests(pending);
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: pending.root,
      }),
    ).rejects.toThrow("independent cohesive-set approval");

    const dependent = await createApprovedSource();
    dependent.approval.assets[0].visualReview.independent = false;
    await persistManifests(dependent);
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: dependent.root,
      }),
    ).rejects.toThrow("independent passing visual approval");
  });

  test("rejects PNGs that violate alpha requirements even when hashes are rebound", async () => {
    const source = await createApprovedSource();
    const contract = GAMEPLAY_MODEL_ASSET_CONTRACTS.find(
      (candidate) => candidate.id === "character-idle",
    )!;
    const bytes = contractPng(contract, true);
    await replaceFinalAsset(source, contract.id, bytes);

    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("must contain transparent and painted pixels");
  });

  test("rejects fractional alpha in an opaque role even when hashes are rebound", async () => {
    const source = await createApprovedSource();
    const concept = PNG.sync.read(await fs.readFile(path.join(source.root, "concept.png")));
    concept.data[3] = 254;
    await replaceFinalAsset(
      source,
      "concept",
      PNG.sync.write(concept, { colorType: 6, inputColorType: 6 }),
    );

    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("must be fully opaque");
  });

  test("requires the role gutters while leaving undeclared legacy atlas edges unchanged", async () => {
    const missing = await createApprovedSource();
    delete missing.producer.assets.find((asset) => asset.id === "character-attack")!
      .postprocess.cellGutterPixels;
    await persistManifests(missing);
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: missing.root,
      }),
    ).rejects.toThrow("must declare cellGutterPixels: 2");

    const malformed = await createApprovedSource();
    malformed.producer.assets.find((asset) => asset.id === "character-idle")!
      .postprocess.cellGutterPixels = 1;
    await persistManifests(malformed);
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: malformed.root,
      }),
    ).rejects.toThrow("exact 2-pixel atlas gutter");

    const undeclared = await createApprovedSource();
    const idlePath = path.join(undeclared.root, "character-idle.png");
    const idle = PNG.sync.read(await fs.readFile(idlePath));
    idle.data[3] = 255;
    await replaceFinalAsset(
      undeclared,
      "character-idle",
      PNG.sync.write(idle, { colorType: 6, inputColorType: 6 }),
    );
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: undeclared.root,
      }),
    ).resolves.toMatchObject({ tag: GAMEPLAY_MODEL_TAG });
  });

  test("enforces transparent gutters and the opaque tileset fill interior", async () => {
    const source = await createApprovedSource();
    const tilesetPath = path.join(source.root, "tileset.png");
    const validBytes = await fs.readFile(tilesetPath);
    const opaqueGutter = PNG.sync.read(validBytes);
    opaqueGutter.data[(96 * opaqueGutter.width) * 4 + 3] = 255;
    await replaceFinalAsset(
      source,
      "tileset",
      PNG.sync.write(opaqueGutter, { colorType: 6, inputColorType: 6 }),
    );
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("cell gutters must be transparent");

    const transparentInterior = PNG.sync.read(validBytes);
    transparentInterior.data[(98 * transparentInterior.width + 2) * 4 + 3] = 0;
    await replaceFinalAsset(
      source,
      "tileset",
      PNG.sync.write(transparentInterior, { colorType: 6, inputColorType: 6 }),
    );
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("ground-fill cell interior must be fully opaque");
  });

  test("rejects symlinked assets and relative output roots", async () => {
    const source = await createApprovedSource();
    const assetPath = path.join(source.root, "portal.png");
    const movedPath = path.join(source.root, "portal-original.png");
    await fs.rename(assetPath, movedPath);
    await fs.symlink(path.basename(movedPath), assetPath);
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("non-symlink regular file");
    await expect(
      generateApprovedModelGameplayFixture("relative/out", { sourceRoot: source.root }),
    ).rejects.toThrow("absolute path");
  });
});
