import { describe, expect, test } from "bun:test";
import {
  GAMEPLAY_AUTOMATION_MODE,
  type GameplayAutomationSnapshot,
} from "../../lib/runtime/automation";
import {
  GAMEPLAY_STILL_REPORT_KIND,
  GAMEPLAY_STILL_REPORT_SCHEMA_VERSION,
  parseGameplayStillArgs,
  parseGameplayStillReport,
  validateGameplayStillProbe,
} from "./still";

function validStillReport(): Record<string, unknown> {
  return {
    schema_version: GAMEPLAY_STILL_REPORT_SCHEMA_VERSION,
    kind: GAMEPLAY_STILL_REPORT_KIND,
    state: "unreviewed",
    capture_target: "phaser-canvas-only",
    shell_included: false,
    development_overlay_included: false,
    route: `/preview/storybook-demo?automation=${GAMEPLAY_AUTOMATION_MODE}`,
    tag: "storybook-demo",
    build_id: "current-build",
    output: "output/playwright/storybook-demo.canvas.png",
    sidecar: "output/playwright/storybook-demo.canvas.png.capture.json",
    width: 1280,
    height: 720,
    sha256: "a".repeat(64),
    runtime: {
      errors: [],
      diagnostics: [],
      loaded_asset_keys: ["tileset", "ladder", "character_idle"],
      visible_tier_count: 3,
      visible_ladder_count: 1,
    },
  };
}

describe("gameplay canvas-only still capture", () => {
  test("parses one confined output contract", () => {
    expect(
      parseGameplayStillArgs([
        "--tag",
        "storybook-demo",
        "--output",
        "output/playwright/storybook-demo.canvas.png",
      ]),
    ).toEqual({
      tag: "storybook-demo",
      output: "output/playwright/storybook-demo.canvas.png",
      timeoutMs: 120_000,
    });
    expect(() =>
      parseGameplayStillArgs(["--tag", "storybook-demo", "--output", "../capture.png"]),
    ).toThrow("repository-relative");
  });

  test("accepts only the exact current persisted and public still report", () => {
    const value = validStillReport();

    const report = parseGameplayStillReport(value);

    expect(report as unknown).toEqual(value);
    expect(report.schema_version).toBe(1);
    expect(report.kind).toBe("gameplay-still-report-v1");
    expect(report.capture_target).toBe("phaser-canvas-only");
    expect(report.runtime.loaded_asset_keys).toEqual([
      "tileset",
      "ladder",
      "character_idle",
    ]);
    expect(Object.isFrozen(report)).toBeTrue();
    expect(Object.isFrozen(report.runtime)).toBeTrue();
    expect(report).not.toHaveProperty("schemaVersion");
    expect(report).not.toHaveProperty("captureTarget");
    expect(report.runtime).not.toHaveProperty("loadedAssetKeys");
  });

  test("rejects legacy aliases, version drift, extras, and invalid report bindings", () => {
    expect(() =>
      parseGameplayStillReport({ ...validStillReport(), schema_version: 2 }),
    ).toThrow("schema_version must equal 1");
    expect(() =>
      parseGameplayStillReport({ ...validStillReport(), kind: "gameplay-still-report-v2" }),
    ).toThrow("kind must equal");
    expect(() => parseGameplayStillReport({ ...validStillReport(), extra: true })).toThrow(
      "extra is not a supported key",
    );

    const camel = validStillReport();
    camel.schemaVersion = camel.schema_version;
    delete camel.schema_version;
    expect(() => parseGameplayStillReport(camel)).toThrow(
      "schemaVersion is not a supported key",
    );

    const nestedCamel = validStillReport();
    const runtime = nestedCamel.runtime as Record<string, unknown>;
    runtime.loadedAssetKeys = runtime.loaded_asset_keys;
    delete runtime.loaded_asset_keys;
    expect(() => parseGameplayStillReport(nestedCamel)).toThrow(
      "runtime.loadedAssetKeys is not a supported key",
    );

    expect(() =>
      parseGameplayStillReport({
        ...validStillReport(),
        route: `/preview/another-run?automation=${GAMEPLAY_AUTOMATION_MODE}`,
      }),
    ).toThrow("route must equal");
    expect(() =>
      parseGameplayStillReport({
        ...validStillReport(),
        sidecar: "output/playwright/another.capture.json",
      }),
    ).toThrow("sidecar must equal");
    expect(() =>
      parseGameplayStillReport({
        ...validStillReport(),
        runtime: {
          ...(validStillReport().runtime as Record<string, unknown>),
          errors: ["browser failed"],
        },
      }),
    ).toThrow("must record a clean capture");
  });

  test("requires clean roles and a complete safe still composition", () => {
    const keys = [
      "spec:Storybook",
      "layer_backdrop_sky",
      "layer_foreground",
      "tileset",
      "ladder",
      "character_climb",
      "character_idle",
      "character_walk",
      "character_run",
      "character_jump",
      "character_crawl",
      "character_attack",
      "items",
      "inventory",
      "portal",
      "mob_0_idle",
    ];
    const probe = {
      version: "gameplay-v2",
      state: "ready",
      ready: true,
      errors: [],
      diagnostics: [],
      assetKeys: keys,
      frame: 0,
      simulationMs: 0,
      player: {
        renderBounds: { left: 100, right: 180, top: 300, bottom: 420 },
      },
      camera: { scrollX: 0, scrollY: 0, zoom: 1 },
      layers: [
        {
          kind: "sky",
          render: { visible: true, spriteCount: 1 },
        },
        {
          kind: "near-foreground",
          render: { visible: true, spriteCount: 1 },
          foreground: { meaningfulContentScreenBounds: { top: 560 } },
          safeBounds: { top: 540 },
        },
      ],
      platforms: [520, 440, 360].map((deckY, index) => ({
        visible: true,
        tier: index + 1,
        deckY,
      })),
      platformRoutes: [],
      ladders: [{ visible: true }],
      mobs: [
        {
          alive: true,
          visible: true,
          renderBounds: { left: 300, right: 400, top: 300, bottom: 400 },
        },
      ],
      inventory: {
        visible: true,
        bounds: { left: 821, right: 1256, top: 24, bottom: 314 },
        slots: [],
      },
      worldItems: [
        {
          kindIndex: 0,
          x: 720,
          y: 440,
          settled: true,
          renderBounds: { left: 700, right: 740, top: 400, bottom: 440 },
        },
      ],
      encounter: {},
      portals: [{ kind: "entry", x: 560, y: 500, w: 120, h: 180 }],
      presentation: {},
      events: [],
      heightmapDigest: "a".repeat(64),
    } as unknown as GameplayAutomationSnapshot;
    expect(() => validateGameplayStillProbe(probe)).not.toThrow();
    expect(() =>
      validateGameplayStillProbe({
        ...probe,
        layers: probe.layers.filter((layer) => layer.kind !== "sky"),
      }),
    ).toThrow("sky-layer");
    expect(() =>
      validateGameplayStillProbe({ ...probe, errors: ["boom"] }),
    ).toThrow("zero runtime errors");
    expect(() =>
      validateGameplayStillProbe({
        ...probe,
        platforms: probe.platforms.map((platform, index) => ({
          ...platform,
          visible: index < 2,
        })),
      }),
    ).toThrow("three tiers");

    expect(() =>
      validateGameplayStillProbe({
        ...probe,
        player: {
          ...probe.player!,
          renderBounds: { left: -180, right: -100, top: 300, bottom: 420 },
        },
      }),
    ).toThrow("fully visible");
    expect(() =>
      validateGameplayStillProbe({
        ...probe,
        mobs: probe.mobs.map((mob) => ({
          ...mob,
          renderBounds: { left: 1400, right: 1500, top: 300, bottom: 400 },
        })),
      }),
    ).toThrow("fully visible identifiable live mob");
    expect(() =>
      validateGameplayStillProbe({
        ...probe,
        player: {
          ...probe.player!,
          renderBounds: { left: 100, right: 180, top: 380, bottom: 420 },
        },
      }),
    ).toThrow("too small");
    expect(() => validateGameplayStillProbe({ ...probe, portals: [] })).toThrow(
      "fully visible identifiable portal",
    );
    expect(() =>
      validateGameplayStillProbe({ ...probe, worldItems: [] }),
    ).toThrow("fully visible identifiable pickup");
    expect(() =>
      validateGameplayStillProbe({
        ...probe,
        worldItems: probe.worldItems.map((item) => ({
          ...item,
          renderBounds: { left: 700, right: 710, top: 380, bottom: 440 },
        })),
      }),
    ).toThrow("fully visible identifiable pickup");
  });
});
