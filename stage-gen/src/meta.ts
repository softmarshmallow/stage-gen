// Compatibility wrapper for deterministic recipe stages. AI capability
// packages write their own provenance directly through @stage-gen/core.

import { writeProvenance, type JsonObject } from "@stage-gen/core";

export interface MetaPayload {
  stage: string;
  prompt: string;
  ts: string;
  model?: string;
  seed?: number | string;
  refs?: string[];
  params?: Record<string, unknown>;
  extra?: Record<string, unknown>;
}

export function writeMeta(artifactPath: string, payload: MetaPayload): Promise<string> {
  return writeProvenance(artifactPath, {
    provider: "local",
    model: "deterministic-postprocess",
    prompt: payload.prompt.trim() || `deterministic ${payload.stage}`,
    refs: payload.refs ?? [],
    timestamp: payload.ts,
    attempts: 1,
    params: {
      stage: payload.stage,
      ...(payload.model ? { upstream_model: payload.model } : {}),
      ...(payload.seed !== undefined ? { seed: String(payload.seed) } : {}),
      ...((payload.params ?? {}) as JsonObject),
      metadata: (payload.extra ?? {}) as JsonObject,
    },
  });
}

export function stubMeta(stage: string, prompt: string): MetaPayload {
  return { stage, prompt, ts: new Date().toISOString() };
}
