import {
  assertMediaType,
  assertNonEmptyString,
  assertSuccessfulResponse,
  decodeBase64Strict,
  DEFAULT_TOOL_IDENTITY,
  hashInputReference,
  isRecord,
  readJsonObject,
  responseMetadataFromHeaders,
  sanitizeReference,
  withRetry,
  writeArtifactWithProvenance,
  type BinaryArtifact,
  type JsonObject,
  type ProviderResponseMetadata,
  type RetryOptions,
  type SoftwareIdentity,
} from "@stage-gen/core";

export const OPENROUTER_IMAGE_MODEL = "openai/gpt-image-2" as const;
export const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1" as const;
export const IMAGE_GENERATION_COMPONENT = {
  name: "@stage-gen/image-generation",
  version: "0.0.0",
} as const;

export type ImageAspectRatio = `${number}:${number}` | "auto";
export type ImageQuality = "auto" | "low" | "medium" | "high";
export type ImageBackground = "auto" | "opaque";

export interface ImageReference {
  url: string;
  /** Stable path/id recorded in provenance instead of a data URL. */
  provenanceRef?: string;
}

export interface OpenRouterImageGeneratorConfig {
  apiKey: string;
  model?: string;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  now?: () => Date;
  retry?: Omit<RetryOptions, "label" | "secrets" | "signal">;
  tool?: SoftwareIdentity;
}

export interface ImageGenerationRequest {
  prompt: string;
  /** Intended output path; the adapter writes `<artifactPath>.meta.json`. */
  artifactPath: string;
  inputReferences?: readonly ImageReference[];
  aspectRatio?: ImageAspectRatio;
  quality?: ImageQuality;
  background?: ImageBackground;
  outputCompression?: number;
  moderation?: "auto" | "low";
  /** Caller-owned stage/dimension/recipe metadata persisted under `params.metadata`. */
  metadata?: Record<string, unknown>;
  /** Cancels the active provider request, backoff, and remaining retries. */
  signal?: AbortSignal;
  /** Per-attempt timeout; defaults to the core policy. */
  timeoutMs?: number;
  /** Throwing here retries the complete provider call within the same retry owner. */
  validate?: (
    artifact: BinaryArtifact,
  ) => void | Record<string, unknown> | Promise<void | Record<string, unknown>>;
}

export interface ImageGenerationResult {
  bytes: Uint8Array;
  mediaType: string;
  provider: "openrouter";
  model: string;
  attempts: number;
  provenancePath: string;
  responseMetadata: ProviderResponseMetadata;
}

export interface OpenRouterImageGenerator {
  generate(request: ImageGenerationRequest): Promise<ImageGenerationResult>;
}

export function createOpenRouterImageGenerator(
  config: OpenRouterImageGeneratorConfig,
): OpenRouterImageGenerator {
  assertNonEmptyString(config.apiKey, "OpenRouter apiKey");
  const apiKey = config.apiKey;
  const model = nonEmpty(config.model, OPENROUTER_IMAGE_MODEL);
  const baseUrl = normalizeBaseUrl(config.baseUrl ?? OPENROUTER_BASE_URL);
  const fetchImpl = config.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("a fetch implementation is required");
  }

  return {
    async generate(request): Promise<ImageGenerationResult> {
      validateRequest(request);
      const inputReferences = request.inputReferences ?? [];
      const body: Record<string, unknown> = {
        model,
        prompt: request.prompt,
        n: 1,
      };
      if (request.aspectRatio !== undefined) body.aspect_ratio = request.aspectRatio;
      if (request.quality !== undefined) body.quality = request.quality;
      if (request.background !== undefined) body.background = request.background;
      if (request.outputCompression !== undefined) {
        body.output_compression = request.outputCompression;
      }
      if (inputReferences.length > 0) {
        body.input_references = inputReferences.map(({ url }) => ({
          type: "image_url",
          image_url: { url },
        }));
      }
      if (request.moderation !== undefined) {
        body.provider = { options: { openai: { moderation: request.moderation } } };
      }

      let attempts = 0;
      const generated = await withRetry(
        async ({ attempt, signal }) => {
          attempts = attempt;
          const response = await fetchImpl(`${baseUrl}/images`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${apiKey}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
            signal,
          });
          assertSuccessfulResponse(response, "OpenRouter image generation");
          const payload = await readJsonObject(response, "OpenRouter image generation");
          const parsed = parseImageResponse(payload, response);
          const callerFacts = await request.validate?.({
            bytes: parsed.bytes,
            mediaType: parsed.mediaType,
          });
          if (callerFacts !== undefined && !isRecord(callerFacts)) {
            throw new Error("image validator must return an object or void");
          }
          return { ...parsed, callerFacts: callerFacts ?? {} };
        },
        {
          ...config.retry,
          signal: request.signal,
          timeoutMs: request.timeoutMs ?? config.retry?.timeoutMs,
          label: "OpenRouter image generation",
          secrets: [apiKey],
        },
      );

      const params: Record<string, unknown> = {
        n: 1,
        ...(request.aspectRatio ? { aspect_ratio: request.aspectRatio } : {}),
        ...(request.quality ? { quality: request.quality } : {}),
        ...(request.background ? { background: request.background } : {}),
        ...(request.outputCompression !== undefined
          ? { output_compression: request.outputCompression }
          : {}),
        ...(request.moderation ? { moderation: request.moderation } : {}),
        validated: request.validate !== undefined,
        ...(request.metadata ? { metadata: request.metadata } : {}),
      };
      const responseProvenance: Record<string, unknown> = {
        media_type: generated.mediaType,
        bytes: generated.bytes.length,
        ...(generated.responseMetadata.requestId
          ? { request_id: generated.responseMetadata.requestId }
          : {}),
        ...(generated.responseMetadata.created !== undefined
          ? { created: generated.responseMetadata.created }
          : {}),
        ...(generated.responseMetadata.usage
          ? { usage: generated.responseMetadata.usage }
          : {}),
      };
      const refs = inputReferences.map((reference) =>
        reference.provenanceRef ? reference.provenanceRef : sanitizeReference(reference.url),
      );
      const provenancePath = await writeArtifactWithProvenance(
        request.artifactPath,
        { bytes: generated.bytes, mediaType: generated.mediaType },
        {
          provider: "openrouter",
          model,
          seed: null,
          prompt: request.prompt,
          refs,
          inputs: inputReferences.map((reference) =>
            hashInputReference(reference.url, reference.provenanceRef),
          ),
          params,
          validation: {
            output_nonempty: true,
            base64: "strict",
            media_type: generated.mediaType,
            signature: "matched",
            caller: request.validate !== undefined,
            ...generated.callerFacts,
          },
          component: IMAGE_GENERATION_COMPONENT,
          tool: config.tool ?? DEFAULT_TOOL_IDENTITY,
          timestamp: config.now?.().toISOString(),
          attempts,
          response: responseProvenance,
        },
        { secrets: [apiKey] },
      );

      return {
        bytes: generated.bytes,
        mediaType: generated.mediaType,
        provider: "openrouter",
        model,
        attempts,
        provenancePath,
        responseMetadata: generated.responseMetadata,
      };
    },
  };
}

function parseImageResponse(
  payload: Record<string, unknown>,
  response: Response,
): {
  bytes: Uint8Array;
  mediaType: string;
  responseMetadata: ProviderResponseMetadata;
} {
  if (!Array.isArray(payload.data) || payload.data.length !== 1 || !isRecord(payload.data[0])) {
    throw new Error("OpenRouter image generation returned no single image");
  }
  const image = payload.data[0];
  const bytes = decodeBase64Strict(image.b64_json, "OpenRouter image b64_json");
  const mediaType = assertMediaType(image.media_type, "image");
  assertImageSignature(bytes, mediaType);

  const headerMetadata = responseMetadataFromHeaders(response);
  const created =
    typeof payload.created === "number" && Number.isFinite(payload.created)
      ? payload.created
      : undefined;
  const usage = isRecord(payload.usage) ? (payload.usage as JsonObject) : undefined;
  return {
    bytes,
    mediaType,
    responseMetadata: {
      ...headerMetadata,
      ...(created !== undefined ? { created } : {}),
      ...(usage ? { usage } : {}),
    },
  };
}

function assertImageSignature(bytes: Uint8Array, mediaType: string): void {
  const matches =
    (mediaType === "image/png" &&
      startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) ||
    ((mediaType === "image/jpeg" || mediaType === "image/jpg") &&
      startsWith(bytes, [0xff, 0xd8, 0xff])) ||
    (mediaType === "image/webp" &&
      startsWith(bytes, [0x52, 0x49, 0x46, 0x46]) &&
      bytes.length >= 12 &&
      String.fromCharCode(...bytes.slice(8, 12)) === "WEBP");
  if (!matches) {
    throw new Error(`image bytes do not match declared media type ${mediaType}`);
  }
}

function validateRequest(request: ImageGenerationRequest): void {
  assertNonEmptyString(request.prompt, "image prompt");
  assertNonEmptyString(request.artifactPath, "artifactPath");
  if (
    request.outputCompression !== undefined &&
    (!Number.isInteger(request.outputCompression) ||
      request.outputCompression < 0 ||
      request.outputCompression > 100)
  ) {
    throw new Error("outputCompression must be an integer from 0 to 100");
  }
  if (
    request.aspectRatio !== undefined &&
    request.aspectRatio !== "auto" &&
    !/^[1-9]\d*:[1-9]\d*$/.test(request.aspectRatio)
  ) {
    throw new Error("aspectRatio must be auto or two positive integers separated by a colon");
  }
  for (const reference of request.inputReferences ?? []) {
    assertNonEmptyString(reference.url, "image reference url");
    if (!/^(?:https?:\/\/|data:image\/[^;,]+;base64,)/i.test(reference.url)) {
      throw new Error("image references must be HTTP(S) URLs or base64 image data URLs");
    }
  }
}

function startsWith(bytes: Uint8Array, expected: readonly number[]): boolean {
  return expected.every((value, index) => bytes[index] === value);
}

function normalizeBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  assertNonEmptyString(trimmed, "OpenRouter baseUrl");
  return trimmed;
}

function nonEmpty(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim() : fallback;
}
