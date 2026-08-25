import { describe, expect, test } from "bun:test";
import {
  CANONICAL_SCENE_STACK,
  NEAR_FOREGROUND_DEPTH_COEFFICIENT,
  SCENE_CONTENT_DEPTH,
  SCENE_LAYER_DEPTH,
  foregroundPhaseForCamera,
  layoutSceneLayer,
  resolveSceneLayerStack,
  sceneLayerTextureScale,
  sceneLayerProbe,
  snapForegroundPhase,
  type SceneLayerAssetMetadata,
  type SceneLayerContract,
  type SceneLayerContext,
  type SceneLayerLayout,
  type SceneLayerManifestInput,
  type SceneLayerRenderState,
} from "./layers";

const CONTEXT: SceneLayerContext = Object.freeze({
  viewportWidth: 1280,
  viewportHeight: 720,
  worldWidth: 12_800,
  groundBaselineY: 720,
  foregroundContactScreenY: 704,
  foregroundSafeBandTopY: 540,
  foregroundMaxScale: 0.75,
});

const FOREGROUND_ASSET: SceneLayerAssetMetadata = Object.freeze({
  width: 1024,
  height: 711,
  foreground: Object.freeze({
    sourceWidth: 1280,
    sourceHeight: 720,
    contentBounds: Object.freeze({ left: 0, top: 0, right: 1024, bottom: 711 }),
    meaningfulContentBounds: Object.freeze({
      left: 0,
      top: 425,
      right: 1024,
      bottom: 654,
    }),
    contactStrip: Object.freeze({ top: 609, bottom: 654 }),
    contactSourceY: 653,
    repeatPeriod: 1024,
    overlap: 256,
  }),
});

const LEGACY_LAYERS: readonly SceneLayerManifestInput[] = Object.freeze([
  Object.freeze({
    id: "foreground",
    z_index: 30,
    parallax: NEAR_FOREGROUND_DEPTH_COEFFICIENT,
    opaque: false,
  }),
  Object.freeze({ id: "sky", z_index: 0, parallax: 0, opaque: true }),
  Object.freeze({ id: "ridges", z_index: 10, parallax: 0.25, opaque: false }),
  Object.freeze({ id: "ruins", z_index: 20, parallax: 0.7, opaque: false }),
]);

function projectedScreenBounds(
  x: number,
  y: number,
  scale: number,
  zoom: number,
  width: number,
  height: number,
  context = CONTEXT,
) {
  const centerX = context.viewportWidth / 2;
  const centerY = context.viewportHeight / 2;
  const left = centerX + (x - centerX) * zoom;
  const top = centerY + (y - centerY) * zoom;
  return {
    left,
    top,
    right: left + width * scale * zoom,
    bottom: top + height * scale * zoom,
  };
}

function renderedState(
  contract: SceneLayerContract,
  layout: SceneLayerLayout,
  context: SceneLayerContext = CONTEXT,
  visible = true,
): SceneLayerRenderState {
  return Object.freeze({
    x: layout.x,
    y: layout.y,
    scaleX: layout.scale,
    scaleY: layout.scale,
    displayWidth: layout.renderWidth * layout.scale,
    displayHeight: layout.renderHeight * layout.scale,
    originX: 0,
    originY: 0,
    scrollFactorX: 0,
    scrollFactorY: 0,
    tilePositionX: layout.tilePositionX,
    tilePositionY: 0,
    tileScaleX: layout.textureScale,
    tileScaleY: layout.textureScale,
    visible,
    depth: contract.renderDepth,
    spriteCount: contract.repeat === "repeat-x-seam-overlap" ? 2 : 1,
    textureWidth: layout.textureWidth,
    textureHeight: layout.textureHeight,
    clipBounds: Object.freeze({
      left: 0,
      top: 0,
      right: context.viewportWidth,
      bottom: context.viewportHeight,
    }),
  });
}

function signedCircularDelta(
  from: number,
  to: number,
  period: number,
): number {
  return (((to - from + period / 2) % period) + period) % period - period / 2;
}

describe("semantic scene layer contracts", () => {
  test("publishes the canonical back-to-front stack and content depth bands", () => {
    expect(CANONICAL_SCENE_STACK).toEqual([
      { kind: "sky", coordinateSpace: "screen", renderDepth: 0 },
      { kind: "distant", coordinateSpace: "parallax", renderDepth: 100 },
      { kind: "midground", coordinateSpace: "parallax", renderDepth: 200 },
      { kind: "world-terrain", coordinateSpace: "world", renderDepth: 500 },
      { kind: "actors-effects", coordinateSpace: "world", renderDepth: 700 },
      { kind: "near-foreground", coordinateSpace: "parallax", renderDepth: 1200 },
      { kind: "screen-hud", coordinateSpace: "screen", renderDepth: 2000 },
    ]);
    expect(SCENE_CONTENT_DEPTH).toEqual({
      terrain: SCENE_LAYER_DEPTH.worldTerrain,
      portal: 720,
      prop: 740,
      mob: 800,
      item: 850,
      player: 900,
      effect: 950,
      actorHud: 1300,
      hud: SCENE_LAYER_DEPTH.screenHud,
    });
  });

  test("adapts legacy world layers into canonical semantic contracts", () => {
    const layers = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT);
    expect(layers.map(({ id, kind, renderDepth }) => ({ id, kind, renderDepth }))).toEqual([
      { id: "sky", kind: "sky", renderDepth: 0 },
      { id: "ridges", kind: "distant", renderDepth: 100 },
      { id: "ruins", kind: "midground", renderDepth: 200 },
      { id: "foreground", kind: "near-foreground", renderDepth: 1200 },
    ]);
    expect(layers.at(-1)).toMatchObject({
      coordinateSpace: "parallax",
      anchor: "screen-ground-left",
      baseline: "screen-ground",
      repeat: "repeat-x-overlap-add",
      cull: "never",
      opacity: { mode: "source-alpha", alpha: 1 },
      blend: "normal",
      depthCoefficient: NEAR_FOREGROUND_DEPTH_COEFFICIENT,
      safeBounds: { left: 0, top: 540, right: 1280, bottom: 720 },
      placement: {
        mode: "screen-ground-contact-strip",
        snap: "screen-pixels",
      },
    });
    expect(
      sceneLayerTextureScale(layers.at(-1)!, FOREGROUND_ASSET, CONTEXT),
    ).toBeCloseTo(164 / 228, 12);
    expect(() =>
      sceneLayerTextureScale(
        layers.at(-1)!,
        { width: 1280, height: 0 },
        CONTEXT,
      ),
    ).toThrow("dimensions must be positive integers");
  });

  test("anchors measured foreground contact below the actor-safe lane", () => {
    const layers = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT);
    const sky = layers[0]!;
    const skyLayout = layoutSceneLayer(
      sky,
      { scrollX: 101.7, scrollY: 0, zoom: 1.2 },
      CONTEXT,
      { width: 1280, height: 720 },
      2,
    );
    expect(
      projectedScreenBounds(
        skyLayout.x,
        skyLayout.y,
        skyLayout.scale,
        1.2,
        skyLayout.renderWidth,
        skyLayout.renderHeight,
      ),
    ).toEqual(sky.safeBounds);

    const foreground = layers.at(-1)!;
    for (const zoom of [1, 1.2]) {
      for (const devicePixelRatio of [1, 2]) {
        const layout = layoutSceneLayer(
          foreground,
          { scrollX: 101.7, scrollY: 17, zoom },
          CONTEXT,
          FOREGROUND_ASSET,
          devicePixelRatio,
        );
        const probe = sceneLayerProbe(
          foreground,
          layout,
          { scrollX: 101.7, scrollY: 17, zoom },
          renderedState(foreground, layout),
        );
        expect(probe.foreground?.contactScreenY).toBeCloseTo(704, 0);
        expect(
          probe.foreground!.meaningfulContentScreenBounds.top,
        ).toBeGreaterThanOrEqual(540 - 0.5 / devicePixelRatio);
        expect(probe.foreground?.clipBounds).toEqual({
          left: 0,
          top: 0,
          right: 1280,
          bottom: 720,
        });
        expect(probe.foreground?.spriteCount).toBe(1);
        expect(
          Math.abs(
            probe.foreground!.phaseDevicePixels -
              Math.round(probe.foreground!.phaseDevicePixels),
          ),
        ).toBeLessThan(1e-9);
        const projected = projectedScreenBounds(
          layout.x,
          layout.y,
          layout.scale,
          zoom,
          layout.renderWidth,
          layout.renderHeight,
        );
        expect(projected.top).toBeCloseTo(layout.screenBounds.top, 10);
        expect(projected.bottom).toBeCloseTo(layout.screenBounds.bottom, 10);
      }
    }
  });

  test("keeps phase stable across long traversal and repeat re-entry", () => {
    const foreground = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT).at(-1)!;
    const scale = sceneLayerTextureScale(foreground, FOREGROUND_ASSET, CONTEXT);
    for (const devicePixelRatio of [1, 2]) {
      const first = layoutSceneLayer(
        foreground,
        { scrollX: -98_765.4321, scrollY: 0, zoom: 1.2 },
        CONTEXT,
        FOREGROUND_ASSET,
        devicePixelRatio,
      );
      const reentered = layoutSceneLayer(
        foreground,
        {
          scrollX:
            -98_765.4321 +
            (1024 * scale) /
              (1.2 * foreground.depthCoefficient),
          scrollY: 0,
          zoom: 1.2,
        },
        CONTEXT,
        FOREGROUND_ASSET,
        devicePixelRatio,
      );
      expect(reentered.tilePositionX).toBeCloseTo(first.tilePositionX, 9);
      expect(first.foreground?.phaseDevicePixels).toBe(
        reentered.foreground?.phaseDevicePixels,
      );
      const snappedDevicePhase =
        snapForegroundPhase(1_000_000.125, scale, devicePixelRatio, 1024) *
        scale *
        devicePixelRatio;
      expect(
        Math.abs(snappedDevicePhase - Math.round(snappedDevicePhase)),
      ).toBeLessThan(1e-9);
    }
  });

  test("moves the foreground at a scale-, zoom-, and DPR-invariant 1.8x terrain speed", () => {
    const contexts = [
      CONTEXT,
      Object.freeze({
        viewportWidth: 960,
        viewportHeight: 540,
        worldWidth: 9_600,
        groundBaselineY: 540,
        foregroundContactScreenY: 528,
        foregroundSafeBandTopY: 405,
        foregroundMaxScale: 0.5625,
      }),
    ] as const;
    for (const context of contexts) {
      const foreground = resolveSceneLayerStack(LEGACY_LAYERS, context).at(-1)!;
      for (const zoom of [1, 1.2]) {
        for (const devicePixelRatio of [1, 1.25, 2, 3, 4]) {
          const first = layoutSceneLayer(
            foreground,
            { scrollX: 100, scrollY: -128, zoom },
            context,
            FOREGROUND_ASSET,
            devicePixelRatio,
          ).foreground!;
          const second = layoutSceneLayer(
            foreground,
            { scrollX: 200, scrollY: -128, zoom },
            context,
            FOREGROUND_ASSET,
            devicePixelRatio,
          ).foreground!;
          const phaseTravel = signedCircularDelta(
            first.observedPhaseScreenPx,
            second.observedPhaseScreenPx,
            first.seamPeriodScreenPx,
          );
          const terrainTravel = 100 * zoom;
          expect(
            Math.abs(
              phaseTravel -
                terrainTravel * NEAR_FOREGROUND_DEPTH_COEFFICIENT,
            ),
          ).toBeLessThanOrEqual(1 / devicePixelRatio + 1e-9);
          expect(phaseTravel).toBeGreaterThan(terrainTravel * 1.75);
          expect(second.projectedCameraTravelScreenPx).toBe(
            200 * zoom * NEAR_FOREGROUND_DEPTH_COEFFICIENT,
          );
        }
      }
    }
  });

  test("uses the signed closed-form phase for negative, long, wrap, and zoomed travel", () => {
    const foreground = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT).at(-1)!;
    const scale = sceneLayerTextureScale(foreground, FOREGROUND_ASSET, CONTEXT);
    for (const zoom of [1, 1.2]) {
      for (const devicePixelRatio of [1, 2, 3, 4]) {
        const periodWorld =
          (1024 * scale) /
          (zoom * NEAR_FOREGROUND_DEPTH_COEFFICIENT);
        const origin = foregroundPhaseForCamera(
          { scrollX: 0, scrollY: 0, zoom },
          foreground.depthCoefficient,
          scale,
          devicePixelRatio,
          1024,
        );
        const reentered = foregroundPhaseForCamera(
          { scrollX: periodWorld, scrollY: -512, zoom },
          foreground.depthCoefficient,
          scale,
          devicePixelRatio,
          1024,
        );
        expect(reentered.phaseSourcePx).toBeCloseTo(origin.phaseSourcePx, 9);
        for (const scrollX of [
          -100,
          -98_765.4321,
          periodWorld - 1e-4,
          periodWorld + 1e-4,
          1_000_000.125,
        ]) {
          const phase = foregroundPhaseForCamera(
            { scrollX, scrollY: -37.6666666667, zoom },
            foreground.depthCoefficient,
            scale,
            devicePixelRatio,
            1024,
          );
          expect(Number.isFinite(phase.phaseSourcePx)).toBeTrue();
          expect(phase.phaseSourcePx).toBeGreaterThanOrEqual(0);
          expect(phase.phaseSourcePx).toBeLessThan(1024);
          expect(
            phase.phaseSourcePx * scale * devicePixelRatio,
          ).toBeCloseTo(
            Math.round(phase.phaseSourcePx * scale * devicePixelRatio),
            9,
          );
        }
        const negative = foregroundPhaseForCamera(
          { scrollX: -100, scrollY: 0, zoom },
          foreground.depthCoefficient,
          scale,
          devicePixelRatio,
          1024,
        );
        expect(
          signedCircularDelta(
            origin.phaseScreenPx,
            negative.phaseScreenPx,
            1024 * scale,
          ),
        ).toBeCloseTo(
          -100 * zoom * NEAR_FOREGROUND_DEPTH_COEFFICIENT,
          0,
        );
      }
    }
  });

  test("keeps vertical anchoring independent of scrollY while render depth and motion depth vary independently", () => {
    const foreground = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT).at(-1)!;
    for (const zoom of [1, 1.2]) {
      for (const devicePixelRatio of [1, 2, 3, 4]) {
        const layouts = [0, -128, -512].map((scrollY) =>
          layoutSceneLayer(
            foreground,
            { scrollX: 321.25, scrollY, zoom },
            CONTEXT,
            FOREGROUND_ASSET,
            devicePixelRatio,
          ),
        );
        expect(new Set(layouts.map((layout) => layout.tilePositionX)).size).toBe(
          1,
        );
        expect(new Set(layouts.map((layout) => layout.y)).size).toBe(1);
        expect(
          new Set(
            layouts.map((layout) => layout.foreground!.contactScreenY),
          ).size,
        ).toBe(1);
        for (const layout of layouts) {
          expect(layout.foreground!.clipBounds).toEqual({
            left: 0,
            top: 0,
            right: 1280,
            bottom: 720,
          });
          expect(
            layout.foreground!.meaningfulContentScreenBounds.top,
          ).toBeGreaterThanOrEqual(540 - 0.5 / devicePixelRatio);
        }
      }
    }
    const camera = { scrollX: 240, scrollY: -128, zoom: 1 } as const;
    const base = layoutSceneLayer(
      foreground,
      camera,
      CONTEXT,
      FOREGROUND_ASSET,
      2,
    );
    const movedPainter = layoutSceneLayer(
      { ...foreground, renderDepth: 1234 },
      camera,
      CONTEXT,
      FOREGROUND_ASSET,
      2,
    );
    const movedPlane = layoutSceneLayer(
      { ...foreground, depthCoefficient: 1.9 },
      camera,
      CONTEXT,
      FOREGROUND_ASSET,
      2,
    );
    expect(movedPainter.tilePositionX).toBe(base.tilePositionX);
    expect(movedPlane.tilePositionX).not.toBe(base.tilePositionX);
    expect(movedPlane.foreground!.depthCoefficient).toBe(1.9);
    expect(foreground.renderDepth).toBe(1200);
  });

  test("rejects a correlated live phase based on the removed source-pixel formula", () => {
    const foreground = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT).at(-1)!;
    const camera = { scrollX: 941.25, scrollY: -101.6666666667, zoom: 1.2 };
    const canonical = layoutSceneLayer(
      foreground,
      camera,
      CONTEXT,
      FOREGROUND_ASSET,
      2,
    );
    const oldPhase = snapForegroundPhase(
      camera.scrollX * foreground.depthCoefficient,
      canonical.textureScale,
      2,
      1024,
    );
    const forgedForeground = Object.freeze({
      ...canonical.foreground!,
      phaseSourcePx: oldPhase,
      observedPhaseScreenPx: oldPhase * canonical.textureScale,
      phaseDevicePixels: oldPhase * canonical.textureScale * 2,
    });
    const forged = Object.freeze({
      ...canonical,
      tilePositionX: oldPhase,
      foreground: forgedForeground,
    });
    const live = { ...renderedState(foreground, forged), tilePositionX: oldPhase };
    expect(() => sceneLayerProbe(foreground, forged, camera, live)).toThrow(
      "physical phase",
    );
  });

  test("preserves the contact and safe-band contract at an alternate viewport", () => {
    const alternate: SceneLayerContext = Object.freeze({
      viewportWidth: 960,
      viewportHeight: 540,
      worldWidth: 9_600,
      groundBaselineY: 540,
      foregroundContactScreenY: 528,
      foregroundSafeBandTopY: 405,
      foregroundMaxScale: 0.5625,
    });
    const foreground = resolveSceneLayerStack(LEGACY_LAYERS, alternate).at(-1)!;
    for (const zoom of [1, 1.2]) {
      for (const devicePixelRatio of [1, 2]) {
        const layout = layoutSceneLayer(
          foreground,
          { scrollX: 12_345.67, scrollY: 99, zoom },
          alternate,
          FOREGROUND_ASSET,
          devicePixelRatio,
        );
        const probe = sceneLayerProbe(
          foreground,
          layout,
          { scrollX: 12_345.67, scrollY: 99, zoom },
          renderedState(foreground, layout, alternate),
        ).foreground!;
        expect(probe.contactScreenY).toBeCloseTo(528, 0);
        expect(probe.meaningfulContentScreenBounds.top).toBeGreaterThanOrEqual(
          405 - 0.5 / devicePixelRatio,
        );
        expect(probe.clipBounds.right).toBe(960);
        expect(probe.clipBounds.bottom).toBe(540);
        expect(probe.spriteCount).toBe(1);
      }
    }
  });

  test("accepts an explicit contract only when it is the canonical adapter result", () => {
    const inferred = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT);
    const explicit = LEGACY_LAYERS.map((layer) => ({
      ...layer,
      scene_layer: inferred.find((candidate) => candidate.id === layer.id),
    }));
    expect(resolveSceneLayerStack(explicit, CONTEXT)).toEqual(inferred);

    const floating = structuredClone(explicit) as {
      id: string;
      z_index: number;
      parallax: number;
      opaque: boolean;
      scene_layer: { safeBounds: { bottom: number } };
    }[];
    const foreground = floating.find((layer) => layer.id === "foreground")!;
    foreground.scene_layer.safeBounds.bottom = 680;
    expect(() => resolveSceneLayerStack(floating, CONTEXT)).toThrow(
      "must match its canonical placement",
    );
  });

  test("rejects live partner, position, and phase mutations hidden by a planned layout", () => {
    const foreground = resolveSceneLayerStack(LEGACY_LAYERS, CONTEXT).at(-1)!;
    const layout = layoutSceneLayer(
      foreground,
      { scrollX: 941.25, scrollY: 0, zoom: 1.2 },
      CONTEXT,
      FOREGROUND_ASSET,
      2,
    );
    const live = renderedState(foreground, layout);
    const camera = { scrollX: 941.25, scrollY: 0, zoom: 1.2 } as const;
    expect(() => sceneLayerProbe(foreground, layout, camera, live)).not.toThrow();
    for (const mutation of [
      { ...live, spriteCount: 2 },
      { ...live, y: live.y + 24 },
      { ...live, tilePositionX: live.tilePositionX + 1 },
    ]) {
      expect(() => sceneLayerProbe(foreground, layout, camera, mutation)).toThrow(
        "live render state diverges",
      );
    }
  });

  test("rejects ambiguous sky, duplicate ids, and invalid depth bindings", () => {
    expect(() =>
      resolveSceneLayerStack(
        LEGACY_LAYERS.filter((layer) => layer.id !== "sky"),
        CONTEXT,
      ),
    ).toThrow("exactly one sky");
    expect(() =>
      resolveSceneLayerStack([...LEGACY_LAYERS, LEGACY_LAYERS[0]!], CONTEXT),
    ).toThrow("unique stable text");
    expect(() =>
      resolveSceneLayerStack(
        LEGACY_LAYERS.map((layer) =>
          layer.id === "ridges" ? { ...layer, id: "../ridges" } : layer,
        ),
        CONTEXT,
      ),
    ).toThrow("unique stable text");
    expect(() =>
      resolveSceneLayerStack(
        LEGACY_LAYERS.map((layer) =>
          layer.id === "ridges" ? { ...layer, z_index: -1 } : layer,
        ),
        CONTEXT,
      ),
    ).toThrow("z_index must be nonnegative");
    expect(() =>
      resolveSceneLayerStack(
        LEGACY_LAYERS.map((layer) =>
          layer.id === "ruins"
            ? { ...layer, scene_layer: { kind: "world-terrain" } }
            : layer,
        ),
        CONTEXT,
      ),
    ).toThrow("cannot bind generated art to world-terrain");
  });
});
