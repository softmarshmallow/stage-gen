export type SceneLayerKind =
  | "sky"
  | "distant"
  | "midground"
  | "world-terrain"
  | "actors-effects"
  | "near-foreground"
  | "screen-hud";

export type SceneCoordinateSpace = "screen" | "world" | "parallax";
export type SceneLayerAnchor =
  | "viewport-top-left"
  | "world-ground-left"
  | "world-ground-center"
  | "screen-ground-left"
  | "screen-top-left";
export type SceneLayerBaseline =
  "viewport-top" | "world-ground" | "screen-ground" | "none";
export type SceneLayerRepeat =
  | "none"
  | "repeat-x"
  | "repeat-x-seam-overlap"
  | "repeat-x-overlap-add"
  | "repeat-x-verified";
export type SceneLayerCull = "viewport" | "world-bounds" | "never";
export type SceneLayerOpacity = "opaque" | "source-alpha";
export type SceneLayerBlend = "normal" | "multiply" | "screen" | "add";
export type SceneLayerPlacement =
  | "viewport-cover"
  | "grounded-viewport-cover"
  | "screen-ground-contact-strip"
  | "world-grid"
  | "world-anchor"
  | "screen-fixed";

export type SceneLayerBounds = Readonly<{
  left: number;
  top: number;
  right: number;
  bottom: number;
}>;

export type SceneLayerContract = Readonly<{
  id: string;
  kind: SceneLayerKind;
  coordinateSpace: SceneCoordinateSpace;
  anchor: SceneLayerAnchor;
  baseline: SceneLayerBaseline;
  /** Painter order only. This does not control projected motion. */
  renderDepth: number;
  /** Horizontal screen-velocity ratio relative to the gameplay plane. */
  depthCoefficient: number;
  repeat: SceneLayerRepeat;
  cull: SceneLayerCull;
  opacity: Readonly<{ mode: SceneLayerOpacity; alpha: number }>;
  blend: SceneLayerBlend;
  safeBounds: SceneLayerBounds;
  placement: Readonly<{
    mode: SceneLayerPlacement;
    snap: "screen-pixels";
  }>;
}>;

export type SceneLayerManifestInput = Readonly<{
  id: string;
  z_index: number;
  parallax: number;
  opaque: boolean;
  scene_layer?: unknown;
}>;

export type SceneLayerContext = Readonly<{
  viewportWidth: number;
  viewportHeight: number;
  worldWidth: number;
  groundBaselineY: number;
  foregroundContactScreenY: number;
  foregroundSafeBandTopY: number;
  foregroundMaxScale: number;
}>;

export type SceneLayerCamera = Readonly<{
  scrollX: number;
  scrollY: number;
  zoom: number;
}>;

export type SceneLayerLayout = Readonly<{
  x: number;
  y: number;
  scale: number;
  tilePositionX: number;
  screenBounds: SceneLayerBounds;
  renderWidth: number;
  renderHeight: number;
  textureScale: number;
  textureWidth: number;
  textureHeight: number;
  foreground: SceneLayerForegroundLayout | null;
}>;

/** Values read back from the live Phaser objects after applying a layout. */
export type SceneLayerRenderState = Readonly<{
  x: number;
  y: number;
  scaleX: number;
  scaleY: number;
  displayWidth: number;
  displayHeight: number;
  originX: number;
  originY: number;
  scrollFactorX: number;
  scrollFactorY: number;
  tilePositionX: number;
  tilePositionY: number;
  tileScaleX: number;
  tileScaleY: number;
  visible: boolean;
  depth: number;
  spriteCount: number;
  textureWidth: number;
  textureHeight: number;
  clipBounds: SceneLayerBounds;
}>;

export type SceneLayerImageRepeatSelection = Readonly<{
  schemaVersion: 2;
  axis: "x";
  decision: "admitted" | "repaired";
  sourcePath: string;
  repeatUnitPath: string;
  periodPx: number;
}>;

export type SceneLayerImageRepeatProbe = SceneLayerImageRepeatSelection &
  Readonly<{
    selected: "verified-v2";
    unverifiedFallbackApplied: false;
    partnerSpriteCount: number;
  }>;

export type SceneLayerAssetMetadata = Readonly<{
  width: number;
  height: number;
  foreground?: SceneLayerForegroundAssetMetadata;
}>;

export type SceneLayerForegroundAssetMetadata = Readonly<{
  sourceWidth: number;
  sourceHeight: number;
  contentBounds: SceneLayerBounds;
  meaningfulContentBounds: SceneLayerBounds;
  contactStrip: Readonly<{ top: number; bottom: number }>;
  contactSourceY: number;
  repeatPeriod: number;
  overlap: number;
}>;

export type SceneLayerForegroundLayout = Readonly<{
  sourceContentBounds: SceneLayerBounds;
  meaningfulContentSourceBounds: SceneLayerBounds;
  contentScreenBounds: SceneLayerBounds;
  meaningfulContentScreenBounds: SceneLayerBounds;
  contactStripSource: Readonly<{ top: number; bottom: number }>;
  contactStripScreen: Readonly<{ top: number; bottom: number }>;
  contactSourceY: number;
  contactScreenY: number;
  clipBounds: SceneLayerBounds;
  repeatPeriodSourcePx: number;
  overlapSourcePx: number;
  sourceScaleScreenX: number;
  sourceScaleScreenY: number;
  depthCoefficient: number;
  projectedCameraTravelScreenPx: number;
  phaseSourcePx: number;
  observedPhaseScreenPx: number;
  phaseDevicePixels: number;
  devicePixelRatio: number;
  seamScreenX: number;
  seamPeriodScreenPx: number;
  spriteCount: number;
}>;

export type SceneLayerProbe = Readonly<{
  id: string;
  kind: SceneLayerKind;
  coordinateSpace: SceneCoordinateSpace;
  anchor: SceneLayerAnchor;
  baseline: SceneLayerBaseline;
  renderDepth: number;
  depthCoefficient: number;
  repeat: SceneLayerRepeat;
  cull: SceneLayerCull;
  opacity: SceneLayerOpacity;
  blend: SceneLayerBlend;
  placement: SceneLayerPlacement;
  safeBounds: SceneLayerBounds;
  screenBounds: SceneLayerBounds;
  tilePositionX: number;
  cameraScrollX: number;
  cameraScrollY: number;
  cameraZoom: number;
  integerScreenBounds: boolean;
  render: SceneLayerRenderState & Readonly<{ displayBounds: SceneLayerBounds }>;
  foreground: SceneLayerForegroundLayout | null;
  /** Present only when the promoted v2 repeat unit is selected. */
  imageRepeat?: SceneLayerImageRepeatProbe;
}>;

/** Browser-local near-plane screen velocity relative to the gameplay plane. */
export const NEAR_FOREGROUND_DEPTH_COEFFICIENT = 1.8;

export const CANONICAL_SCENE_STACK = Object.freeze([
  Object.freeze({ kind: "sky", coordinateSpace: "screen", renderDepth: 0 }),
  Object.freeze({ kind: "distant", coordinateSpace: "parallax", renderDepth: 100 }),
  Object.freeze({ kind: "midground", coordinateSpace: "parallax", renderDepth: 200 }),
  Object.freeze({
    kind: "world-terrain",
    coordinateSpace: "world",
    renderDepth: 500,
  }),
  Object.freeze({
    kind: "actors-effects",
    coordinateSpace: "world",
    renderDepth: 700,
  }),
  Object.freeze({
    kind: "near-foreground",
    coordinateSpace: "parallax",
    renderDepth: 1200,
  }),
  Object.freeze({ kind: "screen-hud", coordinateSpace: "screen", renderDepth: 2000 }),
] satisfies readonly Readonly<{
  kind: SceneLayerKind;
  coordinateSpace: SceneCoordinateSpace;
  renderDepth: number;
}>[]);

const ENUM_VALUES = Object.freeze({
  kind: CANONICAL_SCENE_STACK.map((entry) => entry.kind),
  coordinateSpace: ["screen", "world", "parallax"],
  anchor: [
    "viewport-top-left",
    "world-ground-left",
    "world-ground-center",
    "screen-ground-left",
    "screen-top-left",
  ],
  baseline: ["viewport-top", "world-ground", "screen-ground", "none"],
  repeat: ["none", "repeat-x", "repeat-x-seam-overlap", "repeat-x-overlap-add"],
  cull: ["viewport", "world-bounds", "never"],
  opacity: ["opaque", "source-alpha"],
  blend: ["normal", "multiply", "screen", "add"],
  placement: [
    "viewport-cover",
    "grounded-viewport-cover",
    "screen-ground-contact-strip",
    "world-grid",
    "world-anchor",
    "screen-fixed",
  ],
} as const);

function record(
  value: unknown,
  label: string,
): Readonly<Record<string, unknown>> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Readonly<Record<string, unknown>>;
}

function finiteInteger(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value))
    throw new Error(`${label} must be a safe integer`);
  return value as number;
}

function finiteNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be finite`);
  }
  return value;
}

function enumValue<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  label: string,
): T[number] {
  if (typeof value !== "string" || !allowed.includes(value as T[number])) {
    throw new Error(`${label} is unsupported`);
  }
  return value as T[number];
}

function validateContext(context: SceneLayerContext): void {
  for (const [label, value] of Object.entries({
    viewportWidth: context.viewportWidth,
    viewportHeight: context.viewportHeight,
    worldWidth: context.worldWidth,
    groundBaselineY: context.groundBaselineY,
    foregroundContactScreenY: context.foregroundContactScreenY,
    foregroundSafeBandTopY: context.foregroundSafeBandTopY,
  })) {
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw new Error(`scene layer ${label} must be a positive integer`);
    }
  }
  if (context.groundBaselineY > context.viewportHeight) {
    throw new Error("scene layer ground baseline must be inside the viewport");
  }
  if (
    context.foregroundSafeBandTopY >= context.foregroundContactScreenY ||
    context.foregroundContactScreenY > context.viewportHeight
  ) {
    throw new Error(
      "scene layer foreground safe band must end before its screen contact",
    );
  }
  if (
    !Number.isFinite(context.foregroundMaxScale) ||
    context.foregroundMaxScale <= 0 ||
    context.foregroundMaxScale > 1
  ) {
    throw new Error(
      "scene layer foreground maximum scale must be within (0, 1]",
    );
  }
}

function inferKind(layer: SceneLayerManifestInput): SceneLayerKind {
  if (layer.id === "sky" || layer.opaque) return "sky";
  if (layer.parallax > 1) return "near-foreground";
  if (layer.parallax <= 0.5) return "distant";
  return "midground";
}

function depthBase(kind: SceneLayerKind): number {
  const entry = CANONICAL_SCENE_STACK.find(
    (candidate) => candidate.kind === kind,
  );
  if (!entry)
    throw new Error(`scene layer kind ${kind} has no canonical depth`);
  return entry.renderDepth;
}

function canonicalLayer(
  layer: SceneLayerManifestInput,
  kind: SceneLayerKind,
  ordinal: number,
  context: SceneLayerContext,
): SceneLayerContract {
  if (ordinal < 0 || ordinal >= 50) {
    throw new Error(`${kind} exceeds its canonical depth band`);
  }
  if (kind === "sky" && (!layer.opaque || layer.parallax !== 0)) {
    throw new Error("sky must be opaque with zero depth coefficient");
  }
  if (
    (kind === "distant" || kind === "midground") &&
    (layer.opaque || layer.parallax <= 0 || layer.parallax > 1)
  ) {
    throw new Error(`${kind} must be alpha-bearing parallax within (0, 1]`);
  }
  if (kind === "near-foreground" && (layer.opaque || layer.parallax <= 1)) {
    throw new Error("near foreground must be alpha-bearing parallax above 1");
  }
  const sky = kind === "sky";
  const foreground = kind === "near-foreground";
  const safeBounds = sky
    ? {
        left: 0,
        top: 0,
        right: context.viewportWidth,
        bottom: context.viewportHeight,
      }
    : foreground
      ? {
          left: 0,
          top: context.foregroundSafeBandTopY,
          right: context.viewportWidth,
          bottom: context.viewportHeight,
        }
      : {
          left: 0,
          top: context.groundBaselineY - context.viewportHeight,
          right: context.viewportWidth,
          bottom: context.groundBaselineY,
        };
  return Object.freeze({
    id: layer.id,
    kind,
    coordinateSpace: sky ? "screen" : "parallax",
    anchor: sky
      ? "viewport-top-left"
      : foreground
        ? "screen-ground-left"
        : "world-ground-left",
    baseline: sky
      ? "viewport-top"
      : foreground
        ? "screen-ground"
        : "world-ground",
    renderDepth: depthBase(kind) + ordinal,
    depthCoefficient: layer.parallax,
    repeat: layer.opaque
      ? "repeat-x"
      : foreground
        ? "repeat-x-overlap-add"
        : "repeat-x-seam-overlap",
    cull: foreground ? "never" : "viewport",
    opacity: Object.freeze({
      mode: layer.opaque ? "opaque" : "source-alpha",
      alpha: 1,
    }),
    blend: "normal",
    safeBounds: Object.freeze(safeBounds),
    placement: Object.freeze({
      mode: sky
        ? "viewport-cover"
        : foreground
          ? "screen-ground-contact-strip"
          : "grounded-viewport-cover",
      snap: "screen-pixels",
    }),
  });
}

function declaredLayer(
  raw: unknown,
  fallback: SceneLayerContract,
): SceneLayerContract {
  const value = record(raw, `${fallback.id}.scene_layer`);
  const opacity = record(value.opacity, `${fallback.id}.scene_layer.opacity`);
  const safeBounds = record(
    value.safeBounds,
    `${fallback.id}.scene_layer.safeBounds`,
  );
  const placement = record(
    value.placement,
    `${fallback.id}.scene_layer.placement`,
  );
  if (placement.snap !== "screen-pixels") {
    throw new Error(
      `${fallback.id}.scene_layer.placement.snap must be screen-pixels`,
    );
  }
  const parsed = Object.freeze({
    id: fallback.id,
    kind: enumValue(
      value.kind,
      ENUM_VALUES.kind,
      `${fallback.id}.scene_layer.kind`,
    ),
    coordinateSpace: enumValue(
      value.coordinateSpace,
      ENUM_VALUES.coordinateSpace,
      `${fallback.id}.scene_layer.coordinateSpace`,
    ),
    anchor: enumValue(
      value.anchor,
      ENUM_VALUES.anchor,
      `${fallback.id}.scene_layer.anchor`,
    ),
    baseline: enumValue(
      value.baseline,
      ENUM_VALUES.baseline,
      `${fallback.id}.scene_layer.baseline`,
    ),
    renderDepth: finiteInteger(
      value.renderDepth,
      `${fallback.id}.scene_layer.renderDepth`,
    ),
    depthCoefficient: finiteNumber(
      value.depthCoefficient,
      `${fallback.id}.scene_layer.depthCoefficient`,
    ),
    repeat: enumValue(
      value.repeat,
      ENUM_VALUES.repeat,
      `${fallback.id}.scene_layer.repeat`,
    ),
    cull: enumValue(
      value.cull,
      ENUM_VALUES.cull,
      `${fallback.id}.scene_layer.cull`,
    ),
    opacity: Object.freeze({
      mode: enumValue(
        opacity.mode,
        ENUM_VALUES.opacity,
        `${fallback.id}.scene_layer.opacity.mode`,
      ),
      alpha: finiteNumber(
        opacity.alpha,
        `${fallback.id}.scene_layer.opacity.alpha`,
      ),
    }),
    blend: enumValue(
      value.blend,
      ENUM_VALUES.blend,
      `${fallback.id}.scene_layer.blend`,
    ),
    safeBounds: Object.freeze({
      left: finiteInteger(
        safeBounds.left,
        `${fallback.id}.scene_layer.safeBounds.left`,
      ),
      top: finiteInteger(
        safeBounds.top,
        `${fallback.id}.scene_layer.safeBounds.top`,
      ),
      right: finiteInteger(
        safeBounds.right,
        `${fallback.id}.scene_layer.safeBounds.right`,
      ),
      bottom: finiteInteger(
        safeBounds.bottom,
        `${fallback.id}.scene_layer.safeBounds.bottom`,
      ),
    }),
    placement: Object.freeze({
      mode: enumValue(
        placement.mode,
        ENUM_VALUES.placement,
        `${fallback.id}.scene_layer.placement.mode`,
      ),
      snap: "screen-pixels" as const,
    }),
  } satisfies SceneLayerContract);
  const expected = JSON.stringify(fallback);
  if (JSON.stringify(parsed) !== expected) {
    throw new Error(
      `${fallback.id}.scene_layer must match its canonical placement`,
    );
  }
  return parsed;
}

export function resolveSceneLayerStack(
  layers: readonly SceneLayerManifestInput[],
  context: SceneLayerContext,
): readonly SceneLayerContract[] {
  validateContext(context);
  if (layers.length === 0)
    throw new Error("scene layer stack must not be empty");
  const ids = new Set<string>();
  const ordinals = new Map<SceneLayerKind, number>();
  const validated = layers.map((layer) => {
    if (!/^[a-z0-9_]+$/.test(layer.id) || ids.has(layer.id)) {
      throw new Error("scene layer ids must be unique stable text");
    }
    ids.add(layer.id);
    if (finiteInteger(layer.z_index, `${layer.id}.z_index`) < 0) {
      throw new Error(`${layer.id}.z_index must be nonnegative`);
    }
    const parallax = finiteNumber(layer.parallax, `${layer.id}.parallax`);
    if (parallax < 0 || parallax > 2) {
      throw new Error(`${layer.id}.parallax must be within [0, 2]`);
    }
    if (typeof layer.opaque !== "boolean") {
      throw new Error(`${layer.id}.opaque must be boolean`);
    }
    return layer;
  });
  const resolved = [...validated]
    .sort(
      (left, right) =>
        left.z_index - right.z_index || left.id.localeCompare(right.id),
    )
    .map((layer) => {
      const declaredKind =
        layer.scene_layer === undefined
          ? undefined
          : enumValue(
              record(layer.scene_layer, `${layer.id}.scene_layer`).kind,
              ENUM_VALUES.kind,
              `${layer.id}.scene_layer.kind`,
            );
      const kind = declaredKind ?? inferKind(layer);
      if (
        kind === "world-terrain" ||
        kind === "actors-effects" ||
        kind === "screen-hud"
      ) {
        throw new Error(`${layer.id} cannot bind generated art to ${kind}`);
      }
      const ordinal = ordinals.get(kind) ?? 0;
      ordinals.set(kind, ordinal + 1);
      const fallback = canonicalLayer(layer, kind, ordinal, context);
      return layer.scene_layer === undefined
        ? fallback
        : declaredLayer(layer.scene_layer, fallback);
    })
    .sort(
      (left, right) =>
        left.renderDepth - right.renderDepth || left.id.localeCompare(right.id),
    );
  const skyCount = resolved.filter((layer) => layer.kind === "sky").length;
  if (skyCount !== 1)
    throw new Error("scene layer stack requires exactly one sky");
  for (let index = 1; index < resolved.length; index += 1) {
    if (
      resolved[index - 1]!.renderDepth >= resolved[index]!.renderDepth
    ) {
      throw new Error("scene layer depth order must be strictly increasing");
    }
  }
  return Object.freeze(resolved);
}

/** Replace an unverified repeat mode with one verified exact X period. */
export function withVerifiedHorizontalRepeat(
  contract: SceneLayerContract,
): SceneLayerContract {
  if (contract.repeat === "none") {
    throw new Error(`${contract.id} cannot select an X repeat for a non-repeating layer`);
  }
  if (contract.repeat === "repeat-x-verified") return contract;
  return Object.freeze({ ...contract, repeat: "repeat-x-verified" });
}

export function layoutSceneLayer(
  contract: SceneLayerContract,
  camera: SceneLayerCamera,
  context: SceneLayerContext,
  asset: SceneLayerAssetMetadata,
  devicePixelRatio = 1,
): SceneLayerLayout {
  validateContext(context);
  if (
    contract.coordinateSpace === "world" ||
    (contract.placement.mode !== "viewport-cover" &&
      contract.placement.mode !== "grounded-viewport-cover" &&
      contract.placement.mode !== "screen-ground-contact-strip")
  ) {
    throw new Error(`${contract.id} is not a viewport-composited scene layer`);
  }
  if (
    !Number.isFinite(camera.scrollX) ||
    !Number.isFinite(camera.scrollY) ||
    !Number.isFinite(camera.zoom) ||
    camera.zoom <= 0
  ) {
    throw new Error(
      "scene layer camera values must be finite with positive zoom",
    );
  }
  if (
    !Number.isFinite(devicePixelRatio) ||
    devicePixelRatio < 1 ||
    devicePixelRatio > 8
  ) {
    throw new Error("scene layer device pixel ratio must be within [1, 8]");
  }
  const textureScale = sceneLayerTextureScale(contract, asset, context);
  let targetLeft = contract.safeBounds.left;
  let targetTop = contract.safeBounds.top;
  let renderWidth = contract.safeBounds.right - contract.safeBounds.left;
  let renderHeight = contract.safeBounds.bottom - contract.safeBounds.top;
  let screenBounds = contract.safeBounds;
  let tilePositionX = Math.round(camera.scrollX * contract.depthCoefficient);
  let foreground: SceneLayerForegroundLayout | null = null;
  if (contract.kind === "near-foreground") {
    const metadata = requireForegroundMetadata(contract, asset);
    targetLeft = 0;
    renderWidth = context.viewportWidth;
    // Phaser floors TileSprite constructor dimensions before applying its
    // camera-compensating object scale. Keep the layout contract aligned with
    // that live geometry while retaining the measured source-pixel scale.
    renderHeight = Math.floor(asset.height * textureScale);
    // A near foreground is cut off by the bottom of the frame, never suspended
    // above it. Anchoring the contact row is what places the layer, but the
    // anchor cannot guarantee coverage on its own: an asset whose contact row
    // is also its last painted row has nothing left to draw underneath, and the
    // floor above gives back up to a further pixel. Whatever the anchor asks
    // for, the painted bottom lands on the screen edge or below it.
    targetTop = Math.max(
      snapScreenPixel(
        context.foregroundContactScreenY -
          metadata.contactSourceY * textureScale,
        devicePixelRatio,
      ),
      context.viewportHeight - renderHeight,
    );
    screenBounds = Object.freeze({
      left: targetLeft,
      top: targetTop,
      right: targetLeft + renderWidth,
      bottom: targetTop + renderHeight,
    });
    const phase = foregroundPhaseForCamera(
      camera,
      contract.depthCoefficient,
      textureScale,
      devicePixelRatio,
      metadata.repeatPeriod,
    );
    tilePositionX = phase.phaseSourcePx;
    const contactScreenY = targetTop + metadata.contactSourceY * textureScale;
    const contentScreenBounds = projectForegroundBounds(
      metadata.contentBounds,
      targetTop,
      textureScale,
      context.viewportWidth,
    );
    const meaningfulContentScreenBounds = projectForegroundBounds(
      metadata.meaningfulContentBounds,
      targetTop,
      textureScale,
      context.viewportWidth,
    );
    const phaseDevicePixels = Math.round(
      tilePositionX * textureScale * devicePixelRatio,
    );
    const seamDistanceSource =
      tilePositionX === 0 ? 0 : metadata.repeatPeriod - tilePositionX;
    foreground = Object.freeze({
      sourceContentBounds: metadata.contentBounds,
      meaningfulContentSourceBounds: metadata.meaningfulContentBounds,
      contentScreenBounds,
      meaningfulContentScreenBounds,
      contactStripSource: metadata.contactStrip,
      contactStripScreen: Object.freeze({
        top: targetTop + metadata.contactStrip.top * textureScale,
        bottom: targetTop + metadata.contactStrip.bottom * textureScale,
      }),
      contactSourceY: metadata.contactSourceY,
      contactScreenY,
      clipBounds: Object.freeze({
        left: 0,
        top: 0,
        right: context.viewportWidth,
        bottom: context.viewportHeight,
      }),
      repeatPeriodSourcePx: metadata.repeatPeriod,
      overlapSourcePx: metadata.overlap,
      sourceScaleScreenX: textureScale,
      sourceScaleScreenY: textureScale,
      depthCoefficient: contract.depthCoefficient,
      projectedCameraTravelScreenPx:
        phase.projectedCameraTravelScreenPx,
      phaseSourcePx: tilePositionX,
      observedPhaseScreenPx: tilePositionX * textureScale,
      phaseDevicePixels,
      devicePixelRatio,
      seamScreenX: snapScreenPixel(
        seamDistanceSource * textureScale,
        devicePixelRatio,
      ),
      seamPeriodScreenPx: metadata.repeatPeriod * textureScale,
      spriteCount: 1,
    });
  }
  const centerX = context.viewportWidth / 2;
  const centerY = context.viewportHeight / 2;
  return Object.freeze({
    x: centerX + (targetLeft - centerX) / camera.zoom,
    y: centerY + (targetTop - centerY) / camera.zoom,
    scale: 1 / camera.zoom,
    tilePositionX,
    screenBounds,
    renderWidth,
    renderHeight,
    textureScale,
    textureWidth: asset.width,
    textureHeight: asset.height,
    foreground,
  });
}

function validBounds(
  bounds: SceneLayerBounds,
  width: number,
  height: number,
): boolean {
  return (
    Number.isSafeInteger(bounds.left) &&
    Number.isSafeInteger(bounds.top) &&
    Number.isSafeInteger(bounds.right) &&
    Number.isSafeInteger(bounds.bottom) &&
    bounds.left >= 0 &&
    bounds.top >= 0 &&
    bounds.right > bounds.left &&
    bounds.bottom > bounds.top &&
    bounds.right <= width &&
    bounds.bottom <= height
  );
}

function requireForegroundMetadata(
  contract: SceneLayerContract,
  asset: SceneLayerAssetMetadata,
): SceneLayerForegroundAssetMetadata {
  const metadata = asset.foreground;
  if (!metadata) {
    throw new Error(
      `${contract.id} foreground requires measured asset metadata`,
    );
  }
  const verifiedRepeat = contract.repeat === "repeat-x-verified";
  const repeatGeometryValid = verifiedRepeat
    ? metadata.repeatPeriod === asset.width &&
      metadata.repeatPeriod === metadata.sourceWidth &&
      metadata.sourceHeight === asset.height &&
      metadata.overlap === 0
    : metadata.repeatPeriod === asset.width &&
      metadata.repeatPeriod === metadata.sourceWidth - metadata.overlap &&
      metadata.overlap >= 2 &&
      metadata.overlap * 2 < metadata.sourceWidth;
  if (
    !Number.isSafeInteger(metadata.sourceWidth) ||
    !Number.isSafeInteger(metadata.sourceHeight) ||
    metadata.sourceWidth <= 0 ||
    metadata.sourceHeight <= 0 ||
    !Number.isSafeInteger(metadata.repeatPeriod) ||
    !Number.isSafeInteger(metadata.overlap) ||
    !repeatGeometryValid
  ) {
    throw new Error(`${contract.id} foreground repeat metadata is invalid`);
  }
  if (
    !validBounds(metadata.contentBounds, asset.width, asset.height) ||
    !validBounds(metadata.meaningfulContentBounds, asset.width, asset.height) ||
    metadata.meaningfulContentBounds.top < metadata.contentBounds.top ||
    metadata.meaningfulContentBounds.bottom > metadata.contentBounds.bottom ||
    !Number.isSafeInteger(metadata.contactStrip.top) ||
    !Number.isSafeInteger(metadata.contactStrip.bottom) ||
    metadata.contactStrip.top < metadata.contentBounds.top ||
    metadata.contactStrip.bottom <= metadata.contactStrip.top ||
    metadata.contactStrip.bottom > metadata.contentBounds.bottom ||
    metadata.contactSourceY !== metadata.contactStrip.bottom - 1 ||
    metadata.contactSourceY <= metadata.meaningfulContentBounds.top
  ) {
    throw new Error(`${contract.id} foreground measured bounds are invalid`);
  }
  return metadata;
}

function positiveModulo(value: number, period: number): number {
  return ((value % period) + period) % period;
}

function snapScreenPixel(value: number, devicePixelRatio: number): number {
  return Math.round(value * devicePixelRatio) / devicePixelRatio;
}

export type ForegroundPhaseProjection = Readonly<{
  projectedCameraTravelScreenPx: number;
  rawPhaseSourcePx: number;
  phaseSourcePx: number;
  phaseScreenPx: number;
}>;

/**
 * Resolve a closed-form foreground sampling phase. Positive camera X advances
 * the TileSprite sample phase, so painted features move left on screen. The
 * source-scale division and zoom multiplication keep that apparent movement
 * equal to `depthCoefficient` times gameplay-plane movement at every scale.
 */
export function foregroundPhaseForCamera(
  camera: SceneLayerCamera,
  depthCoefficient: number,
  textureScale: number,
  devicePixelRatio: number,
  repeatPeriod: number,
): ForegroundPhaseProjection {
  if (
    !Number.isFinite(camera.scrollX) ||
    !Number.isFinite(camera.scrollY) ||
    !Number.isFinite(camera.zoom) ||
    camera.zoom <= 0 ||
    !Number.isFinite(depthCoefficient) ||
    depthCoefficient <= 1 ||
    depthCoefficient > 2
  ) {
    throw new Error("foreground phase camera and coefficient are invalid");
  }
  const projectedCameraTravelScreenPx =
    camera.scrollX * camera.zoom * depthCoefficient;
  const rawPhaseSourcePx = positiveModulo(
    projectedCameraTravelScreenPx / textureScale,
    repeatPeriod,
  );
  const phaseSourcePx = snapForegroundPhase(
    rawPhaseSourcePx,
    textureScale,
    devicePixelRatio,
    repeatPeriod,
  );
  return Object.freeze({
    projectedCameraTravelScreenPx,
    rawPhaseSourcePx,
    phaseSourcePx,
    phaseScreenPx: phaseSourcePx * textureScale,
  });
}

export function snapForegroundPhase(
  rawPhase: number,
  textureScale: number,
  devicePixelRatio: number,
  repeatPeriod: number,
): number {
  if (
    !Number.isFinite(rawPhase) ||
    !Number.isFinite(textureScale) ||
    textureScale <= 0 ||
    !Number.isFinite(devicePixelRatio) ||
    devicePixelRatio < 1 ||
    !Number.isSafeInteger(repeatPeriod) ||
    repeatPeriod <= 0
  ) {
    throw new Error("foreground phase snapping inputs are invalid");
  }
  return snapSourcePhase(
    positiveModulo(rawPhase, repeatPeriod),
    textureScale,
    devicePixelRatio,
    repeatPeriod,
  );
}

function snapSourcePhase(
  normalizedPhase: number,
  textureScale: number,
  devicePixelRatio: number,
  repeatPeriod: number,
): number {
  const deviceScale = textureScale * devicePixelRatio;
  const snapped = Math.round(normalizedPhase * deviceScale) / deviceScale;
  return snapped >= repeatPeriod ? 0 : snapped;
}

function projectForegroundBounds(
  source: SceneLayerBounds,
  targetTop: number,
  textureScale: number,
  viewportWidth: number,
): SceneLayerBounds {
  return Object.freeze({
    left: 0,
    top: targetTop + source.top * textureScale,
    right: viewportWidth,
    bottom: targetTop + source.bottom * textureScale,
  });
}

/** Scale source pixels without distorting the layer's semantic placement. */
export function sceneLayerTextureScale(
  contract: SceneLayerContract,
  asset: SceneLayerAssetMetadata,
  context: SceneLayerContext,
): number {
  validateContext(context);
  if (
    !Number.isSafeInteger(asset.width) ||
    !Number.isSafeInteger(asset.height) ||
    asset.width <= 0 ||
    asset.height <= 0
  ) {
    throw new Error(
      `${contract.id} scene layer dimensions must be positive integers`,
    );
  }
  if (contract.kind === "near-foreground") {
    const metadata = requireForegroundMetadata(contract, asset);
    const safeSourceHeight =
      metadata.contactSourceY - metadata.meaningfulContentBounds.top;
    const safeScreenHeight =
      context.foregroundContactScreenY - context.foregroundSafeBandTopY;
    return Math.min(
      context.viewportWidth / metadata.sourceWidth,
      context.foregroundMaxScale,
      safeScreenHeight / safeSourceHeight,
    );
  }
  const safeHeight = contract.safeBounds.bottom - contract.safeBounds.top;
  if (!Number.isSafeInteger(safeHeight) || safeHeight <= 0) {
    throw new Error(`${contract.id} scene layer safe height must be positive`);
  }
  return safeHeight / asset.height;
}

export function sceneLayerProbe(
  contract: SceneLayerContract,
  layout: SceneLayerLayout,
  camera: SceneLayerCamera,
  rendered: SceneLayerRenderState,
  imageRepeat: SceneLayerImageRepeatSelection | null = null,
): SceneLayerProbe {
  const render = normalizeRenderedState(rendered, camera.zoom);
  const bounds = render.displayBounds;
  const foreground = observedForegroundLayout(
    contract,
    layout.foreground,
    render,
    camera,
  );
  assertRenderedLayout(contract, layout, render, foreground, camera);
  const probe = Object.freeze({
    id: contract.id,
    kind: contract.kind,
    coordinateSpace: contract.coordinateSpace,
    anchor: contract.anchor,
    baseline: contract.baseline,
    renderDepth: contract.renderDepth,
    depthCoefficient: contract.depthCoefficient,
    repeat: contract.repeat,
    cull: contract.cull,
    opacity: contract.opacity.mode,
    blend: contract.blend,
    placement: contract.placement.mode,
    safeBounds: contract.safeBounds,
    screenBounds: bounds,
    tilePositionX: render.tilePositionX,
    cameraScrollX: camera.scrollX,
    cameraScrollY: camera.scrollY,
    cameraZoom: camera.zoom,
    integerScreenBounds:
      foreground === null
        ? Object.values(bounds).every(isNearInteger)
        : isNearInteger(bounds.left * foreground.devicePixelRatio) &&
          isNearInteger(bounds.top * foreground.devicePixelRatio),
    render,
    foreground,
    ...(imageRepeat === null
      ? {}
      : {
          imageRepeat: Object.freeze({
            ...imageRepeat,
            selected: "verified-v2" as const,
            unverifiedFallbackApplied: false as const,
            partnerSpriteCount: Math.max(0, render.spriteCount - 1),
          }),
        }),
  });
  assertSceneLayerProbe(probe);
  return probe;
}

const RENDER_EPSILON = 1e-6;

function isNearInteger(value: number): boolean {
  return (
    Number.isFinite(value) &&
    Math.abs(value - Math.round(value)) <= RENDER_EPSILON
  );
}

function nearlyEqual(left: number, right: number): boolean {
  return (
    Number.isFinite(left) &&
    Number.isFinite(right) &&
    Math.abs(left - right) <=
      RENDER_EPSILON * Math.max(1, Math.abs(left), Math.abs(right))
  );
}

function finiteRenderBounds(
  bounds: SceneLayerBounds,
  label: string,
): SceneLayerBounds {
  if (
    !Number.isFinite(bounds.left) ||
    !Number.isFinite(bounds.top) ||
    !Number.isFinite(bounds.right) ||
    !Number.isFinite(bounds.bottom) ||
    bounds.right <= bounds.left ||
    bounds.bottom <= bounds.top
  ) {
    throw new Error(`${label} bounds are invalid`);
  }
  return Object.freeze({ ...bounds });
}

function normalizeRenderedState(
  rendered: SceneLayerRenderState,
  cameraZoom: number,
): SceneLayerProbe["render"] {
  if (!Number.isFinite(cameraZoom) || cameraZoom <= 0) {
    throw new Error("scene layer rendered camera zoom must be positive");
  }
  for (const [label, value] of Object.entries({
    x: rendered.x,
    y: rendered.y,
    scaleX: rendered.scaleX,
    scaleY: rendered.scaleY,
    displayWidth: rendered.displayWidth,
    displayHeight: rendered.displayHeight,
    originX: rendered.originX,
    originY: rendered.originY,
    scrollFactorX: rendered.scrollFactorX,
    scrollFactorY: rendered.scrollFactorY,
    tilePositionX: rendered.tilePositionX,
    tilePositionY: rendered.tilePositionY,
    tileScaleX: rendered.tileScaleX,
    tileScaleY: rendered.tileScaleY,
    depth: rendered.depth,
  })) {
    if (!Number.isFinite(value)) {
      throw new Error(`scene layer rendered ${label} must be finite`);
    }
  }
  if (
    rendered.scaleX <= 0 ||
    rendered.scaleY <= 0 ||
    rendered.displayWidth <= 0 ||
    rendered.displayHeight <= 0 ||
    rendered.tileScaleX <= 0 ||
    rendered.tileScaleY <= 0 ||
    typeof rendered.visible !== "boolean" ||
    !Number.isSafeInteger(rendered.depth) ||
    !Number.isSafeInteger(rendered.spriteCount) ||
    rendered.spriteCount <= 0 ||
    !Number.isSafeInteger(rendered.textureWidth) ||
    !Number.isSafeInteger(rendered.textureHeight) ||
    rendered.textureWidth <= 0 ||
    rendered.textureHeight <= 0
  ) {
    throw new Error("scene layer rendered state is invalid");
  }
  const clipBounds = finiteRenderBounds(
    rendered.clipBounds,
    "scene layer clip",
  );
  const centerX = (clipBounds.left + clipBounds.right) / 2;
  const centerY = (clipBounds.top + clipBounds.bottom) / 2;
  const localLeft = rendered.x - rendered.displayWidth * rendered.originX;
  const localTop = rendered.y - rendered.displayHeight * rendered.originY;
  const displayBounds = Object.freeze({
    left: centerX + (localLeft - centerX) * cameraZoom,
    top: centerY + (localTop - centerY) * cameraZoom,
    right: centerX + (localLeft + rendered.displayWidth - centerX) * cameraZoom,
    bottom:
      centerY + (localTop + rendered.displayHeight - centerY) * cameraZoom,
  });
  return Object.freeze({
    ...rendered,
    clipBounds,
    displayBounds,
  });
}

function projectedObservedBounds(
  source: SceneLayerBounds,
  displayBounds: SceneLayerBounds,
  sourceScaleScreenY: number,
): SceneLayerBounds {
  return Object.freeze({
    left: displayBounds.left,
    top: displayBounds.top + source.top * sourceScaleScreenY,
    right: displayBounds.right,
    bottom: displayBounds.top + source.bottom * sourceScaleScreenY,
  });
}

function observedForegroundLayout(
  contract: SceneLayerContract,
  planned: SceneLayerForegroundLayout | null,
  render: SceneLayerProbe["render"],
  camera: SceneLayerCamera,
): SceneLayerForegroundLayout | null {
  if (!planned) return null;
  const sourceScaleScreenX = render.tileScaleX * render.scaleX * camera.zoom;
  const sourceScaleScreenY = render.tileScaleY * render.scaleY * camera.zoom;
  const phaseSourcePx = render.tilePositionX;
  const seamDistanceSource =
    phaseSourcePx === 0 ? 0 : planned.repeatPeriodSourcePx - phaseSourcePx;
  return Object.freeze({
    sourceContentBounds: planned.sourceContentBounds,
    meaningfulContentSourceBounds: planned.meaningfulContentSourceBounds,
    contentScreenBounds: projectedObservedBounds(
      planned.sourceContentBounds,
      render.displayBounds,
      sourceScaleScreenY,
    ),
    meaningfulContentScreenBounds: projectedObservedBounds(
      planned.meaningfulContentSourceBounds,
      render.displayBounds,
      sourceScaleScreenY,
    ),
    contactStripSource: planned.contactStripSource,
    contactStripScreen: Object.freeze({
      top:
        render.displayBounds.top +
        planned.contactStripSource.top * sourceScaleScreenY,
      bottom:
        render.displayBounds.top +
        planned.contactStripSource.bottom * sourceScaleScreenY,
    }),
    contactSourceY: planned.contactSourceY,
    contactScreenY:
      render.displayBounds.top + planned.contactSourceY * sourceScaleScreenY,
    clipBounds: render.clipBounds,
    repeatPeriodSourcePx: planned.repeatPeriodSourcePx,
    overlapSourcePx: planned.overlapSourcePx,
    sourceScaleScreenX,
    sourceScaleScreenY,
    depthCoefficient: contract.depthCoefficient,
    projectedCameraTravelScreenPx:
      camera.scrollX * camera.zoom * contract.depthCoefficient,
    phaseSourcePx,
    observedPhaseScreenPx: phaseSourcePx * sourceScaleScreenX,
    phaseDevicePixels:
      phaseSourcePx * sourceScaleScreenX * planned.devicePixelRatio,
    devicePixelRatio: planned.devicePixelRatio,
    seamScreenX:
      render.displayBounds.left + seamDistanceSource * sourceScaleScreenX,
    seamPeriodScreenPx: planned.repeatPeriodSourcePx * sourceScaleScreenX,
    spriteCount: render.spriteCount,
  });
}

function assertBoundsMatch(
  actual: SceneLayerBounds,
  expected: SceneLayerBounds,
  label: string,
): void {
  for (const key of ["left", "top", "right", "bottom"] as const) {
    if (!nearlyEqual(actual[key], expected[key])) {
      throw new Error(`${label} ${key} diverges from applied layout`);
    }
  }
}

function assertRenderedLayout(
  contract: SceneLayerContract,
  layout: SceneLayerLayout,
  render: SceneLayerProbe["render"],
  foreground: SceneLayerForegroundLayout | null,
  camera: SceneLayerCamera,
): void {
  const expectedSpriteCount =
    contract.repeat === "repeat-x-seam-overlap" ? 2 : 1;
  const renderViolations: string[] = [];
  if (!nearlyEqual(render.x, layout.x)) renderViolations.push("x");
  if (!nearlyEqual(render.y, layout.y)) renderViolations.push("y");
  if (!nearlyEqual(render.scaleX, layout.scale)) {
    renderViolations.push("scale x");
  }
  if (!nearlyEqual(render.scaleY, layout.scale)) {
    renderViolations.push("scale y");
  }
  if (!nearlyEqual(render.displayWidth, layout.renderWidth * layout.scale)) {
    renderViolations.push("display width");
  }
  if (!nearlyEqual(render.displayHeight, layout.renderHeight * layout.scale)) {
    renderViolations.push("display height");
  }
  if (render.originX !== 0) renderViolations.push("origin x");
  if (render.originY !== 0) renderViolations.push("origin y");
  if (render.scrollFactorX !== 0) renderViolations.push("scroll factor x");
  if (render.scrollFactorY !== 0) renderViolations.push("scroll factor y");
  if (!nearlyEqual(render.tilePositionX, layout.tilePositionX)) {
    renderViolations.push("tile position x");
  }
  if (render.tilePositionY !== 0) renderViolations.push("tile position y");
  if (!nearlyEqual(render.tileScaleX, layout.textureScale)) {
    renderViolations.push("tile scale x");
  }
  if (!nearlyEqual(render.tileScaleY, layout.textureScale)) {
    renderViolations.push("tile scale y");
  }
  if (render.depth !== contract.renderDepth) {
    renderViolations.push("render depth");
  }
  if (render.spriteCount !== expectedSpriteCount) {
    renderViolations.push("sprite count");
  }
  if (render.textureWidth !== layout.textureWidth) {
    renderViolations.push("texture width");
  }
  if (render.textureHeight !== layout.textureHeight) {
    renderViolations.push("texture height");
  }
  if (renderViolations.length > 0) {
    throw new Error(
      `${contract.id} live render state diverges from its layout: ${renderViolations.join(", ")}`,
    );
  }
  assertBoundsMatch(
    render.displayBounds,
    layout.screenBounds,
    `${contract.id} display bounds`,
  );
  if (layout.foreground === null) {
    if (foreground !== null) {
      throw new Error(`${contract.id} unexpectedly reports foreground state`);
    }
    return;
  }
  if (!foreground) {
    throw new Error(`${contract.id} has no observed foreground state`);
  }
  const tolerance = 0.5 / foreground.devicePixelRatio + RENDER_EPSILON;
  assertBoundsMatch(
    foreground.clipBounds,
    layout.foreground.clipBounds,
    `${contract.id} clip`,
  );
  const foregroundViolations: string[] = [];
  if (
    Math.abs(foreground.contactScreenY - layout.foreground.contactScreenY) >
    tolerance
  ) {
    foregroundViolations.push("contact");
  }
  if (
    !nearlyEqual(
      foreground.sourceScaleScreenX,
      layout.foreground.sourceScaleScreenX,
    )
  ) {
    foregroundViolations.push("horizontal source scale");
  }
  if (
    !nearlyEqual(
      foreground.sourceScaleScreenY,
      layout.foreground.sourceScaleScreenY,
    )
  ) {
    foregroundViolations.push("vertical source scale");
  }
  if (!nearlyEqual(foreground.phaseSourcePx, layout.foreground.phaseSourcePx)) {
    foregroundViolations.push("phase");
  }
  if (render.spriteCount !== 1) foregroundViolations.push("sprite count");
  const physicalPhase = foregroundPhaseForCamera(
    camera,
    contract.depthCoefficient,
    foreground.sourceScaleScreenX,
    foreground.devicePixelRatio,
    foreground.repeatPeriodSourcePx,
  );
  if (!nearlyEqual(foreground.phaseSourcePx, physicalPhase.phaseSourcePx)) {
    foregroundViolations.push("physical phase");
  }
  if (
    !nearlyEqual(
      foreground.projectedCameraTravelScreenPx,
      physicalPhase.projectedCameraTravelScreenPx,
    )
  ) {
    foregroundViolations.push("projected camera travel");
  }
  if (camera.zoom <= 0) foregroundViolations.push("camera zoom");
  if (foregroundViolations.length > 0) {
    throw new Error(
      `${contract.id} live foreground state diverges from layout: ${foregroundViolations.join(", ")}`,
    );
  }
}

export function assertSceneLayerProbe(probe: SceneLayerProbe): void {
  if (
    !probe.integerScreenBounds ||
    (probe.foreground === null && !Number.isSafeInteger(probe.tilePositionX))
  ) {
    throw new Error(`${probe.id} layer render transform is not pixel-snapped`);
  }
  if (
    !nearlyEqual(probe.screenBounds.left, probe.safeBounds.left) ||
    !nearlyEqual(probe.screenBounds.right, probe.safeBounds.right) ||
    (probe.kind !== "near-foreground" &&
      (!nearlyEqual(probe.screenBounds.top, probe.safeBounds.top) ||
        !nearlyEqual(probe.screenBounds.bottom, probe.safeBounds.bottom)))
  ) {
    throw new Error(`${probe.id} layer escapes its safe bounds`);
  }
  // A near foreground is exempted from the bounds check above because only
  // sparse silhouette rises past the safe band, so its top legitimately sits
  // higher. Its bottom is not exempt: the layer is meant to be cropped by the
  // screen edge, and any shortfall is a full-width strip of the layer behind it
  // showing through. Nothing else measured here would have caught that.
  if (
    probe.kind === "near-foreground" &&
    probe.screenBounds.bottom < probe.safeBounds.bottom - RENDER_EPSILON
  ) {
    throw new Error(
      `${probe.id} near foreground stops short of the screen edge`,
    );
  }
  if (probe.imageRepeat !== undefined) {
    if (
      probe.repeat !== "repeat-x-verified" ||
      probe.imageRepeat.schemaVersion !== 2 ||
      probe.imageRepeat.axis !== "x" ||
      probe.imageRepeat.selected !== "verified-v2" ||
      probe.imageRepeat.unverifiedFallbackApplied !== false ||
      probe.imageRepeat.partnerSpriteCount !== 0 ||
      !Number.isSafeInteger(probe.imageRepeat.periodPx) ||
      probe.imageRepeat.periodPx <= 0 ||
      probe.render.textureWidth !== probe.imageRepeat.periodPx ||
      probe.render.spriteCount !== 1
    ) {
      throw new Error(`${probe.id} verified repeat selection is inconsistent`);
    }
  } else if (probe.repeat === "repeat-x-verified") {
    throw new Error(`${probe.id} verified repeat lacks its manifest selection`);
  }
  if (
    probe.kind === "near-foreground" &&
    (probe.anchor !== "screen-ground-left" ||
      probe.baseline !== "screen-ground" ||
      probe.placement !== "screen-ground-contact-strip" ||
      (probe.repeat !== "repeat-x-overlap-add" &&
        probe.repeat !== "repeat-x-verified") ||
      probe.foreground === null ||
      probe.foreground.spriteCount !== 1 ||
      probe.render.spriteCount !== 1)
  ) {
    throw new Error(
      `${probe.id} near foreground is not screen-contact anchored`,
    );
  }
  if (probe.foreground) {
    const foreground = probe.foreground;
    const tolerance = 0.5 / foreground.devicePixelRatio + 1e-9;
    if (
      Math.abs(
        foreground.contactScreenY -
          (foreground.contactStripScreen.bottom -
            foreground.seamPeriodScreenPx / foreground.repeatPeriodSourcePx),
      ) > tolerance ||
      foreground.meaningfulContentScreenBounds.top <
        probe.safeBounds.top - tolerance ||
      Math.abs(
        foreground.phaseDevicePixels - Math.round(foreground.phaseDevicePixels),
      ) > RENDER_EPSILON ||
      !nearlyEqual(
        foreground.seamPeriodScreenPx / foreground.repeatPeriodSourcePx,
        foreground.sourceScaleScreenX,
      ) ||
      !nearlyEqual(
        foreground.sourceScaleScreenX,
        foreground.sourceScaleScreenY,
      ) ||
      foreground.clipBounds.bottom < probe.safeBounds.bottom ||
      !nearlyEqual(probe.render.tilePositionX, foreground.phaseSourcePx) ||
      !nearlyEqual(
        foreground.observedPhaseScreenPx,
        probe.render.tilePositionX * foreground.sourceScaleScreenX,
      ) ||
      !nearlyEqual(
        foreground.projectedCameraTravelScreenPx,
        probe.cameraScrollX * probe.cameraZoom * probe.depthCoefficient,
      ) ||
      foreground.depthCoefficient !== probe.depthCoefficient ||
      probe.depthCoefficient <= 1
    ) {
      throw new Error(`${probe.id} foreground measured placement is unsafe`);
    }
  }
  if (probe.renderDepth < 0 || !Number.isSafeInteger(probe.renderDepth)) {
    throw new Error(
      `${probe.id} layer render depth must be a nonnegative integer`,
    );
  }
}
