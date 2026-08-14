import {
  assertNonEmptyString,
  assertSuccessfulResponse,
  DEFAULT_TOOL_IDENTITY,
  hashInputReference,
  isRecord,
  readJsonObject,
  responseMetadataFromHeaders,
  sanitizeReference,
  sha256Hex,
  withRetry,
  writeArtifactWithProvenance,
  type JsonObject,
  type ProviderResponseMetadata,
  type RetryOptions,
  type SoftwareIdentity,
} from "@stage-gen/core";

export const OPENROUTER_STRUCTURED_BASE_URL = "https://openrouter.ai/api/v1" as const;
export const STRUCTURED_GENERATION_COMPONENT = {
  name: "@stage-gen/structured-generation",
  version: "0.0.0",
} as const;

export interface StructuredReference {
  url: string;
  provenanceRef?: string;
}

export interface StructuredOutputSchema {
  name: string;
  description?: string;
  jsonSchema: JsonObject;
  strict?: boolean;
}

export interface OpenRouterStructuredGeneratorConfig {
  apiKey: string;
  model: string;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
  now?: () => Date;
  retry?: Omit<RetryOptions, "label" | "secrets" | "signal">;
  tool?: SoftwareIdentity;
}

export interface StructuredGenerationRequest<T> {
  prompt: string;
  system?: string;
  artifactPath: string;
  references?: readonly StructuredReference[];
  schema: StructuredOutputSchema;
  /** Parse and validate the decoded JSON. Throwing triggers the outer retry. */
  parse: (value: unknown) => T;
  temperature?: number;
  maxTokens?: number;
  seed?: number;
  /** Caller-owned stage/recipe metadata persisted under `params.metadata`. */
  metadata?: Record<string, unknown>;
  /** Cancels the active provider request, backoff, and remaining retries. */
  signal?: AbortSignal;
  /** Per-attempt timeout; defaults to the core policy. */
  timeoutMs?: number;
}

export interface StructuredGenerationResult<T> {
  value: T;
  rawText: string;
  provider: "openrouter";
  model: string;
  attempts: number;
  provenancePath: string;
  responseMetadata: ProviderResponseMetadata;
}

export interface OpenRouterStructuredGenerator {
  generate<T>(request: StructuredGenerationRequest<T>): Promise<StructuredGenerationResult<T>>;
}

export function createOpenRouterStructuredGenerator(
  config: OpenRouterStructuredGeneratorConfig,
): OpenRouterStructuredGenerator {
  assertNonEmptyString(config.apiKey, "OpenRouter apiKey");
  assertNonEmptyString(config.model, "OpenRouter structured model");
  const apiKey = config.apiKey;
  const model = config.model.trim();
  const baseUrl = normalizeBaseUrl(config.baseUrl ?? OPENROUTER_STRUCTURED_BASE_URL);
  const fetchImpl = config.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") throw new Error("a fetch implementation is required");

  return {
    async generate<T>(request: StructuredGenerationRequest<T>): Promise<StructuredGenerationResult<T>> {
      validateRequest(request);
      const references = request.references ?? [];
      const userContent: unknown =
        references.length === 0
          ? request.prompt
          : [
              { type: "text", text: request.prompt },
              ...references.map(({ url }) => ({
                type: "image_url",
                image_url: { url },
              })),
            ];
      const messages = [
        ...(request.system ? [{ role: "system", content: request.system }] : []),
        { role: "user", content: userContent },
      ];
      const body: Record<string, unknown> = {
        model,
        messages,
        response_format: {
          type: "json_schema",
          json_schema: {
            name: request.schema.name,
            ...(request.schema.description
              ? { description: request.schema.description }
              : {}),
            strict: request.schema.strict ?? true,
            schema: request.schema.jsonSchema,
          },
        },
        provider: { require_parameters: true },
      };
      if (request.temperature !== undefined) body.temperature = request.temperature;
      if (request.maxTokens !== undefined) body.max_tokens = request.maxTokens;
      if (request.seed !== undefined) body.seed = request.seed;

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
          assertSuccessfulResponse(response, "OpenRouter structured generation");
          const payload = await readJsonObject(response, "OpenRouter structured generation");
          const parsedResponse = parseStructuredResponse(payload, response);
          let value: T;
          try {
            value = request.parse(parsedResponse.decoded);
          } catch {
            throw new Error("OpenRouter structured output failed schema validation");
          }
          return { ...parsedResponse, value };
        },
        {
          ...config.retry,
          signal: request.signal,
          timeoutMs: request.timeoutMs ?? config.retry?.timeoutMs,
          label: "OpenRouter structured generation",
          secrets: [apiKey],
        },
      );

      const params: Record<string, unknown> = {
        schema_name: request.schema.name,
        schema: request.schema.jsonSchema,
        strict: request.schema.strict ?? true,
        require_parameters: true,
        ...(request.system
          ? { system: request.system, system_sha256: sha256Hex(request.system) }
          : {}),
        ...(request.temperature !== undefined ? { temperature: request.temperature } : {}),
        ...(request.maxTokens !== undefined ? { max_tokens: request.maxTokens } : {}),
        ...(request.seed !== undefined ? { seed: request.seed } : {}),
        ...(request.metadata ? { metadata: request.metadata } : {}),
      };
      const responseProvenance: Record<string, unknown> = {
        characters: generated.rawText.length,
        ...(generated.responseMetadata.requestId
          ? { request_id: generated.responseMetadata.requestId }
          : {}),
        ...(generated.responseMetadata.usage
          ? { usage: generated.responseMetadata.usage }
          : {}),
      };
      const artifactBytes = new TextEncoder().encode(`${JSON.stringify(generated.decoded, null, 2)}\n`);
      const provenancePath = await writeArtifactWithProvenance(
        request.artifactPath,
        { bytes: artifactBytes, mediaType: "application/json" },
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
            json: "parsed",
            schema: "caller-validated",
          },
          component: STRUCTURED_GENERATION_COMPONENT,
          tool: config.tool ?? DEFAULT_TOOL_IDENTITY,
          timestamp: config.now?.().toISOString(),
          attempts,
          response: responseProvenance,
        },
        { secrets: [apiKey] },
      );

      return {
        value: generated.value,
        rawText: generated.rawText,
        provider: "openrouter",
        model,
        attempts,
        provenancePath,
        responseMetadata: generated.responseMetadata,
      };
    },
  };
}

function parseStructuredResponse(
  payload: Record<string, unknown>,
  response: Response,
): {
  decoded: unknown;
  rawText: string;
  responseMetadata: ProviderResponseMetadata;
} {
  const firstChoice = Array.isArray(payload.choices) ? payload.choices[0] : undefined;
  if (!isRecord(firstChoice) || !isRecord(firstChoice.message)) {
    throw new Error("OpenRouter structured generation returned no message");
  }
  const message = firstChoice.message;
  let decoded: unknown;
  let rawText: string;
  if (isRecord(message.parsed)) {
    decoded = message.parsed;
    rawText = JSON.stringify(message.parsed);
  } else {
    rawText = extractTextContent(message.content);
    if (rawText.trim().length === 0) {
      throw new Error("OpenRouter structured generation returned empty content");
    }
    try {
      decoded = JSON.parse(rawText);
    } catch {
      throw new Error("OpenRouter structured generation returned invalid JSON content");
    }
  }

  const usage = isRecord(payload.usage) ? (payload.usage as JsonObject) : undefined;
  return {
    decoded,
    rawText,
    responseMetadata: {
      ...responseMetadataFromHeaders(response),
      ...(usage ? { usage } : {}),
    },
  };
}

function extractTextContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => (isRecord(part) && part.type === "text" && typeof part.text === "string" ? part.text : ""))
    .join("");
}

function validateRequest<T>(request: StructuredGenerationRequest<T>): void {
  assertNonEmptyString(request.prompt, "structured prompt");
  assertNonEmptyString(request.artifactPath, "artifactPath");
  assertNonEmptyString(request.schema.name, "schema name");
  if (!isRecord(request.schema.jsonSchema)) throw new Error("jsonSchema must be an object");
  if (typeof request.parse !== "function") throw new Error("parse must be a function");
  if (
    request.temperature !== undefined &&
    (!Number.isFinite(request.temperature) || request.temperature < 0 || request.temperature > 2)
  ) {
    throw new Error("temperature must be between 0 and 2");
  }
  if (
    request.maxTokens !== undefined &&
    (!Number.isInteger(request.maxTokens) || request.maxTokens < 1)
  ) {
    throw new Error("maxTokens must be a positive integer");
  }
  for (const reference of request.references ?? []) {
    assertNonEmptyString(reference.url, "structured reference url");
    if (!/^(?:https?:\/\/|data:image\/[^;,]+;base64,)/i.test(reference.url)) {
      throw new Error("structured references must be HTTP(S) URLs or base64 image data URLs");
    }
  }
}

function normalizeBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  assertNonEmptyString(trimmed, "OpenRouter baseUrl");
  return trimmed;
}
