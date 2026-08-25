import { describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { GameplayAutomationSnapshot } from "../../lib/runtime/automation";
import type { SceneLayerKind, SceneLayerProbe } from "../../lib/runtime/layers";
import {
  GAMEPLAY_TAG,
  generateGameplayFixture,
} from "../../tests/gameplay/fixture";
import {
  DEFAULT_IMAGE_REPEAT_PROOF_TAG,
  assertImageRepeatManifestReady,
  foregroundJoinScreenX,
  isCentralJoinFrame,
  parseImageRepeatProofArgs,
  repeatPeriodsTravelled,
  selectImageRepeatProofTargets,
} from "./image-repeat-proof";

const SOURCE_SHA256 = "a".repeat(64);
const PREVIEW_SHA256 = "c".repeat(64);
const CRITERIA_SHA256 = "d".repeat(64);
const REVIEW_SHA256 = "e".repeat(64);
const REVIEW_PROVENANCE_SHA256 = "f".repeat(64);

async function currentManifest(): Promise<Record<string, unknown>> {
  const root = await fs.mkdtemp(
    path.join(os.tmpdir(), "stage-gen-image-repeat-proof-"),
  );
  try {
    const fixture = await generateGameplayFixture(root);
    return JSON.parse(
      await fs.readFile(
        path.join(fixture.runDir, `manifest_${GAMEPLAY_TAG}.json`),
        "utf8",
      ),
    ) as Record<string, unknown>;
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
}

const scaleMetrics = (scale: number) => ({
  scale,
  boundary_width_px: 2,
  color_mae: 0.01,
  color_p95: 0.02,
  color_max: 0.03,
  gradient_mae: 0.01,
  gradient_p95: 0.02,
  gradient_max: 0.03,
  alpha_mae: 0,
  alpha_p95: 0,
  alpha_max: 0,
  coverage_mismatch_ratio: 0,
  internal_color_p95: 0.02,
  color_limit: 0.12,
  gradient_limit: 0.18,
  alpha_limit: 0.08,
  coverage_limit: 0.1,
});

const admittedImageRepeatArtifact = () => ({
  schema_version: 2,
  kind: "single_axis_repeat_unit",
  axis: "x",
  decision: "admitted",
  source: {
    path: "layer_storybook_foreground.png",
    provenance_path: "layer_storybook_foreground.png.meta.json",
    sha256: SOURCE_SHA256,
    bytes: 123_456,
    width: 2_656,
    height: 800,
  },
  repeat_unit: {
    path: "layer_storybook_foreground.repeat-x.png",
    provenance_path: "layer_storybook_foreground.repeat-x.png.meta.json",
    sha256: SOURCE_SHA256,
    bytes: 123_456,
    width: 2_656,
    height: 800,
  },
  period_px: 2_656,
  cross_axis_extent_px: 800,
  intent: {
    intended_behavior: "one continuous low-salience scrolling layer",
    alpha_policy: "preserve",
    coverage_policy: "sparse_allowed",
    criteria_sha256: CRITERIA_SHA256,
  },
  construction: {
    mode: "admitted",
    algorithm: "direct-wrap-admission-v2",
    source_bytes_preserved: true,
  },
  validation: {
    policy: {
      scales: [1, 0.5, 0.25],
      color_mae: 0.12,
      color_p95: 0.25,
      color_max: 0.45,
      gradient_mae: 0.18,
      gradient_p95: 0.35,
      gradient_max: 0.7,
      alpha_mae: 0.08,
      alpha_p95: 0.2,
      alpha_max: 0.5,
      coverage_mismatch_ratio: 0.1,
      internal_baseline_multiplier: 2,
      coverage_alpha_threshold: 0.05,
    },
    deterministic: {
      validator_version: "single-axis-continuity-v2",
      axis: "x",
      verdict: "pass",
      alpha_policy: "preserve",
      coverage_policy: "sparse_allowed",
      source_immutable: true,
      joins: [
        {
          name: "wrap",
          verdict: "pass",
          scales: [scaleMetrics(1), scaleMetrics(0.5), scaleMetrics(0.25)],
          failure_codes: [],
        },
      ],
      failure_codes: [],
    },
    intended_loop: {
      review_version: "intended-loop-review-v1",
      verdict: "accept",
      confidence: 0.96,
      failure_codes: [],
      evidence: "The exact three-repeat preview reads as one continuous layer.",
      judged_sha256: SOURCE_SHA256,
      preview_sha256: PREVIEW_SHA256,
      criteria_sha256: CRITERIA_SHA256,
      reviewer_provider: "openrouter",
      reviewer_model: "openai/gpt-5.4",
      independent: true,
      review_artifact: {
        path: "layer_storybook_foreground.repeat-review.json",
        provenance_path:
          "layer_storybook_foreground.repeat-review.json.meta.json",
        sha256: REVIEW_SHA256,
        provenance_sha256: REVIEW_PROVENANCE_SHA256,
        bytes: 2_048,
      },
    },
    other_axis_status: "not_evaluated",
  },
  lineage: {
    mode: "admitted",
    source_sha256: SOURCE_SHA256,
    repeat_unit_sha256: SOURCE_SHA256,
  },
  rights_status: "unreviewed",
});

function repeatLayer(input: Readonly<{
  id: string;
  kind: SceneLayerKind;
  depthCoefficient: number;
  periodPx?: number;
  seamScreenX?: number;
  decision?: "admitted" | "repaired";
}>): SceneLayerProbe {
  const periodPx = input.periodPx ?? 2_400;
  return {
    id: input.id,
    kind: input.kind,
    depthCoefficient: input.depthCoefficient,
    repeat: "repeat-x-verified",
    render: {
      visible: true,
      spriteCount: 1,
      textureWidth: periodPx,
      tilePositionX: 0,
      tileScaleX: 0.5,
    },
    foreground:
      input.kind === "near-foreground"
        ? {
            repeatPeriodSourcePx: periodPx,
            overlapSourcePx: 0,
            spriteCount: 1,
            seamScreenX: input.seamScreenX ?? 640,
            projectedCameraTravelScreenPx: 0,
            seamPeriodScreenPx: periodPx * 0.5,
          }
        : null,
    imageRepeat: {
      schemaVersion: 2,
      axis: "x",
      decision: input.decision ?? "repaired",
      sourcePath: `layers/${input.id}.png`,
      repeatUnitPath: `image-repeat/${input.id}.repeat.png`,
      periodPx,
      selected: "verified-v2",
      unverifiedFallbackApplied: false,
      partnerSpriteCount: 0,
    },
  } as unknown as SceneLayerProbe;
}

function proofSnapshot(
  layers: readonly SceneLayerProbe[],
  cameraScrollX = 0,
  foregroundVisible = true,
): GameplayAutomationSnapshot {
  const projectedLayers = layers.map((layer) => ({
    ...layer,
    render: {
      ...layer.render,
      tilePositionX: Math.round(cameraScrollX * layer.depthCoefficient),
    },
    foreground: layer.foreground
      ? {
          ...layer.foreground,
          projectedCameraTravelScreenPx:
            cameraScrollX * layer.depthCoefficient,
        }
      : null,
  })) as readonly SceneLayerProbe[];
  return {
    version: "gameplay-v2",
    state: "ready",
    ready: true,
    errors: [],
    diagnostics: [],
    assetKeys: [],
    stageIndex: 0,
    stageId: "hunting-ground-0",
    frame: 81,
    simulationMs: 1_350,
    player: null,
    camera: { scrollX: cameraScrollX, scrollY: 0, zoom: 1 },
    layers: projectedLayers,
    platforms: [],
    platformRoutes: [],
    ladders: [],
    mobs: [],
    inventory: { visible: true, bounds: null, slots: [] },
    worldItems: [],
    encounter: {
      safeMarginPixels: 64,
      focusX: null,
      focusY: null,
      player: null,
      mob: null,
      attack: null,
      drop: null,
      pickup: null,
    },
    portals: [],
    presentation: {
      encounterFocus: false,
      foregroundVisible,
      inventorySuppressed: false,
      finalActiveWindow: false,
      cameraZoom: 1,
      portalScale: 1,
      portalAlpha: 1,
    },
    events: [],
    heightmapDigest: null,
  };
}

function selectedLayers(): readonly SceneLayerProbe[] {
  return [
    repeatLayer({ id: "distant_realm", kind: "distant", depthCoefficient: 0.18 }),
    repeatLayer({ id: "middle_hills", kind: "midground", depthCoefficient: 0.55 }),
    repeatLayer({ id: "playfield", kind: "midground", depthCoefficient: 1 }),
    repeatLayer({
      id: "near_foreground",
      kind: "near-foreground",
      depthCoefficient: 1.8,
      decision: "admitted",
    }),
  ];
}

describe("image repeat gameplay proof", () => {
  test("accepts the generated 67-character tag and one confined server origin", () => {
    expect(parseImageRepeatProofArgs([])).toEqual({
      tag: DEFAULT_IMAGE_REPEAT_PROOF_TAG,
      baseUrl: "http://127.0.0.1:3000",
      timeoutMs: 180_000,
    });
    expect(
      parseImageRepeatProofArgs([
        "--tag",
        DEFAULT_IMAGE_REPEAT_PROOF_TAG,
        "--base-url",
        "http://localhost:3100/",
        "--timeout-ms",
        "240000",
      ]),
    ).toEqual({
      tag: DEFAULT_IMAGE_REPEAT_PROOF_TAG,
      baseUrl: "http://localhost:3100",
      timeoutMs: 240_000,
    });

    for (const args of [
      ["--tag", "../run"],
      ["--base-url", "https://127.0.0.1:3000"],
      ["--base-url", "http://example.com:3000"],
      ["--base-url", "http://127.0.0.1:3000/preview"],
      ["--tag", "one", "--tag", "two"],
      ["--timeout-ms", "9999"],
      ["--timeout-ms", "600001"],
      ["--frames", "900"],
    ]) {
      expect(() => parseImageRepeatProofArgs(args)).toThrow();
    }
  });

  test("requires the exact current manifest and complete available repeat artifacts", async () => {
    const current = await currentManifest();
    expect(
      assertImageRepeatManifestReady(
        {
          ...current,
          image_repeat: {
            enabled: true,
            status: "available",
            artifacts: [admittedImageRepeatArtifact()],
          },
        },
        GAMEPLAY_TAG,
      ),
    ).toBe(1);

    expect(() =>
      assertImageRepeatManifestReady(
        {
          schema_version: 6,
          recipe: "scrolling-preview",
          tag: GAMEPLAY_TAG,
        },
        GAMEPLAY_TAG,
      ),
    ).toThrow("schema_version");

    const incomplete = { ...current };
    delete incomplete.runtime_assets;
    expect(() =>
      assertImageRepeatManifestReady(incomplete, GAMEPLAY_TAG),
    ).toThrow("missing required core key runtime_assets");

    expect(() =>
      assertImageRepeatManifestReady(
        { ...current, future_system: {} },
        GAMEPLAY_TAG,
      ),
    ).toThrow("future_system");

    expect(() =>
      assertImageRepeatManifestReady(
        {
          ...current,
          runtime_assets: [],
        },
        GAMEPLAY_TAG,
      ),
    ).toThrow();

    expect(() =>
      assertImageRepeatManifestReady(
        {
          ...current,
          image_repeat: {
            enabled: true,
            status: "available",
            artifacts: [{ schema_version: 2 }],
          },
        },
        GAMEPLAY_TAG,
      ),
    ).toThrow();

    expect(() =>
      assertImageRepeatManifestReady(
        { ...current, tag: "different-run" },
        GAMEPLAY_TAG,
      ),
    ).toThrow("requested tag");

    expect(() =>
      assertImageRepeatManifestReady(current, GAMEPLAY_TAG),
    ).toThrow("no available image_repeat artifacts");
  });

  test("selects moving background and foreground only through the verified-v2 gate", () => {
    const selection = selectImageRepeatProofTargets(proofSnapshot(selectedLayers()));
    expect(selection.all).toHaveLength(4);
    expect(selection.background.id).toBe("playfield");
    expect(selection.foreground.id).toBe("near_foreground");
    expect(selection.foreground.decision).toBe("admitted");

    const foreground = selectedLayers()[3]!;
    const invalid = [
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, unverifiedFallbackApplied: true },
      },
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, partnerSpriteCount: 1 },
      },
      {
        ...foreground,
        render: { ...foreground.render, spriteCount: 2 },
      },
      {
        ...foreground,
        render: { ...foreground.render, textureWidth: 2_399 },
      },
      {
        ...foreground,
        foreground: { ...foreground.foreground!, overlapSourcePx: 256 },
      },
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, decision: "accepted" },
      },
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, schemaVersion: 1 },
      },
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, axis: "y" },
      },
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, selected: "unverified" },
      },
      {
        ...foreground,
        imageRepeat: { ...foreground.imageRepeat!, repeatUnitPath: "../repeat.png" },
      },
    ];
    for (const layer of invalid) {
      expect(() =>
        selectImageRepeatProofTargets(
          proofSnapshot([...selectedLayers().slice(0, 3), layer as SceneLayerProbe]),
        ),
      ).toThrow();
    }
    expect(() =>
      selectImageRepeatProofTargets(proofSnapshot(selectedLayers().slice(0, 3))),
    ).toThrow("background and near-foreground");
  });

  test("measures two source periods and recognizes a visible central join", () => {
    const layers = selectedLayers();
    const start = proofSnapshot(layers, 0);
    const current = proofSnapshot(layers, 4_800);
    const selection = selectImageRepeatProofTargets(start);
    expect(repeatPeriodsTravelled(start, current, selection.background)).toBe(2);
    expect(repeatPeriodsTravelled(start, current, selection.foreground)).toBe(7.2);
    expect(foregroundJoinScreenX(current, selection.foreground)).toBe(640);
    expect(isCentralJoinFrame(start, current, selection.foreground)).toBe(true);

    const hidden = proofSnapshot(layers, 4_800, false);
    expect(foregroundJoinScreenX(hidden, selection.foreground)).toBeNull();
    expect(isCentralJoinFrame(start, hidden, selection.foreground)).toBe(false);
    expect(repeatPeriodsTravelled(current, start, selection.background)).toBe(0);
  });

  test("requires clean gameplay snapshots", () => {
    const snapshot = proofSnapshot(selectedLayers());
    expect(() =>
      selectImageRepeatProofTargets({ ...snapshot, errors: ["texture failed"] }),
    ).toThrow("not clean");
    expect(() =>
      selectImageRepeatProofTargets({ ...snapshot, diagnostics: ["fallback"] }),
    ).toThrow("not clean");
    expect(() =>
      selectImageRepeatProofTargets({ ...snapshot, ready: false, state: "loading" }),
    ).toThrow("ready gameplay-v2");
  });
});
