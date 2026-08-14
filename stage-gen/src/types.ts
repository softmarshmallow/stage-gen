import type { CapabilityName, StageGenConfig } from "./config.ts";

export type JsonObject = Record<string, unknown>;

export interface ArtifactRef {
  path: string;
  provenancePath?: string;
}

export interface StageResult {
  stage: string;
  ok: boolean;
  durationMs: number;
  artifacts: string[];
  error?: string;
}

export interface RunSummary<I extends JsonObject = JsonObject> {
  recipe: string;
  input: I;
  tag: string;
  runDir: string;
  startedAt: string;
  endedAt: string;
  durationMs: number;
  ok: boolean;
  failedStage?: string;
  stages: StageResult[];
}

export interface StageContext<I extends JsonObject = JsonObject> {
  input: I;
  tag: string;
  runDir: string;
  config: StageGenConfig;
  signal: AbortSignal;
}

export interface Stage<I extends JsonObject = JsonObject> {
  name: string;
  wave: number;
  description: string;
  run(context: StageContext<I>): Promise<{ artifacts: string[] }>;
}

/**
 * A recipe is an application-level composition of generic capabilities.
 * Generic runner code must not assume a genre, camera, gameplay loop, or engine.
 */
export interface Recipe<I extends JsonObject = JsonObject> {
  id: string;
  description: string;
  requiredCapabilities: readonly CapabilityName[];
  parseInput(value: unknown): I;
  tagFor(input: I): string;
  stages: readonly Stage<I>[];
}

export interface RunOptions<I extends JsonObject = JsonObject> {
  recipe: Recipe<I>;
  input: I;
  config: StageGenConfig;
  log?: (line: string) => void;
  signal?: AbortSignal;
  /** Precomputed public/cache identity. Service callers should supply this. */
  tag?: string;
}
