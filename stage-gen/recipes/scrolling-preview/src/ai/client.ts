// Recipe-local access to provider-neutral capability packages.
// Configuration remains owned by the headless application boundary.

import { AsyncLocalStorage } from "node:async_hooks";
import {
  createFalBackgroundRemover,
  type FalBackgroundRemover,
} from "@stage-gen/background-removal";
import {
  createOpenRouterImageGenerator,
  type OpenRouterImageGenerator,
} from "@stage-gen/image-generation";
import {
  createOpenRouterStructuredGenerator,
  type OpenRouterStructuredGenerator,
} from "@stage-gen/structured-generation";
import {
  assertCapabilities,
  type StageGenConfig,
} from "../../../../src/config.ts";

interface AiExecutionContext {
  image: OpenRouterImageGenerator;
  structured: OpenRouterStructuredGenerator;
  background?: FalBackgroundRemover;
  signal: AbortSignal;
  timeoutMs: number;
}

const execution = new AsyncLocalStorage<AiExecutionContext>();

/** Isolate capability clients and cancellation per concurrent recipe stage. */
export function withAiCapabilities<T>(
  config: StageGenConfig,
  signal: AbortSignal,
  run: () => Promise<T>,
): Promise<T> {
  const apiKey = config.openRouterApiKey;
  if (!apiKey) throw new Error("OPENROUTER_API_KEY is required");
  if (config.transparencyMode === "ai") {
    assertCapabilities(config, ["background-removal"]);
  }
  return execution.run(
    {
      image: createOpenRouterImageGenerator({
        apiKey,
        model: config.imageModel,
        baseUrl: config.openRouterBaseUrl,
      }),
      structured: createOpenRouterStructuredGenerator({
        apiKey,
        model: config.textModel,
        baseUrl: config.openRouterBaseUrl,
      }),
      ...(config.transparencyMode === "ai"
        ? {
            background: createFalBackgroundRemover({
              apiKey: config.falKey!,
              model: config.backgroundRemovalModel,
              baseUrl: config.falBaseUrl,
            }),
          }
        : {}),
      signal,
      timeoutMs: config.capabilityTimeoutMs,
    },
    run,
  );
}

export function imageGenerator(): OpenRouterImageGenerator {
  const context = execution.getStore();
  if (!context) throw new Error("image generation capability is not configured");
  return context.image;
}

export function structuredGenerator(): OpenRouterStructuredGenerator {
  const context = execution.getStore();
  if (!context) throw new Error("structured generation capability is not configured");
  return context.structured;
}

export function backgroundRemover(): FalBackgroundRemover {
  const context = execution.getStore();
  if (!context?.background) {
    throw new Error("AI background-removal capability is not configured");
  }
  return context.background;
}

export function aiRequestControl(): Pick<AiExecutionContext, "signal" | "timeoutMs"> {
  const context = execution.getStore();
  if (!context) throw new Error("AI request context is not configured");
  return { signal: context.signal, timeoutMs: context.timeoutMs };
}
