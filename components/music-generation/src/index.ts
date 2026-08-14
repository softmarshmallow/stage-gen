import {
  assertMediaType,
  assertNonEmptyString,
  assertSuccessfulResponse,
  decodeBase64Strict,
  DEFAULT_TOOL_IDENTITY,
  hashInputReference,
  isRecord,
  responseMetadataFromHeaders,
  sanitizeReference,
  withRetry,
  writeArtifactWithProvenance,
  type BinaryArtifact,
  type ArtifactRights,
  type JsonObject,
  type ProviderResponseMetadata,
  type RetryOptions,
  type SoftwareIdentity,
} from "@stage-gen/core";

export * from "./normalization.ts";

export const OPENROUTER_MUSIC_MODEL = "google/lyria-3-pro-preview" as const;
export const OPENROUTER_MUSIC_BASE_URL = "https://openrouter.ai/api/v1" as const;
export const MUSIC_GENERATION_COMPONENT = {
  name: "@stage-gen/music-generation",
  version: "0.0.0",
} as const;

export type MusicOutputFormat = "mp3" | "wav";

export interface MusicReference {
  url: string;
  provenanceRef?: string;
}

export interface OpenRouterMusicGeneratorConfig {
  apiKey: string;
  model?: string;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  now?: () => Date;
  retry?: Omit<RetryOptions, "label" | "secrets" | "signal">;
  tool?: SoftwareIdentity;
}

export interface MusicGenerationRequest {
  /** Include duration/timestamps and instrumental/vocal direction in this prompt. */
  prompt: string;
  artifactPath: string;
  references?: readonly MusicReference[];
  outputFormat?: MusicOutputFormat;
  temperature?: number;
  topP?: number;
  seed?: number;
  maxTokens?: number;
  metadata?: Record<string, unknown>;
  /** Explicit rights decision; omitted means no decision has been recorded. */
  rights?: ArtifactRights;
  /** Cancels the active provider request, backoff, and remaining retries. */
  signal?: AbortSignal;
  /** Per-attempt timeout; defaults to the core policy. */
  timeoutMs?: number;
  /** Throwing here retries the complete provider call within the same retry owner. */
  validate?: (
    artifact: BinaryArtifact,
  ) => void | Record<string, unknown> | Promise<void | Record<string, unknown>>;
}

export interface MusicGenerationResult {
  bytes: Uint8Array;
  mediaType: string;
  text?: string;
  provider: "openrouter";
  model: string;
  attempts: number;
  provenancePath: string;
  responseMetadata: ProviderResponseMetadata;
}

export interface OpenRouterMusicGenerator {
  generate(request: MusicGenerationRequest): Promise<MusicGenerationResult>;
}

export function createOpenRouterMusicGenerator(
  config: OpenRouterMusicGeneratorConfig,
): OpenRouterMusicGenerator {
  assertNonEmptyString(config.apiKey, "OpenRouter apiKey");
  const apiKey = config.apiKey;
  const model = nonEmpty(config.model, OPENROUTER_MUSIC_MODEL);
  const baseUrl = normalizeBaseUrl(config.baseUrl ?? OPENROUTER_MUSIC_BASE_URL);
  const fetchImpl = config.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") throw new Error("a fetch implementation is required");

  return {
    async generate(request): Promise<MusicGenerationResult> {
      validateRequest(request);
      const references = request.references ?? [];
      const outputFormat = request.outputFormat ?? "mp3";
      const content: unknown =
        references.length === 0
          ? request.prompt
          : [
              { type: "text", text: request.prompt },
              ...references.map(({ url }) => ({
                type: "image_url",
                image_url: { url },
              })),
            ];
      const body: Record<string, unknown> = {
        model,
        messages: [{ role: "user", content }],
        modalities: ["text", "audio"],
        audio: { format: outputFormat },
        stream: true,
      };
      if (request.temperature !== undefined) body.temperature = request.temperature;
      if (request.topP !== undefined) body.top_p = request.topP;
      if (request.seed !== undefined) body.seed = request.seed;
      if (request.maxTokens !== undefined) body.max_tokens = request.maxTokens;

      let attempts = 0;
      const generated = await withRetry(
        async ({ attempt, signal }) => {
          attempts = attempt;
          const response = await fetchImpl(`${baseUrl}/chat/completions`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${apiKey}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
            signal,
          });
          assertSuccessfulResponse(response, "OpenRouter music generation");
          const parsed = await parseMusicResponse(response, outputFormat);
          const callerFacts = await request.validate?.({
            bytes: parsed.bytes,
            mediaType: parsed.mediaType,
          });
          if (callerFacts !== undefined && !isRecord(callerFacts)) {
            throw new Error("music validator must return an object or void");
          }
          return { ...parsed, callerFacts: callerFacts ?? {} };
        },
        {
          ...config.retry,
          signal: request.signal,
          timeoutMs: request.timeoutMs ?? config.retry?.timeoutMs,
          label: "OpenRouter music generation",
          secrets: [apiKey],
        },
      );

      const params: Record<string, unknown> = {
        output_format: outputFormat,
        modalities: ["text", "audio"],
        stream: true,
        validated: request.validate !== undefined,
        ...(request.temperature !== undefined ? { temperature: request.temperature } : {}),
        ...(request.topP !== undefined ? { top_p: request.topP } : {}),
        ...(request.seed !== undefined ? { seed: request.seed } : {}),
        ...(request.maxTokens !== undefined ? { max_tokens: request.maxTokens } : {}),
        ...(request.metadata ? { metadata: request.metadata } : {}),
      };
      const responseProvenance: Record<string, unknown> = {
        media_type: generated.mediaType,
        bytes: generated.bytes.length,
        source_shape: generated.sourceShape,
        ...(generated.text ? { text_characters: generated.text.length } : {}),
        ...(generated.responseMetadata.requestId
          ? { request_id: generated.responseMetadata.requestId }
          : {}),
        ...(generated.responseMetadata.usage
          ? { usage: generated.responseMetadata.usage }
          : {}),
      };
      const provenancePath = await writeArtifactWithProvenance(
        request.artifactPath,
        { bytes: generated.bytes, mediaType: generated.mediaType },
        {
          provider: "openrouter",
          model,
          seed: request.seed ?? null,
          prompt: request.prompt,
          refs: references.map((reference) =>
            reference.provenanceRef ?? sanitizeReference(reference.url),
          ),
          inputs: references.map((reference) =>
            hashInputReference(reference.url, reference.provenanceRef),
          ),
          params,
          validation: {
            output_nonempty: true,
            base64: "strict",
            media_type: generated.mediaType,
            signature: "matched",
            source_shape: generated.sourceShape,
            caller: request.validate !== undefined,
            ...generated.callerFacts,
          },
          component: MUSIC_GENERATION_COMPONENT,
          tool: config.tool ?? DEFAULT_TOOL_IDENTITY,
          timestamp: config.now?.().toISOString(),
          attempts,
          response: responseProvenance,
          ...(request.rights ? { rights: request.rights } : {}),
        },
        { secrets: [apiKey] },
      );

      return {
        bytes: generated.bytes,
        mediaType: generated.mediaType,
        ...(generated.text ? { text: generated.text } : {}),
        provider: "openrouter",
        model,
        attempts,
        provenancePath,
        responseMetadata: generated.responseMetadata,
      };
    },
  };
}

interface ParsedMusicResponse {
  bytes: Uint8Array;
  mediaType: string;
  text?: string;
  sourceShape: string;
  responseMetadata: ProviderResponseMetadata;
}

async function parseMusicResponse(
  response: Response,
  requestedFormat: MusicOutputFormat,
): Promise<ParsedMusicResponse> {
  const text = await response.text();
  if (text.trim().length === 0) {
    throw new Error("OpenRouter music generation returned an empty response");
  }
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (contentType.includes("text/event-stream") || /^\s*data:/m.test(text)) {
    return parseMusicSse(text, response, requestedFormat);
  }

  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error("OpenRouter music generation returned invalid JSON");
  }
  if (!isRecord(payload)) {
    throw new Error("OpenRouter music generation returned a non-object JSON response");
  }
  return parseBufferedMusic(payload, response, requestedFormat);
}

function parseMusicSse(
  text: string,
  response: Response,
  requestedFormat: MusicOutputFormat,
): ParsedMusicResponse {
  const audioChunks: string[] = [];
  const textChunks: string[] = [];
  const mediaTypes: string[] = [];
  let usage: JsonObject | undefined;
  let parsedEvents = 0;

  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const data = line.slice(5).trim();
    if (data === "" || data === "[DONE]") continue;
    let event: unknown;
    try {
      event = JSON.parse(data);
    } catch {
      throw new Error("OpenRouter music stream contained invalid JSON");
    }
    if (!isRecord(event)) throw new Error("OpenRouter music stream contained a non-object event");
    if (event.type === "error" || isRecord(event.error)) {
      throw new Error("OpenRouter music stream reported an error");
    }
    parsedEvents += 1;
    collectChatAudio(event, audioChunks, mediaTypes, textChunks);
    collectProviderNativeAudio(event, audioChunks, mediaTypes, textChunks);
    if (isRecord(event.usage)) usage = event.usage as JsonObject;
  }
  if (parsedEvents === 0) throw new Error("OpenRouter music stream contained no events");
  return finalizeAudio({
    audioChunks,
    mediaTypes,
    textChunks,
    requestedFormat,
    sourceShape: "sse",
    response,
    usage,
  });
}

function parseBufferedMusic(
  payload: Record<string, unknown>,
  response: Response,
  requestedFormat: MusicOutputFormat,
): ParsedMusicResponse {
  const audioChunks: string[] = [];
  const textChunks: string[] = [];
  const mediaTypes: string[] = [];
  collectChatAudio(payload, audioChunks, mediaTypes, textChunks);
  collectProviderNativeAudio(payload, audioChunks, mediaTypes, textChunks);
  return finalizeAudio({
    audioChunks,
    mediaTypes,
    textChunks,
    requestedFormat,
    sourceShape: "json",
    response,
    usage: isRecord(payload.usage) ? (payload.usage as JsonObject) : undefined,
  });
}

function collectChatAudio(
  payload: Record<string, unknown>,
  audioChunks: string[],
  mediaTypes: string[],
  textChunks: string[],
): void {
  if (!Array.isArray(payload.choices)) return;
  for (const choice of payload.choices) {
    if (!isRecord(choice)) continue;
    for (const holderName of ["delta", "message"] as const) {
      const holder = choice[holderName];
      if (!isRecord(holder)) continue;
      if (typeof holder.content === "string" && holder.content.length > 0) {
        textChunks.push(holder.content);
      } else if (Array.isArray(holder.content)) {
        collectContentBlocks(holder.content, audioChunks, mediaTypes, textChunks);
      }
      if (isRecord(holder.audio)) {
        collectAudioObject(holder.audio, audioChunks, mediaTypes, textChunks);
      }
    }
  }
}

function collectProviderNativeAudio(
  payload: Record<string, unknown>,
  audioChunks: string[],
  mediaTypes: string[],
  textChunks: string[],
): void {
  if (Array.isArray(payload.steps)) {
    for (const step of payload.steps) {
      if (isRecord(step) && step.type === "model_output" && Array.isArray(step.content)) {
        collectContentBlocks(step.content, audioChunks, mediaTypes, textChunks);
      }
    }
  }
  if (Array.isArray(payload.output)) {
    for (const output of payload.output) {
      if (isRecord(output) && Array.isArray(output.content)) {
        collectContentBlocks(output.content, audioChunks, mediaTypes, textChunks);
      }
    }
  }
  if (isRecord(payload.output_audio)) {
    collectAudioObject(payload.output_audio, audioChunks, mediaTypes, textChunks);
  }
}

function collectContentBlocks(
  blocks: unknown[],
  audioChunks: string[],
  mediaTypes: string[],
  textChunks: string[],
): void {
  for (const block of blocks) {
    if (!isRecord(block)) continue;
    if (block.type === "text" || block.type === "output_text") {
      if (typeof block.text === "string" && block.text.length > 0) textChunks.push(block.text);
      continue;
    }
    if (block.type === "audio" || block.type === "output_audio" || block.type === "input_audio") {
      if (isRecord(block.audio)) collectAudioObject(block.audio, audioChunks, mediaTypes, textChunks);
      else collectAudioObject(block, audioChunks, mediaTypes, textChunks);
    }
  }
}

function collectAudioObject(
  audio: Record<string, unknown>,
  audioChunks: string[],
  mediaTypes: string[],
  textChunks: string[],
): void {
  if (typeof audio.data === "string" && audio.data.length > 0) {
    const dataUri = /^data:([^;,]+);base64,(.+)$/i.exec(audio.data);
    if (dataUri) {
      mediaTypes.push(normalizeAudioMediaType(dataUri[1]));
      audioChunks.push(dataUri[2]);
    } else {
      audioChunks.push(audio.data);
    }
  }
  for (const key of ["media_type", "mime_type", "content_type", "format"] as const) {
    if (typeof audio[key] === "string" && audio[key].length > 0) {
      mediaTypes.push(normalizeAudioMediaType(audio[key]));
    }
  }
  if (typeof audio.transcript === "string" && audio.transcript.length > 0) {
    textChunks.push(audio.transcript);
  }
}

function finalizeAudio(args: {
  audioChunks: string[];
  mediaTypes: string[];
  textChunks: string[];
  requestedFormat: MusicOutputFormat;
  sourceShape: string;
  response: Response;
  usage?: JsonObject;
}): ParsedMusicResponse {
  if (args.audioChunks.length === 0) {
    throw new Error("OpenRouter music generation returned no audio data");
  }
  const mediaType = resolveMediaType(args.mediaTypes, args.requestedFormat);
  const bytes = decodeBase64Strict(args.audioChunks.join(""), "OpenRouter music audio data");
  assertAudioSignature(bytes, mediaType);
  const text = args.textChunks.join("").trim();
  return {
    bytes,
    mediaType,
    ...(text ? { text } : {}),
    sourceShape: args.sourceShape,
    responseMetadata: {
      ...responseMetadataFromHeaders(args.response),
      ...(args.usage ? { usage: args.usage } : {}),
    },
  };
}

function resolveMediaType(candidates: string[], requestedFormat: MusicOutputFormat): string {
  const fallback = requestedFormat === "mp3" ? "audio/mpeg" : "audio/wav";
  const unique = [...new Set(candidates.map(normalizeAudioMediaType))];
  if (unique.length > 1) {
    throw new Error(`OpenRouter music response declared conflicting media types: ${unique.join(", ")}`);
  }
  const mediaType = unique[0] ?? fallback;
  if (requestedFormat === "mp3" && mediaType !== "audio/mpeg") {
    throw new Error(`requested mp3 but received ${mediaType}`);
  }
  if (requestedFormat === "wav" && mediaType !== "audio/wav") {
    throw new Error(`requested wav but received ${mediaType}`);
  }
  return assertMediaType(mediaType, "audio");
}

function normalizeAudioMediaType(value: string): string {
  const normalized = value.trim().toLowerCase().split(";", 1)[0];
  if (normalized === "mp3" || normalized === "audio/mp3" || normalized === "audio/mpeg3") {
    return "audio/mpeg";
  }
  if (normalized === "wav" || normalized === "audio/x-wav" || normalized === "audio/wave") {
    return "audio/wav";
  }
  return assertMediaType(normalized, "audio");
}

function assertAudioSignature(bytes: Uint8Array, mediaType: string): void {
  const isMp3 =
    mediaType === "audio/mpeg" &&
    ((bytes.length >= 3 && String.fromCharCode(...bytes.slice(0, 3)) === "ID3") ||
      (bytes.length >= 2 && bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0));
  const isWav =
    mediaType === "audio/wav" &&
    bytes.length >= 12 &&
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WAVE";
  if (!isMp3 && !isWav) {
    throw new Error(`audio bytes do not match declared media type ${mediaType}`);
  }
}

function validateRequest(request: MusicGenerationRequest): void {
  assertNonEmptyString(request.prompt, "music prompt");
  assertNonEmptyString(request.artifactPath, "artifactPath");
  if (
    request.temperature !== undefined &&
    (!Number.isFinite(request.temperature) || request.temperature < 0 || request.temperature > 2)
  ) {
    throw new Error("temperature must be between 0 and 2");
  }
  if (
    request.topP !== undefined &&
    (!Number.isFinite(request.topP) || request.topP <= 0 || request.topP > 1)
  ) {
    throw new Error("topP must be greater than 0 and at most 1");
  }
  if (
    request.maxTokens !== undefined &&
    (!Number.isInteger(request.maxTokens) || request.maxTokens < 1)
  ) {
    throw new Error("maxTokens must be a positive integer");
  }
  for (const reference of request.references ?? []) {
    assertNonEmptyString(reference.url, "music reference url");
    if (!/^(?:https?:\/\/|data:image\/[^;,]+;base64,)/i.test(reference.url)) {
      throw new Error("music references must be HTTP(S) URLs or base64 image data URLs");
    }
  }
}

function normalizeBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  assertNonEmptyString(trimmed, "OpenRouter baseUrl");
  return trimmed;
}

function nonEmpty(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim() : fallback;
}
