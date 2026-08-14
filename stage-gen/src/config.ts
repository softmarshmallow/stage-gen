// Process configuration belongs to the headless application boundary.
// Capability packages receive explicit configuration and never read env.

export type CapabilityName =
  | "structured-generation"
  | "image-generation"
  | "background-removal"
  | "music-generation";

export type TransparencyMode = "ai" | "chroma";
export const DEFAULT_TRANSPARENCY_MODE: TransparencyMode = "ai";

export interface StageGenConfig {
  outDir: string;
  openRouterApiKey?: string;
  falKey?: string;
  openRouterBaseUrl?: string;
  falBaseUrl?: string;
  imageModel: string;
  textModel: string;
  musicModel: string;
  backgroundRemovalModel: string;
  transparencyMode: TransparencyMode;
  /** Maximum wall time for one recipe stage, including provider-owned retries. */
  stageTimeoutMs: number;
  /** Per-provider-attempt timeout for standalone and recipe capabilities. */
  capabilityTimeoutMs: number;
}

export interface LoadConfigOptions {
  require?: CapabilityName[];
  env?: Record<string, string | undefined>;
}

const DEFAULTS = {
  outDir: "out",
  imageModel: "openai/gpt-image-2",
  textModel: "openai/gpt-5.5",
  musicModel: "google/lyria-3-pro-preview",
  backgroundRemovalModel: "fal-ai/birefnet/v2",
  stageTimeoutMs: 30 * 60 * 1_000,
  capabilityTimeoutMs: 10 * 60 * 1_000,
  transparencyMode: DEFAULT_TRANSPARENCY_MODE,
} as const;

/** Load config without logging or returning secret values in errors. */
export function loadConfig(options: LoadConfigOptions = {}): StageGenConfig {
  const env = options.env ?? process.env;
  const config: StageGenConfig = {
    outDir: nonEmpty(env.STAGE_GEN_OUT_DIR) ?? nonEmpty(env.OUT_DIR) ?? DEFAULTS.outDir,
    openRouterApiKey: nonEmpty(env.OPENROUTER_API_KEY),
    falKey: nonEmpty(env.FAL_KEY),
    openRouterBaseUrl: nonEmpty(env.OPENROUTER_BASE_URL),
    falBaseUrl: nonEmpty(env.FAL_BASE_URL),
    imageModel:
      nonEmpty(env.STAGE_GEN_IMAGE_MODEL) ?? nonEmpty(env.IMAGE_MODEL) ?? DEFAULTS.imageModel,
    textModel:
      nonEmpty(env.STAGE_GEN_TEXT_MODEL) ?? nonEmpty(env.TEXT_MODEL) ?? DEFAULTS.textModel,
    musicModel:
      nonEmpty(env.STAGE_GEN_MUSIC_MODEL) ?? nonEmpty(env.MUSIC_MODEL) ?? DEFAULTS.musicModel,
    backgroundRemovalModel:
      nonEmpty(env.STAGE_GEN_BACKGROUND_REMOVAL_MODEL) ??
      nonEmpty(env.BACKGROUND_REMOVAL_MODEL) ??
      DEFAULTS.backgroundRemovalModel,
    transparencyMode: optionalTransparencyMode(
      env.TRANSPARENCY_MODE,
      DEFAULTS.transparencyMode,
      "TRANSPARENCY_MODE",
    ),
    stageTimeoutMs: positiveInteger(
      env.STAGE_GEN_STAGE_TIMEOUT_MS,
      "STAGE_GEN_STAGE_TIMEOUT_MS",
      DEFAULTS.stageTimeoutMs,
    ),
    capabilityTimeoutMs: positiveInteger(
      env.STAGE_GEN_CAPABILITY_TIMEOUT_MS,
      "STAGE_GEN_CAPABILITY_TIMEOUT_MS",
      DEFAULTS.capabilityTimeoutMs,
    ),
  };

  assertCapabilities(config, options.require ?? []);
  return config;
}

export function assertCapabilities(
  config: StageGenConfig,
  capabilities: CapabilityName[],
): void {
  const missing = new Set<string>();
  for (const capability of capabilities) {
    if (
      capability === "structured-generation" ||
      capability === "image-generation" ||
      capability === "music-generation"
    ) {
      if (!config.openRouterApiKey) missing.add("OPENROUTER_API_KEY");
    }
    if (capability === "background-removal" && !config.falKey) {
      missing.add("FAL_KEY");
    }
  }
  if (missing.size > 0) {
    throw new ConfigError([...missing]);
  }
}

export class ConfigError extends Error {
  readonly missing: string[];

  constructor(missing: string[]) {
    super(
      `missing required environment variable${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`,
    );
    this.name = "ConfigError";
    this.missing = missing;
  }
}

function nonEmpty(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function positiveInteger(
  value: string | undefined,
  name: string,
  fallback: number,
): number {
  const normalized = nonEmpty(value);
  if (normalized === undefined) return fallback;
  const parsed = Number(normalized);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive integer in milliseconds`);
  }
  return parsed;
}

export function parseTransparencyMode(
  value: unknown,
  label = "transparency mode",
): TransparencyMode {
  if (value === "ai" || value === "chroma") return value;
  throw new Error(`${label} must be ai or chroma`);
}

/** Additional capability required by the selected transparency strategy. */
export function transparencyCapabilities(
  mode: TransparencyMode,
): readonly CapabilityName[] {
  return mode === "ai" ? ["background-removal"] : [];
}

function optionalTransparencyMode(
  value: string | undefined,
  fallback: TransparencyMode,
  label: string,
): TransparencyMode {
  const normalized = nonEmpty(value);
  return normalized === undefined ? fallback : parseTransparencyMode(normalized, label);
}
