import {
  parseRecipeRunSummary,
  type RecipeRunSummary,
  type RunTransparencyMode,
} from "./run-summary";

/** UI/CLI adapter spelling for the run contract's transparency mode. */
export type TransparencyMode = RunTransparencyMode;

export const DEFAULT_TRANSPARENCY_MODE: TransparencyMode = "ai";

export interface WebRunInput {
  prompt: string;
  transparencyMode: TransparencyMode;
}

export type PreviewTransparencyPolicy = "canonical-alpha";

export function isTransparencyMode(value: unknown): value is TransparencyMode {
  return value === "ai" || value === "chroma";
}

export function parseWebRunInput(value: unknown): WebRunInput {
  if (!value || typeof value !== "object") throw new Error("request body must be an object");
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (key !== "prompt" && key !== "transparency_mode") {
      throw new Error(`request body.${key} is not a supported key`);
    }
  }
  const rawPrompt = record.prompt;
  const prompt = typeof rawPrompt === "string" ? rawPrompt.trim() : "";
  if (!prompt) throw new Error("prompt is required");
  const rawMode = record.transparency_mode;
  if (rawMode !== undefined && !isTransparencyMode(rawMode)) {
    throw new Error("transparency_mode must be ai or chroma");
  }
  return {
    prompt,
    transparencyMode: rawMode ?? DEFAULT_TRANSPARENCY_MODE,
  };
}

export function modeForAiBackgroundRemoval(enabled: boolean): TransparencyMode {
  return enabled ? "ai" : "chroma";
}

/** Read the generation mode only after validating the complete persisted summary. */
export function transparencyModeFromRunSummary(value: unknown): TransparencyMode {
  return parseRecipeRunSummary(value).input.transparency_mode;
}

export function promptFromRunSummary(value: RecipeRunSummary): string | undefined {
  const prompt = value.input["prompt"];
  return typeof prompt === "string" && prompt.trim() ? prompt.trim() : undefined;
}

export function previewPolicyForRunMode(
  mode: TransparencyMode | null,
): PreviewTransparencyPolicy {
  if (!isTransparencyMode(mode)) {
    throw new Error("current preview requires a transparency mode");
  }
  return "canonical-alpha";
}

export function transparencyModeLabel(mode: TransparencyMode | null): string {
  if (mode === "ai") return "ai (background removal)";
  if (mode === "chroma") return "chroma (degraded fallback)";
  throw new Error("current preview requires a transparency mode");
}
