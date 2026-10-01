export type ImagePoint = readonly [x: number, y: number];

export type IllustratedMapFeatureKind =
  | "settlement"
  | "landmark"
  | "natural_feature"
  | "crossing"
  | "ruin"
  | "sanctuary";

export type IllustratedMapLabelPlacement = "above" | "below" | "left" | "right";

export interface IllustratedMapFeatureV1 {
  readonly feature_id: string;
  readonly feature_kind: IllustratedMapFeatureKind;
  readonly geometry: {
    readonly kind: "point";
    readonly coordinates: ImagePoint;
  };
  readonly label: {
    readonly fallback_text: string;
    readonly placement: IllustratedMapLabelPlacement;
    readonly priority: number;
    readonly min_screen_pixels_per_image_pixel: number;
  };
  readonly interaction: {
    readonly selectable: boolean;
    readonly hit_radius_image_pixels: number;
  };
  readonly summary: string;
  readonly tags: readonly string[];
}

export interface IllustratedMapManifestV1 {
  readonly schema_version: 1;
  readonly kind: "illustrated-map-manifest-v1";
  readonly map_id: string;
  readonly revision: number;
  readonly display_name: string;
  readonly coordinate_space: {
    readonly kind: "image-pixel-v1";
    readonly origin: "top_left";
    readonly x_axis: "right";
    readonly y_axis: "down";
    readonly width: number;
    readonly height: number;
  };
  readonly raster: {
    readonly delivery_kind: "single_image";
    readonly path: string;
    readonly media_type: "image/png";
    readonly sha256: string;
    readonly bytes: number;
    readonly width: number;
    readonly height: number;
  };
  readonly initial_view: {
    readonly mode: "fit_extent";
    readonly min_screen_pixels_per_image_pixel: number;
    readonly max_screen_pixels_per_image_pixel: number;
  };
  readonly features: readonly IllustratedMapFeatureV1[];
}

const ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const TAG_PATTERN = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;

function fail(path: string, message: string): never {
  throw new Error(`${path}: ${message}`);
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(path, "expected an object");
  }
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  path: string,
): void {
  const expected = new Set(keys);
  for (const key of Object.keys(value)) {
    if (!expected.has(key)) {
      fail(`${path}.${key}`, "unknown field");
    }
  }
  for (const key of keys) {
    if (!(key in value)) {
      fail(`${path}.${key}`, "missing field");
    }
  }
}

function stringValue(
  value: unknown,
  path: string,
  options: { max: number; pattern?: RegExp },
): string {
  if (typeof value !== "string" || value.trim() !== value || value.length === 0) {
    fail(path, "expected a non-empty trimmed string");
  }
  if (value.length > options.max) {
    fail(path, `must be at most ${options.max} characters`);
  }
  if (options.pattern && !options.pattern.test(value)) {
    fail(path, "has an invalid format");
  }
  return value;
}

function numberValue(
  value: unknown,
  path: string,
  options: { min?: number; max?: number; integer?: boolean } = {},
): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(path, "expected a finite number");
  }
  if (options.integer && !Number.isInteger(value)) {
    fail(path, "expected an integer");
  }
  if (options.min !== undefined && value < options.min) {
    fail(path, `must be at least ${options.min}`);
  }
  if (options.max !== undefined && value > options.max) {
    fail(path, `must be at most ${options.max}`);
  }
  return value;
}

function literal<T extends string | number>(
  value: unknown,
  expected: T,
  path: string,
): T {
  if (value !== expected) {
    fail(path, `expected ${JSON.stringify(expected)}`);
  }
  return expected;
}

function oneOf<T extends string>(
  value: unknown,
  expected: readonly T[],
  path: string,
): T {
  if (typeof value !== "string" || !expected.includes(value as T)) {
    fail(path, `expected one of ${expected.join(", ")}`);
  }
  return value as T;
}

function booleanValue(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    fail(path, "expected a boolean");
  }
  return value;
}

function portableRelativePath(value: unknown, path: string): string {
  const parsed = stringValue(value, path, { max: 240 });
  const segments = parsed.split("/");
  if (
    parsed.startsWith("/") ||
    parsed.includes("\\") ||
    parsed.includes("?") ||
    parsed.includes("#") ||
    segments.some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    fail(path, "expected a portable relative POSIX path");
  }
  return parsed;
}

function sha256(value: unknown, path: string): string {
  return stringValue(value, path, { max: 64, pattern: SHA256_PATTERN });
}

function parseFeature(
  value: unknown,
  index: number,
  width: number,
  height: number,
  minScale: number,
  maxScale: number,
): IllustratedMapFeatureV1 {
  const path = `manifest.features[${index}]`;
  const feature = record(value, path);
  exactKeys(
    feature,
    [
      "feature_id",
      "feature_kind",
      "geometry",
      "label",
      "interaction",
      "summary",
      "tags",
    ],
    path,
  );

  const geometryPath = `${path}.geometry`;
  const geometry = record(feature.geometry, geometryPath);
  exactKeys(geometry, ["kind", "coordinates"], geometryPath);
  literal(geometry.kind, "point", `${geometryPath}.kind`);
  if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length !== 2) {
    fail(`${geometryPath}.coordinates`, "expected exactly [x, y]");
  }
  const x = numberValue(geometry.coordinates[0], `${geometryPath}.coordinates[0]`, {
    min: 0,
  });
  const y = numberValue(geometry.coordinates[1], `${geometryPath}.coordinates[1]`, {
    min: 0,
  });
  if (x >= width || y >= height) {
    fail(`${geometryPath}.coordinates`, "point lies outside the source image");
  }

  const labelPath = `${path}.label`;
  const label = record(feature.label, labelPath);
  exactKeys(
    label,
    [
      "fallback_text",
      "placement",
      "priority",
      "min_screen_pixels_per_image_pixel",
    ],
    labelPath,
  );
  const labelScale = numberValue(
    label.min_screen_pixels_per_image_pixel,
    `${labelPath}.min_screen_pixels_per_image_pixel`,
    { min: Number.MIN_VALUE },
  );
  if (labelScale < minScale || labelScale > maxScale) {
    fail(
      `${labelPath}.min_screen_pixels_per_image_pixel`,
      "must be inside the supported view scale range",
    );
  }

  const interactionPath = `${path}.interaction`;
  const interaction = record(feature.interaction, interactionPath);
  exactKeys(
    interaction,
    ["selectable", "hit_radius_image_pixels"],
    interactionPath,
  );

  if (!Array.isArray(feature.tags)) {
    fail(`${path}.tags`, "expected an array");
  }
  const tags = feature.tags.map((tag, tagIndex) =>
    stringValue(tag, `${path}.tags[${tagIndex}]`, {
      max: 48,
      pattern: TAG_PATTERN,
    }),
  );
  if (new Set(tags).size !== tags.length) {
    fail(`${path}.tags`, "tags must be unique");
  }

  return {
    feature_id: stringValue(feature.feature_id, `${path}.feature_id`, {
      max: 80,
      pattern: ID_PATTERN,
    }),
    feature_kind: oneOf(
      feature.feature_kind,
      [
        "settlement",
        "landmark",
        "natural_feature",
        "crossing",
        "ruin",
        "sanctuary",
      ] as const,
      `${path}.feature_kind`,
    ),
    geometry: { kind: "point", coordinates: [x, y] },
    label: {
      fallback_text: stringValue(label.fallback_text, `${labelPath}.fallback_text`, {
        max: 120,
      }),
      placement: oneOf(
        label.placement,
        ["above", "below", "left", "right"] as const,
        `${labelPath}.placement`,
      ),
      priority: numberValue(label.priority, `${labelPath}.priority`, {
        integer: true,
        min: 0,
        max: 100,
      }),
      min_screen_pixels_per_image_pixel: labelScale,
    },
    interaction: {
      selectable: booleanValue(interaction.selectable, `${interactionPath}.selectable`),
      hit_radius_image_pixels: numberValue(
        interaction.hit_radius_image_pixels,
        `${interactionPath}.hit_radius_image_pixels`,
        { min: Number.MIN_VALUE, max: 256 },
      ),
    },
    summary: stringValue(feature.summary, `${path}.summary`, { max: 280 }),
    tags,
  };
}

export function parseIllustratedMapManifest(input: unknown): IllustratedMapManifestV1 {
  const manifest = record(input, "manifest");
  exactKeys(
    manifest,
    [
      "schema_version",
      "kind",
      "map_id",
      "revision",
      "display_name",
      "coordinate_space",
      "raster",
      "initial_view",
      "features",
    ],
    "manifest",
  );

  const coordinate = record(manifest.coordinate_space, "manifest.coordinate_space");
  exactKeys(
    coordinate,
    ["kind", "origin", "x_axis", "y_axis", "width", "height"],
    "manifest.coordinate_space",
  );
  const width = numberValue(coordinate.width, "manifest.coordinate_space.width", {
    integer: true,
    min: 1,
  });
  const height = numberValue(coordinate.height, "manifest.coordinate_space.height", {
    integer: true,
    min: 1,
  });

  const raster = record(manifest.raster, "manifest.raster");
  exactKeys(
    raster,
    ["delivery_kind", "path", "media_type", "sha256", "bytes", "width", "height"],
    "manifest.raster",
  );
  const rasterWidth = numberValue(raster.width, "manifest.raster.width", {
    integer: true,
    min: 1,
  });
  const rasterHeight = numberValue(raster.height, "manifest.raster.height", {
    integer: true,
    min: 1,
  });
  if (rasterWidth !== width || rasterHeight !== height) {
    fail("manifest.raster", "dimensions must match the coordinate space");
  }

  const initialView = record(manifest.initial_view, "manifest.initial_view");
  exactKeys(
    initialView,
    [
      "mode",
      "min_screen_pixels_per_image_pixel",
      "max_screen_pixels_per_image_pixel",
    ],
    "manifest.initial_view",
  );
  const minScale = numberValue(
    initialView.min_screen_pixels_per_image_pixel,
    "manifest.initial_view.min_screen_pixels_per_image_pixel",
    { min: Number.MIN_VALUE },
  );
  const maxScale = numberValue(
    initialView.max_screen_pixels_per_image_pixel,
    "manifest.initial_view.max_screen_pixels_per_image_pixel",
    { min: Number.MIN_VALUE },
  );
  if (minScale > maxScale) {
    fail("manifest.initial_view", "minimum scale must not exceed maximum scale");
  }

  if (!Array.isArray(manifest.features)) {
    fail("manifest.features", "expected an array");
  }
  if (manifest.features.length < 1 || manifest.features.length > 256) {
    fail("manifest.features", "expected between 1 and 256 features");
  }
  const features = manifest.features.map((feature, index) =>
    parseFeature(feature, index, width, height, minScale, maxScale),
  );
  const featureIds = features.map((feature) => feature.feature_id);
  if (new Set(featureIds).size !== featureIds.length) {
    fail("manifest.features", "feature_id values must be unique");
  }

  return {
    schema_version: literal(manifest.schema_version, 1, "manifest.schema_version"),
    kind: literal(manifest.kind, "illustrated-map-manifest-v1", "manifest.kind"),
    map_id: stringValue(manifest.map_id, "manifest.map_id", {
      max: 80,
      pattern: ID_PATTERN,
    }),
    revision: numberValue(manifest.revision, "manifest.revision", {
      integer: true,
      min: 1,
    }),
    display_name: stringValue(manifest.display_name, "manifest.display_name", {
      max: 160,
    }),
    coordinate_space: {
      kind: literal(coordinate.kind, "image-pixel-v1", "manifest.coordinate_space.kind"),
      origin: literal(
        coordinate.origin,
        "top_left",
        "manifest.coordinate_space.origin",
      ),
      x_axis: literal(coordinate.x_axis, "right", "manifest.coordinate_space.x_axis"),
      y_axis: literal(coordinate.y_axis, "down", "manifest.coordinate_space.y_axis"),
      width,
      height,
    },
    raster: {
      delivery_kind: literal(
        raster.delivery_kind,
        "single_image",
        "manifest.raster.delivery_kind",
      ),
      path: portableRelativePath(raster.path, "manifest.raster.path"),
      media_type: literal(raster.media_type, "image/png", "manifest.raster.media_type"),
      sha256: sha256(raster.sha256, "manifest.raster.sha256"),
      bytes: numberValue(raster.bytes, "manifest.raster.bytes", {
        integer: true,
        min: 1,
      }),
      width: rasterWidth,
      height: rasterHeight,
    },
    initial_view: {
      mode: literal(initialView.mode, "fit_extent", "manifest.initial_view.mode"),
      min_screen_pixels_per_image_pixel: minScale,
      max_screen_pixels_per_image_pixel: maxScale,
    },
    features,
  };
}

export function imagePixelToMapCoordinate(
  point: ImagePoint,
  imageHeight: number,
): [number, number] {
  return [point[0], imageHeight - point[1]];
}

export function screenPixelsPerImagePixel(resolution: number): number {
  return 1 / resolution;
}

export function sortFeaturesByLabelPriority(
  left: IllustratedMapFeatureV1,
  right: IllustratedMapFeatureV1,
): number {
  return right.label.priority - left.label.priority;
}
