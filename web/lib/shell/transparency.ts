/** JSON/CLI boundary shared with the authoritative Python backend. */
export type TransparencyMode = "ai" | "chroma";

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
  const nested =
    record.input && typeof record.input === "object"
      ? (record.input as Record<string, unknown>)
      : undefined;
  const rawPrompt = record.prompt ?? nested?.prompt;
  const prompt = typeof rawPrompt === "string" ? rawPrompt.trim() : "";
  if (!prompt) throw new Error("prompt is required");
  const rawMode = record.transparencyMode ?? nested?.transparencyMode;
  if (rawMode !== undefined && !isTransparencyMode(rawMode)) {
    throw new Error("transparencyMode must be ai or chroma");
  }
  return {
    prompt,
    transparencyMode: rawMode ?? DEFAULT_TRANSPARENCY_MODE,
  };
}

export function modeForAiBackgroundRemoval(enabled: boolean): TransparencyMode {
  return enabled ? "ai" : "chroma";
}

/** Read the required generation mode from the one current run manifest contract. */
export function transparencyModeFromRunManifest(value: unknown): TransparencyMode {
  if (!value || typeof value !== "object") {
    throw new Error("run manifest must be an object");
  }
  const input = (value as { input?: unknown }).input;
  if (!input || typeof input !== "object") {
    throw new Error("run manifest input must be an object");
  }
  const mode = (input as { transparencyMode?: unknown }).transparencyMode;
  if (!isTransparencyMode(mode)) {
    throw new Error("run manifest input.transparencyMode must be ai or chroma");
  }
  return mode;
}

export function promptFromRunManifest(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const input = (value as { input?: unknown }).input;
  if (!input || typeof input !== "object") return undefined;
  const prompt = (input as { prompt?: unknown }).prompt;
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
