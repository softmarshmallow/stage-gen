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
  GAMEPLAY_DEMO_ROOT,
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
  layout: {
    rows: number;
    columns: number;
    cellWidth?: number;
    cellHeight?: number;
  };
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
  output: {
    sha256: string;
    bytes?: number;
    width: number;
    height: number;
    mimeType: string;
  };
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
    report?: { recordId: string; path?: string; sha256: string; bytes: number };
  };
  rights: { status: string; basis: string[] };
  dimensions?: { width: number; height: number };
  alphaExpectation?: string;
  styleReview?: Record<string, unknown>;
  runtimeScaleReview?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  cohesiveSet?: Record<string, unknown>;
  layout?: Record<string, unknown>;
  runtimeOutput?: Record<string, unknown>;
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
    temporaryRoots
      .splice(0)
      .map((root) => fs.rm(root, { recursive: true, force: true })),
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

function paintPixel(
  png: PngWriteInput,
  x: number,
  y: number,
  channel: number,
): void {
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
  const ladder = source.approval.assets.find((asset) => asset.id === "ladder");
  if (ladder?.provenance) {
    ladder.provenance.producerManifest = { ...source.approval.sourceManifest };
  }
  const climb = source.approval.assets.find(
    (asset) => asset.id === "character-climb",
  );
  if (climb?.provenance) {
    climb.provenance.producerManifest = { ...source.approval.sourceManifest };
  }
  await Promise.all([
    fs.writeFile(
      path.join(source.root, GAMEPLAY_DEMO_ASSET_MANIFEST),
      producerBytes,
    ),
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
  const canonicalClimbBytes = await fs.readFile(
    path.join(GAMEPLAY_DEMO_ROOT, "character-climb.png"),
  );
  for (const contract of GAMEPLAY_MODEL_ASSET_CONTRACTS) {
    const isClimb = contract.id === "character-climb";
    const bytes = isClimb ? canonicalClimbBytes : contractPng(contract);
    await fs.writeFile(path.join(root, contract.path), bytes);
    const outputDigest = sha256(bytes);
    const assetAttestation = `${contract.id}-test-attestation`;
    producerAssets.push({
      id: contract.id,
      path: contract.path,
      runtimeSlot: contract.runtimeSlot,
      target: { width: contract.width, height: contract.height },
      layout: {
        rows: contract.rows,
        columns: contract.columns,
        ...(isClimb ? { cellWidth: 64, cellHeight: 128 } : {}),
      },
      alphaExpectation: contract.alphaExpectation,
      prompt: `Original contract-test artwork for ${contract.id}.`,
      referenceAssetIds: contract.id.endsWith("concept") ? [] : ["concept"],
      parameters: isClimb
        ? {
            generationProvenance: {
              path: "fixtures/gameplay-demo/sources/character-climb/generation.json",
              sha256:
                "59504ed6731c851d3a3d87e91eaff139f1c7ecf7e4dee22cee1e2cf3f9d7b9bc",
              bytes: 14947,
              attempts: 5,
              selectedAttempt: 2,
            },
          }
        : { numLastImagesToInclude: 0 },
      sourceOutput: {
        fileName: isClimb
          ? "exec-38fdc4af-99bb-42cc-be44-d5d0ba80e0a5.png"
          : `${contract.id}-source.png`,
        sha256: isClimb
          ? "2d2e67b3750a0d0f1fa315e9a23c8fd7af3c2b75c472fdd661f4dfe897b4dbd2"
          : sha256(Buffer.from(`source:${contract.id}`, "utf8")),
        width: isClimb ? 1774 : contract.width,
        height: isClimb ? 887 : contract.height,
        mimeType: "image/png",
      },
      postprocess: isClimb
        ? {
            cellGutterPixels: 2,
            producerProvenance: {
              path: "fixtures/gameplay-demo/sources/character-climb/generation.json",
              sha256:
                "59504ed6731c851d3a3d87e91eaff139f1c7ecf7e4dee22cee1e2cf3f9d7b9bc",
              bytes: 14947,
              tool: "image_gen.imagegen",
              mode: "built-in",
              attempts: 5,
              selectedAttempt: 2,
            },
            backgroundExtraction: {
              tool: "Pillow",
              operation: "local-checkerboard-to-alpha-and-edge-decontamination",
              inputSha256:
                "2d2e67b3750a0d0f1fa315e9a23c8fd7af3c2b75c472fdd661f4dfe897b4dbd2",
              output: {
                sha256:
                  "4e23bc7690662429c2d52c88d90020c3dd5176f0e18b047d88a59d60a3040df5",
                bytes: 830149,
                width: 1774,
                height: 887,
                mimeType: "image/png",
              },
              provenancePath:
                "fixtures/gameplay-demo/sources/character-climb/character-climb-local-extracted.png.meta.json",
              provenanceSha256:
                "c7887efbf5cea15679137c8e70a73665c273376fc7781dc1507fcfe41da0018a",
              provenanceBytes: 1840,
              externalUploadPerformed: false,
            },
            normalization: {
              sourceSha256:
                "4e23bc7690662429c2d52c88d90020c3dd5176f0e18b047d88a59d60a3040df5",
              transparentGutterPixelsPerCellEdge: 2,
            },
          }
        : {
            tool: "contract-test",
            operation: "deterministic-fixture",
        ...(contract.id === "ladder"
          ? {
              producerProvenance: {
                path: "fixtures/gameplay-demo/sources/ladder/generation.json",
                sha256: sha256(
                  Buffer.from("synthetic ladder provenance", "utf8"),
                ),
              },
            }
          : {}),
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
        ...(isClimb ? { bytes: bytes.byteLength } : {}),
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
        ...(contract.id === "ladder"
          ? {
              report: {
                recordId: "stage-gen-ladder-visual-review",
                sha256:
                  "a4aea48b569cd5d29d322ac8705177506c1910b6a9bceed4220ab9f8bf0397b8",
                bytes: 282,
              },
            }
          : isClimb
            ? {
                report: {
                  recordId: "stage-gen-character-climb-visual-review",
                  path: "fixtures/gameplay-demo/sources/character-climb/visual-review.md",
                  sha256:
                    "b0e492daa55778ac99ae5b8ef5fec114455bf74e0240bb5b4f9557eacbab7c05",
                  bytes: 752,
                },
              }
            : {}),
      },
      rights: {
        status: "redistribution-approved",
        basis: [assetAttestation, setAttestation],
      },
      ...(contract.id === "ladder"
        ? {
            dimensions: { width: contract.width, height: contract.height },
            alphaExpectation: "transparent",
            styleReview: {
              status: "approved",
              result: "pass",
              independent: true,
              artDirection: "Moonlit Overgrown Ruins",
              cohesiveWithApprovedSet: true,
              referenceAssetIds: ["tileset", "concept"],
            },
            runtimeScaleReview: {
              status: "approved",
              result: "pass",
              source: { width: contract.width, height: contract.height },
              display: { width: 80, height: 320 },
              uniformScale: 0.3125,
            },
            provenance: {
              producerManifest: {
                path: GAMEPLAY_DEMO_ASSET_MANIFEST,
                sha256: "0".repeat(64),
                bytes: 1,
              },
              producerAssetId: "ladder",
              generationRecord: {
                path: "fixtures/gameplay-demo/sources/ladder/generation.json",
                sha256: sha256(
                  Buffer.from("synthetic ladder provenance", "utf8"),
                ),
                bytes: Buffer.byteLength("synthetic ladder provenance"),
              },
              backgroundRemovalProvenanceSha256: sha256(
                Buffer.from("background-removal:ladder", "utf8"),
              ),
            },
            cohesiveSet: {
              member: true,
              setAttestationId: setAttestation,
              extensionAttestationId: assetAttestation,
            },
          }
        : isClimb
          ? {
              dimensions: { width: 256, height: 128 },
              alphaExpectation: "transparent",
              layout: {
                rows: 1,
                columns: 4,
                cellWidth: 64,
                cellHeight: 128,
                transparentGutterPixelsPerCellEdge: 2,
              },
              styleReview: {
                status: "approved",
                result: "pass",
                independent: true,
                artDirection: "Moonlit Overgrown Ruins",
                cohesiveWithApprovedSet: true,
                referenceAssetIds: [
                  "character-concept",
                  "character-idle",
                  "character-jump",
                  "ladder",
                ],
              },
              runtimeOutput: {
                slot: "character_<tag>-fromcombined_climb.png",
                textureKey: "character_climb",
                frame: { width: 64, height: 128, count: 4 },
              },
              provenance: {
                producerManifest: {
                  path: GAMEPLAY_DEMO_ASSET_MANIFEST,
                  sha256: "0".repeat(64),
                  bytes: 1,
                },
                producerAssetId: "character-climb",
                generationRecord: {
                  path: "fixtures/gameplay-demo/sources/character-climb/generation.json",
                  sha256:
                    "59504ed6731c851d3a3d87e91eaff139f1c7ecf7e4dee22cee1e2cf3f9d7b9bc",
                  bytes: 14947,
                  attempts: 5,
                  selectedAttempt: 2,
                },
                localExtractionRecord: {
                  path: "fixtures/gameplay-demo/sources/character-climb/character-climb-local-extracted.png.meta.json",
                  sha256:
                    "c7887efbf5cea15679137c8e70a73665c273376fc7781dc1507fcfe41da0018a",
                  bytes: 1840,
                  outputSha256:
                    "4e23bc7690662429c2d52c88d90020c3dd5176f0e18b047d88a59d60a3040df5",
                  externalUploadPerformed: false,
                },
              },
              cohesiveSet: {
                member: true,
                setAttestationId: setAttestation,
                extensionAttestationId: assetAttestation,
              },
            }
          : {}),
    });
  }
  const source: TestSource = {
    root,
    producer: {
      schemaVersion: 1,
      artDirection: {
        title: "Original test direction",
        palette: ["navy", "amber"],
      },
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
  const generationRoot = path.join(root, "sources", "ladder");
  await fs.mkdir(generationRoot, { recursive: true });
  await fs.writeFile(
    path.join(generationRoot, "generation.json"),
    Buffer.from("synthetic ladder provenance", "utf8"),
  );
  const climbRoot = path.join(root, "sources", "character-climb");
  await fs.mkdir(climbRoot, { recursive: true });
  await Promise.all([
    fs.copyFile(
      path.join(
        GAMEPLAY_DEMO_ROOT,
        "sources",
        "character-climb",
        "generation.json",
      ),
      path.join(climbRoot, "generation.json"),
    ),
    fs.copyFile(
      path.join(
        GAMEPLAY_DEMO_ROOT,
        "sources",
        "character-climb",
        "character-climb-local-extracted.png.meta.json",
      ),
      path.join(climbRoot, "character-climb-local-extracted.png.meta.json"),
    ),
    fs.copyFile(
      path.join(
        GAMEPLAY_DEMO_ROOT,
        "sources",
        "character-climb",
        "visual-review.md",
      ),
      path.join(climbRoot, "visual-review.md"),
    ),
  ]);
  await persistManifests(source);
  return source;
}

async function replaceFinalAsset(
  source: TestSource,
  assetId: string,
  bytes: Buffer,
): Promise<void> {
  const producer = source.producer.assets.find(
    (asset) => asset.id === assetId,
  )!;
  const approval = source.approval.assets.find(
    (asset) => asset.id === assetId,
  )!;
  await fs.writeFile(path.join(source.root, producer.path), bytes);
  producer.output.sha256 = sha256(bytes);
  approval.sha256 = sha256(bytes);
  approval.bytes = bytes.byteLength;
  await persistManifests(source);
}

describe("approved model gameplay fixture adapter", () => {
  test("promotes exact approved bytes into the deterministic runtime contract", async () => {
    const source = await createApprovedSource();
    const first = await generateApprovedModelGameplayFixture(
      await makeRoot("model-out"),
      {
        sourceRoot: source.root,
      },
    );
    const second = await generateApprovedModelGameplayFixture(
      await makeRoot("model-out"),
      {
        sourceRoot: source.root,
      },
    );

    expect(first.files).toEqual([...GAMEPLAY_MODEL_FIXTURE_FILES].sort());
    expect(first.digest).toBe(second.digest);
    expect(first.tag).toBe(GAMEPLAY_MODEL_TAG);
    for (const contract of GAMEPLAY_MODEL_ASSET_CONTRACTS) {
      const sourceBytes = await fs.readFile(
        path.join(source.root, contract.path),
      );
      const runtimeName = contract.runtimeSlot.replace(
        "<tag>",
        GAMEPLAY_MODEL_TAG,
      );
      const promotedBytes = await fs.readFile(
        path.join(first.runDir, runtimeName),
      );
      expect(promotedBytes).toEqual(sourceBytes);
      const stat = await fs.lstat(path.join(first.runDir, runtimeName));
      expect(stat.isFile()).toBe(true);
      expect(stat.isSymbolicLink()).toBe(false);
    }
    const metadata = JSON.parse(
      await fs.readFile(
        path.join(first.runDir, GAMEPLAY_FIXTURE_METADATA_FILE),
        "utf8",
      ),
    );
    expect(metadata.generator).toBe("web/tests/gameplay/model-assets.ts");
    expect(metadata.sourceManifest.path).toBe(
      "fixtures/gameplay-demo/asset-manifest.json",
    );
    expect(metadata.approvalManifest.path).toBe(
      "fixtures/gameplay-demo/approval-manifest.json",
    );
    expect(Object.keys(metadata.sourceAssetHashes)).toHaveLength(
      GAMEPLAY_MODEL_ASSET_CONTRACTS.length,
    );
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
        (asset) =>
          asset.alphaExpectation === "transparent" &&
          asset.id !== "character-climb",
      )
        .map((asset) => asset.id)
        .sort(),
    );
    expect(metadata.transparencyProvenance.localExtractionAssetIds).toEqual([
      "character-climb",
    ]);

    const run = JSON.parse(
      await fs.readFile(path.join(first.runDir, "run.json"), "utf8"),
    );
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
    expect(GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS).toContain("ladder");
    expect(GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS).toContain("character_climb");
    const emittedText = JSON.stringify({ run, spec, metadata });
    expect(emittedText).not.toContain("Geometric Relay Range");
    expect(emittedText).not.toContain("chroma");
  });

  test("promotes the exact independently approved ladder and provenance", async () => {
    const fixture = await generateApprovedModelGameplayFixture(
      await makeRoot("approved-ladder"),
      { sourceRoot: GAMEPLAY_DEMO_ROOT },
    );
    const ladder = GAMEPLAY_MODEL_ASSET_CONTRACTS.find(
      (asset) => asset.id === "ladder",
    )!;
    const promoted = await fs.readFile(
      path.join(
        fixture.runDir,
        ladder.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG),
      ),
    );
    expect(sha256(promoted)).toBe(
      "a89b1d865b651806b1457ab1fc37da4d0a54ff28daf5566ec4011483c732faa6",
    );
    expect(promoted.byteLength).toBe(172703);
  });

  test("promotes the exact independently approved climb sheet and provenance", async () => {
    const fixture = await generateApprovedModelGameplayFixture(
      await makeRoot("approved-climb"),
      { sourceRoot: GAMEPLAY_DEMO_ROOT },
    );
    const climb = GAMEPLAY_MODEL_ASSET_CONTRACTS.find(
      (asset) => asset.id === "character-climb",
    )!;
    const promoted = await fs.readFile(
      path.join(
        fixture.runDir,
        climb.runtimeSlot.replace("<tag>", GAMEPLAY_MODEL_TAG),
      ),
    );
    expect(sha256(promoted)).toBe(
      "782fcda99a7296ab746c21d05014214503d4af280541b1f115031cf4d70dc56e",
    );
    expect(promoted.byteLength).toBe(39677);
  });

  test("rejects malformed climb generation-attempt provenance", async () => {
    const source = await createApprovedSource();
    const climb = source.producer.assets.find(
      (asset) => asset.id === "character-climb",
    )!;
    (
      climb.postprocess.producerProvenance as Record<string, unknown>
    ).attempts = 4;
    await persistManifests(source);

    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("five-attempt ImageGen provenance");
  });

  test("rejects an unapproved ladder runtime scale", async () => {
    const source = await createApprovedSource();
    const ladder = source.approval.assets.find(
      (asset) => asset.id === "ladder",
    )!;
    ladder.runtimeScaleReview!.uniformScale = 0.5;
    await persistManifests(source);

    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("preserve the approved aspect ratio");
  });

  test("requires truthful FAL background-removal provenance for transparent roles", async () => {
    const source = await createApprovedSource();
    const transparent = source.producer.assets.find(
      (asset) => asset.alphaExpectation === "transparent",
    )!;
    (
      transparent.postprocess.backgroundRemoval as Record<string, unknown>
    ).provider = "unapproved-provider";
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
    const concept = PNG.sync.read(
      await fs.readFile(path.join(source.root, "concept.png")),
    );
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
    delete missing.producer.assets.find(
      (asset) => asset.id === "character-attack",
    )!.postprocess.cellGutterPixels;
    await persistManifests(missing);
    await expect(
      generateApprovedModelGameplayFixture(await makeRoot("model-out"), {
        sourceRoot: missing.root,
      }),
    ).rejects.toThrow("must declare cellGutterPixels: 2");

    const malformed = await createApprovedSource();
    malformed.producer.assets.find(
      (asset) => asset.id === "character-idle",
    )!.postprocess.cellGutterPixels = 1;
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
    opaqueGutter.data[96 * opaqueGutter.width * 4 + 3] = 255;
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
      generateApprovedModelGameplayFixture("relative/out", {
        sourceRoot: source.root,
      }),
    ).rejects.toThrow("absolute path");
  });
});
