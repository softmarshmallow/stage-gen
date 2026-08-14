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
  type ProviderResponseMetadata,
  type RetryOptions,
  type SoftwareIdentity,
} from "@stage-gen/core";

export const FAL_BACKGROUND_REMOVAL_MODEL = "fal-ai/birefnet/v2" as const;
export const FAL_BASE_URL = "https://fal.run" as const;
export const BACKGROUND_REMOVAL_COMPONENT = {
  name: "@stage-gen/background-removal",
  version: "0.0.0",
} as const;

export type BackgroundModelVariant =
  | "General Use (Light)"
  | "General Use (Light 2K)"
  | "General Use (Heavy)"
  | "Matting"
  | "Portrait"
  | "General Use (Dynamic)";
export type BackgroundOperatingResolution = "1024x1024" | "2048x2048" | "2304x2304";
export type BackgroundOutputFormat = "png" | "webp" | "gif";

export interface FalBackgroundRemoverConfig {
  apiKey: string;
  model?: string;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  now?: () => Date;
  retry?: Omit<RetryOptions, "label" | "secrets" | "signal">;
  tool?: SoftwareIdentity;
}

export interface BackgroundRemovalRequest {
  imageUrl: string;
  artifactPath: string;
  modelVariant?: BackgroundModelVariant;
  operatingResolution?: BackgroundOperatingResolution;
  outputMask?: boolean;
  refineForeground?: boolean;
  outputFormat?: BackgroundOutputFormat;
  maskOnly?: boolean;
  /** Defaults true so the primary artifact can be validated without another hosted-file request. */
  syncMode?: boolean;
  /** Caller-owned stage/recipe metadata persisted under `params.metadata`. */
  metadata?: Record<string, unknown>;
  /** Cancels the active provider request, hosted download, backoff, and retries. */
  signal?: AbortSignal;
  /** Per-attempt timeout; defaults to the core policy. */
  timeoutMs?: number;
  /** Throwing here retries generation and extraction within the same retry owner. */
  validate?: (
    artifact: BinaryArtifact,
    context: { mask?: BackgroundMaskArtifact },
  ) => void | Record<string, unknown> | Promise<void | Record<string, unknown>>;
}

export interface BackgroundMaskMetadata {
  url: string;
  mediaType?: string;
  width?: number;
  height?: number;
}

/** Downloaded mask output when the provider returns `mask_image`. */
export interface BackgroundMaskArtifact extends BackgroundMaskMetadata {
  bytes: Uint8Array;
  mediaType: string;
}

export interface BackgroundRemovalResult {
  bytes: Uint8Array;
  mediaType: string;
  sourceUrl: string;
  width?: number;
  height?: number;
  maskImage?: BackgroundMaskMetadata;
  mask?: BackgroundMaskArtifact;
  provider: "fal";
  model: string;
  attempts: number;
  provenancePath: string;
  responseMetadata: ProviderResponseMetadata;
}

export interface FalBackgroundRemover {
  remove(request: BackgroundRemovalRequest): Promise<BackgroundRemovalResult>;
}

export function createFalBackgroundRemover(
  config: FalBackgroundRemoverConfig,
): FalBackgroundRemover {
  assertNonEmptyString(config.apiKey, "fal apiKey");
  const apiKey = config.apiKey;
  const model = nonEmpty(config.model, FAL_BACKGROUND_REMOVAL_MODEL).replace(/^\/+/, "");
  const baseUrl = normalizeBaseUrl(config.baseUrl ?? FAL_BASE_URL);
  const fetchImpl = config.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") throw new Error("a fetch implementation is required");

  return {
    async remove(request): Promise<BackgroundRemovalResult> {
      validateRequest(request);
      const syncMode = request.syncMode ?? true;
      const body = {
        image_url: request.imageUrl,
        model: request.modelVariant ?? "General Use (Light)",
        operating_resolution: request.operatingResolution ?? "1024x1024",
        output_mask: request.outputMask ?? false,
        refine_foreground: request.refineForeground ?? true,
        output_format: request.outputFormat ?? "png",
        mask_only: request.maskOnly ?? false,
        sync_mode: syncMode,
      };

      let attempts = 0;
      const removed = await withRetry(
        async ({ attempt, signal }) => {
          attempts = attempt;
          const response = await fetchImpl(`${baseUrl}/${model}`, {
            method: "POST",
            headers: {
              Authorization: `Key ${apiKey}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
            signal,
          });
          assertSuccessfulResponse(response, "fal background removal");
          const payload = await readJsonObject(response, "fal background removal");
          const parsed = await parseBackgroundResponse(payload, response, fetchImpl, signal);
          const callerFacts = await request.validate?.(
            {
              bytes: parsed.bytes,
              mediaType: parsed.mediaType,
            },
            { ...(parsed.mask ? { mask: parsed.mask } : {}) },
          );
          if (callerFacts !== undefined && !isRecord(callerFacts)) {
            throw new Error("background validator must return an object or void");
          }
          return { ...parsed, callerFacts: callerFacts ?? {} };
        },
        {
          ...config.retry,
          signal: request.signal,
          timeoutMs: request.timeoutMs ?? config.retry?.timeoutMs,
          label: "fal background removal",
          secrets: [apiKey],
        },
      );

      const params: Record<string, unknown> = {
        model_variant: body.model,
        operating_resolution: body.operating_resolution,
        output_mask: body.output_mask,
        refine_foreground: body.refine_foreground,
        output_format: body.output_format,
        mask_only: body.mask_only,
        sync_mode: body.sync_mode,
        validated: request.validate !== undefined,
        ...(request.metadata ? { metadata: request.metadata } : {}),
      };
      const responseProvenance: Record<string, unknown> = {
        media_type: removed.mediaType,
        bytes: removed.bytes.length,
        mask_present: removed.mask !== undefined,
        ...(removed.mask
          ? {
              mask_media_type: removed.mask.mediaType,
              mask_bytes: removed.mask.bytes.length,
            }
          : {}),
        ...(removed.width !== undefined ? { width: removed.width } : {}),
        ...(removed.height !== undefined ? { height: removed.height } : {}),
        ...(removed.responseMetadata.requestId
          ? { request_id: removed.responseMetadata.requestId }
          : {}),
      };
      const stableRef = sanitizeReference(request.imageUrl);
      const provenancePath = await writeArtifactWithProvenance(
        request.artifactPath,
        { bytes: removed.bytes, mediaType: removed.mediaType },
        {
          provider: "fal",
          model,
          seed: null,
          prompt: "Remove the background while preserving the foreground subject.",
          refs: [stableRef],
          inputs: [hashInputReference(request.imageUrl, stableRef)],
          params,
          validation: {
            output_nonempty: true,
            base64_or_download: "validated",
            media_type: removed.mediaType,
            signature: "matched",
            source: removed.sourceKind,
            mask_requested: body.output_mask,
            mask_received: removed.mask !== undefined,
            caller: request.validate !== undefined,
            ...removed.callerFacts,
          },
          component: BACKGROUND_REMOVAL_COMPONENT,
          tool: config.tool ?? DEFAULT_TOOL_IDENTITY,
          timestamp: config.now?.().toISOString(),
          attempts,
          response: responseProvenance,
        },
        { secrets: [apiKey] },
      );

      return {
        ...removed,
        provider: "fal",
        model,
        attempts,
        provenancePath,
      };
    },
  };
}

async function parseBackgroundResponse(
  payload: Record<string, unknown>,
  response: Response,
  fetchImpl: typeof globalThis.fetch,
  signal: AbortSignal,
): Promise<{
  bytes: Uint8Array;
  mediaType: string;
  sourceUrl: string;
  width?: number;
  height?: number;
  maskImage?: BackgroundMaskMetadata;
  mask?: BackgroundMaskArtifact;
  responseMetadata: ProviderResponseMetadata;
  sourceKind: "data-uri" | "hosted-download";
}> {
  const root = isRecord(payload.data) ? payload.data : payload;
  if (!isRecord(root.image)) {
    throw new Error("fal background removal returned no image");
  }
  const image = root.image;
  assertNonEmptyString(image.url, "fal output image url");
  const declaredMediaType = optionalMediaType(image.content_type);
  const binary = await loadImageBytes(image.url, declaredMediaType, fetchImpl, signal);
  assertImageSignature(binary.bytes, binary.mediaType);

  const width = positiveIntegerOrUndefined(image.width);
  const height = positiveIntegerOrUndefined(image.height);
  const maskImage = isRecord(root.mask_image) ? parseMaskMetadata(root.mask_image) : undefined;
  const mask = maskImage
    ? await loadMaskArtifact(maskImage, fetchImpl, signal)
    : undefined;
  return {
    bytes: binary.bytes,
    mediaType: binary.mediaType,
    sourceUrl: image.url,
    ...(width !== undefined ? { width } : {}),
    ...(height !== undefined ? { height } : {}),
    ...(maskImage ? { maskImage } : {}),
    ...(mask ? { mask } : {}),
    sourceKind: binary.sourceKind,
    responseMetadata: responseMetadataFromHeaders(response),
  };
}

async function loadMaskArtifact(
  metadata: BackgroundMaskMetadata,
  fetchImpl: typeof globalThis.fetch,
  signal: AbortSignal,
): Promise<BackgroundMaskArtifact> {
  const binary = await loadImageBytes(metadata.url, metadata.mediaType, fetchImpl, signal);
  assertImageSignature(binary.bytes, binary.mediaType);
  return {
    ...metadata,
    bytes: binary.bytes,
    mediaType: binary.mediaType,
  };
}

async function loadImageBytes(
  sourceUrl: string,
  declaredMediaType: string | undefined,
  fetchImpl: typeof globalThis.fetch,
  signal: AbortSignal,
): Promise<BinaryArtifact & { sourceKind: "data-uri" | "hosted-download" }> {
  const dataMatch = /^data:([^;,]+);base64,(.+)$/i.exec(sourceUrl);
  if (dataMatch) {
    const mediaType = assertMediaType(dataMatch[1], "image");
    if (declaredMediaType && declaredMediaType !== mediaType) {
      throw new Error("fal data URI media type does not match response metadata");
    }
    return {
      bytes: decodeBase64Strict(dataMatch[2], "fal output image data"),
      mediaType,
      sourceKind: "data-uri",
    };
  }
  if (!/^https?:\/\//i.test(sourceUrl)) {
    throw new Error("fal output image url must be HTTP(S) or a base64 data URI");
  }
  const download = await fetchImpl(sourceUrl, { signal });
  assertSuccessfulResponse(download, "fal output image download");
  const headerMediaType = optionalMediaType(download.headers.get("content-type"));
  const mediaType = declaredMediaType ?? headerMediaType;
  if (!mediaType) throw new Error("fal output image media type is missing");
  if (declaredMediaType && headerMediaType && declaredMediaType !== headerMediaType) {
    throw new Error("fal output download media type does not match response metadata");
  }
  const bytes = new Uint8Array(await download.arrayBuffer());
  if (bytes.length === 0) throw new Error("fal output image download was empty");
  return {
    bytes,
    mediaType: assertMediaType(mediaType, "image"),
    sourceKind: "hosted-download",
  };
}

function parseMaskMetadata(value: Record<string, unknown>): BackgroundMaskMetadata | undefined {
  if (typeof value.url !== "string" || value.url.length === 0) return undefined;
  const mediaType = optionalMediaType(value.content_type);
  const width = positiveIntegerOrUndefined(value.width);
  const height = positiveIntegerOrUndefined(value.height);
  return {
    url: value.url,
    ...(mediaType ? { mediaType } : {}),
    ...(width !== undefined ? { width } : {}),
    ...(height !== undefined ? { height } : {}),
  };
}

function validateRequest(request: BackgroundRemovalRequest): void {
  assertNonEmptyString(request.imageUrl, "background removal imageUrl");
  assertNonEmptyString(request.artifactPath, "artifactPath");
  if (!/^(?:https?:\/\/|data:image\/[^;,]+;base64,)/i.test(request.imageUrl)) {
    throw new Error("imageUrl must be an HTTP(S) URL or base64 image data URL");
  }
  if (
    request.operatingResolution === "2304x2304" &&
    request.modelVariant !== "General Use (Dynamic)"
  ) {
    throw new Error("2304x2304 requires the General Use (Dynamic) model variant");
  }
}

function assertImageSignature(bytes: Uint8Array, mediaType: string): void {
  const matches =
    (mediaType === "image/png" &&
      startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) ||
    (mediaType === "image/webp" &&
      startsWith(bytes, [0x52, 0x49, 0x46, 0x46]) &&
      bytes.length >= 12 &&
      String.fromCharCode(...bytes.slice(8, 12)) === "WEBP") ||
    (mediaType === "image/gif" &&
      bytes.length >= 6 &&
      ["GIF87a", "GIF89a"].includes(String.fromCharCode(...bytes.slice(0, 6))));
  if (!matches) throw new Error(`image bytes do not match declared media type ${mediaType}`);
}

function optionalMediaType(value: unknown): string | undefined {
  if (typeof value !== "string" || value.trim().length === 0) return undefined;
  return assertMediaType(value.split(";", 1)[0].trim(), "image");
}

function positiveIntegerOrUndefined(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : undefined;
}

function startsWith(bytes: Uint8Array, expected: readonly number[]): boolean {
  return expected.every((value, index) => bytes[index] === value);
}

function normalizeBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  assertNonEmptyString(trimmed, "fal baseUrl");
  return trimmed;
}

function nonEmpty(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim() : fallback;
}
