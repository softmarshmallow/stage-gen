import { createHash, randomUUID } from "node:crypto";
import {
  access as nodeAccess,
  mkdir as nodeMkdir,
  readFile as nodeReadFile,
  rename as nodeRename,
  rm as nodeRm,
  writeFile as nodeWriteFile,
} from "node:fs/promises";
import { basename, dirname, join } from "node:path";

/** Five retries after the initial attempt. */
export const AI_RETRY_COUNT = 5 as const;
export const MAX_AI_ATTEMPTS = 6 as const;
export const DEFAULT_AI_ATTEMPT_TIMEOUT_MS = 300_000 as const;
export const CORE_COMPONENT = { name: "@stage-gen/core", version: "0.0.0" } as const;
export const DEFAULT_TOOL_IDENTITY = { name: "stage-gen", version: "0.0.0" } as const;

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export interface RetryContext {
  /** One-based attempt number. Attempt one is the initial call. */
  attempt: number;
  /** Zero-based retry number. Attempt one has retry=0. */
  retry: number;
  maxAttempts: typeof MAX_AI_ATTEMPTS;
  /** Per-attempt signal linked to caller cancellation and timeout. */
  signal: AbortSignal;
}

export interface RetryOptions {
  label?: string;
  initialDelayMs?: number;
  backoffFactor?: number;
  maxDelayMs?: number;
  /** Per-attempt timeout. Defaults to five minutes. */
  timeoutMs?: number;
  /** Cancels the active attempt, pending backoff, and all later retries. */
  signal?: AbortSignal;
  sleep?: (delayMs: number, signal?: AbortSignal) => Promise<void>;
  secrets?: readonly string[];
  onAttemptFailure?: (context: RetryContext, error: Error, nextDelayMs: number) => void;
}

export class RetryExhaustedError extends Error {
  readonly attempts = MAX_AI_ATTEMPTS;
  readonly retries = AI_RETRY_COUNT;

  constructor(label: string, cause: Error) {
    super(
      `${label} failed after ${MAX_AI_ATTEMPTS} attempts (${AI_RETRY_COUNT} retries): ${cause.message}`,
      { cause },
    );
    this.name = "RetryExhaustedError";
  }
}

/**
 * Run one AI operation once, then retry it five times. The operation must
 * disable provider/SDK retry so there is exactly one retry owner.
 */
export async function withRetry<T>(
  operation: (context: RetryContext) => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const label = nonEmptyOr(options.label, "AI operation");
  const initialDelayMs = nonNegativeFinite(options.initialDelayMs, 500);
  const backoffFactor = positiveFinite(options.backoffFactor, 2);
  const maxDelayMs = nonNegativeFinite(options.maxDelayMs, 8_000);
  const timeoutMs = positiveFinite(options.timeoutMs, DEFAULT_AI_ATTEMPT_TIMEOUT_MS);
  const sleep = options.sleep ?? defaultSleep;
  let delayMs = initialDelayMs;
  let lastError = new Error("unknown failure");

  for (let attempt = 1; attempt <= MAX_AI_ATTEMPTS; attempt += 1) {
    throwIfAborted(options.signal, options.secrets);
    const attemptController = new AbortController();
    const unlink = linkAbortSignal(options.signal, attemptController);
    let timedOut = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const context: RetryContext = {
      attempt,
      retry: attempt - 1,
      maxAttempts: MAX_AI_ATTEMPTS,
      signal: attemptController.signal,
    };

    try {
      const timeout = new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => {
          timedOut = true;
          attemptController.abort();
          reject(new Error(`${label} timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      });
      return await Promise.race([operation(context), timeout]);
    } catch (error) {
      if (options.signal?.aborted) {
        throw abortError(options.signal, options.secrets);
      }
      lastError = sanitizeError(
        timedOut ? new Error(`${label} timed out after ${timeoutMs}ms`) : error,
        options.secrets,
      );
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      unlink();
    }

    if (attempt === MAX_AI_ATTEMPTS) break;
    const nextDelayMs = Math.min(delayMs, maxDelayMs);
    options.onAttemptFailure?.(context, lastError, nextDelayMs);
    if (nextDelayMs > 0) {
      await sleepWithSignal(sleep, nextDelayMs, options.signal, options.secrets);
    }
    delayMs = Math.min(delayMs * backoffFactor, maxDelayMs);
  }

  throw new RetryExhaustedError(label, lastError);
}

export interface SoftwareIdentity {
  name: string;
  version: string;
}

export interface InputProvenance {
  ref: string;
  sha256: string;
  source: "content" | "reference";
  bytes?: number;
  media_type?: string;
}

export interface ArtifactDigest {
  sha256: string;
  bytes: number;
  media_type: string;
}

export type ArtifactRightsStatus =
  | "unreviewed"
  | "restricted"
  | "redistribution-approved";

interface ArtifactRightsBase {
  /** Human-readable notice text or a stable repository-relative notice reference. */
  notice: string;
  attribution: string[];
  basis: string[];
}

export type ArtifactRights =
  | (ArtifactRightsBase & {
      status: "unreviewed";
      license_id: null;
      reviewed_at: null;
    })
  | (ArtifactRightsBase & {
      status: "restricted";
      license_id: string | null;
      reviewed_at: string;
    })
  | (ArtifactRightsBase & {
      status: "redistribution-approved";
      license_id: string;
      reviewed_at: string;
    });

export interface ArtifactProvenance {
  schema_version: 1;
  provider: string;
  model: string;
  /** Explicitly null when the provider exposes no usable seed. */
  seed: number | null;
  prompt: string;
  prompt_sha256: string;
  references: string[];
  refs: string[];
  inputs: InputProvenance[];
  params: JsonObject;
  validation: JsonObject;
  component: SoftwareIdentity;
  tool: SoftwareIdentity;
  artifact?: ArtifactDigest;
  /** Absent means no rights decision has been recorded. */
  rights?: ArtifactRights;
  ts: string;
  attempts: number;
  retries: number;
  response?: JsonObject;
}

export interface ProvenanceInput {
  provider: string;
  model: string;
  seed?: number | null;
  prompt: string;
  refs?: readonly string[];
  inputs?: readonly InputProvenance[];
  params?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  component?: SoftwareIdentity;
  tool?: SoftwareIdentity;
  timestamp?: string;
  attempts: number;
  response?: Record<string, unknown>;
  /** Explicit rights decision only; provenance writers never infer approval. */
  rights?: ArtifactRights;
}

export interface WriteProvenanceOptions {
  now?: () => Date;
  secrets?: readonly string[];
}

export interface BinaryArtifact {
  bytes: Uint8Array;
  mediaType: string;
}

export interface ProviderResponseMetadata {
  requestId?: string;
  created?: number;
  usage?: JsonObject;
}

export interface AtomicFileSystem {
  mkdir(path: string): Promise<void>;
  writeFile(path: string, data: Uint8Array | string): Promise<void>;
  rename(from: string, to: string): Promise<void>;
  rm(path: string): Promise<void>;
  access(path: string): Promise<void>;
}

export interface WriteArtifactOptions extends WriteProvenanceOptions {
  /** Test seam for proving paired-write rollback behavior. */
  fileSystem?: AtomicFileSystem;
}

export interface ArtifactRightsFileSystem {
  mkdir(path: string): Promise<void>;
  readFile(path: string): Promise<Uint8Array>;
  writeFile(path: string, data: string): Promise<void>;
  rename(from: string, to: string): Promise<void>;
  rm(path: string): Promise<void>;
}

export interface RecordArtifactRightsOptions extends WriteProvenanceOptions {
  /** Defaults to `<artifactPath>.meta.json`. */
  provenancePath?: string;
  /** Test seam for atomic replacement and cleanup assertions. */
  fileSystem?: ArtifactRightsFileSystem;
}

const defaultAtomicFileSystem: AtomicFileSystem = {
  async mkdir(path) {
    await nodeMkdir(path, { recursive: true });
  },
  async writeFile(path, data) {
    await nodeWriteFile(path, data, { flag: "wx", mode: 0o600 });
  },
  async rename(from, to) {
    await nodeRename(from, to);
  },
  async rm(path) {
    await nodeRm(path, { force: true, recursive: true });
  },
  async access(path) {
    await nodeAccess(path);
  },
};

const defaultArtifactRightsFileSystem: ArtifactRightsFileSystem = {
  async mkdir(path) {
    await nodeMkdir(path, { recursive: true });
  },
  async readFile(path) {
    return new Uint8Array(await nodeReadFile(path));
  },
  async writeFile(path, data) {
    await nodeWriteFile(path, data, { flag: "wx", mode: 0o600 });
  },
  async rename(from, to) {
    await nodeRename(from, to);
  },
  async rm(path) {
    await nodeRm(path, { force: true });
  },
};

/**
 * Persist artifact bytes and `<artifactPath>.meta.json` from staged files.
 * If either commit fails, both new outputs are removed and prior outputs are
 * restored when present.
 */
export async function writeArtifactWithProvenance(
  artifactPath: string,
  artifact: BinaryArtifact,
  input: ProvenanceInput,
  options: WriteArtifactOptions = {},
): Promise<string> {
  assertNonEmptyString(artifactPath, "artifactPath");
  if (!(artifact.bytes instanceof Uint8Array) || artifact.bytes.length === 0) {
    throw new Error("artifact bytes must be non-empty");
  }
  assertMediaType(artifact.mediaType, mediaFamily(artifact.mediaType));

  const metaPath = `${artifactPath}.meta.json`;
  const safe = buildProvenance(input, artifact, options);
  const serialized = `${JSON.stringify(safe, null, 2)}\n`;
  const fs = options.fileSystem ?? defaultAtomicFileSystem;
  const token = randomUUID();
  const artifactTemp = join(dirname(artifactPath), `.${basename(artifactPath)}.${token}.tmp`);
  const metaTemp = join(dirname(metaPath), `.${basename(metaPath)}.${token}.tmp`);
  const artifactBackup = `${artifactTemp}.backup`;
  const metaBackup = `${metaTemp}.backup`;
  let artifactBackedUp = false;
  let metaBackedUp = false;
  let artifactInstalled = false;
  let metaInstalled = false;

  await fs.mkdir(dirname(artifactPath));
  await fs.mkdir(dirname(metaPath));

  try {
    await fs.writeFile(artifactTemp, artifact.bytes);
    await fs.writeFile(metaTemp, serialized);
    if (await pathExists(fs, artifactPath)) {
      await fs.rename(artifactPath, artifactBackup);
      artifactBackedUp = true;
    }
    if (await pathExists(fs, metaPath)) {
      await fs.rename(metaPath, metaBackup);
      metaBackedUp = true;
    }
    await fs.rename(artifactTemp, artifactPath);
    artifactInstalled = true;
    await fs.rename(metaTemp, metaPath);
    metaInstalled = true;
    await safeRemove(fs, artifactBackup);
    await safeRemove(fs, metaBackup);
    return metaPath;
  } catch (error) {
    if (metaInstalled) await safeRemove(fs, metaPath);
    if (artifactInstalled) await safeRemove(fs, artifactPath);
    let rollbackError: unknown;
    try {
      if (artifactBackedUp) await fs.rename(artifactBackup, artifactPath);
      if (metaBackedUp) await fs.rename(metaBackup, metaPath);
    } catch (restoreError) {
      rollbackError = restoreError;
    }
    await safeRemove(fs, artifactTemp);
    await safeRemove(fs, metaTemp);
    await safeRemove(fs, artifactBackup);
    await safeRemove(fs, metaBackup);
    if (rollbackError) {
      throw sanitizeError(
        new Error(`artifact pair persistence failed and rollback was incomplete: ${errorMessage(error)}`),
        options.secrets,
      );
    }
    throw sanitizeError(error, options.secrets);
  }
}

/** Legacy sidecar-only writer. AI adapters use `writeArtifactWithProvenance`. */
export async function writeProvenance(
  artifactPath: string,
  input: ProvenanceInput,
  options: WriteProvenanceOptions = {},
): Promise<string> {
  assertNonEmptyString(artifactPath, "artifactPath");
  const metaPath = `${artifactPath}.meta.json`;
  const safe = buildProvenance(input, undefined, options);
  const token = randomUUID();
  const tempPath = join(dirname(metaPath), `.${basename(metaPath)}.${token}.tmp`);
  await nodeMkdir(dirname(metaPath), { recursive: true });
  try {
    await nodeWriteFile(tempPath, `${JSON.stringify(safe, null, 2)}\n`, {
      encoding: "utf8",
      flag: "wx",
      mode: 0o600,
    });
    await nodeRename(tempPath, metaPath);
    return metaPath;
  } catch (error) {
    await nodeRm(tempPath, { force: true });
    throw sanitizeError(error, options.secrets);
  }
}

/**
 * Validate and atomically attach an explicit rights decision to an existing
 * artifact sidecar. The artifact bytes must still match the recorded digest.
 */
export async function recordArtifactRights(
  artifactPath: string,
  rights: ArtifactRights,
  options: RecordArtifactRightsOptions = {},
): Promise<string> {
  assertNonEmptyString(artifactPath, "artifactPath");
  const provenancePath = options.provenancePath ?? `${artifactPath}.meta.json`;
  assertNonEmptyString(provenancePath, "provenancePath");
  const validatedRights = parseArtifactRights(rights);
  const fs = options.fileSystem ?? defaultArtifactRightsFileSystem;
  const artifactBytes = await fs.readFile(artifactPath);
  const originalProvenanceBytes = await fs.readFile(provenancePath);
  const provenance = parseProvenanceObject(originalProvenanceBytes);
  assertArtifactBinding(provenance, artifactBytes);
  if (validatedRights.status === "redistribution-approved") {
    assertPortableProvenanceReferences(provenance);
  }

  const updated = sanitizeForPersistence(
    { ...provenance, rights: validatedRights },
    options.secrets,
  ) as JsonObject;
  const serialized = `${JSON.stringify(updated, null, 2)}\n`;
  const token = randomUUID();
  const tempPath = join(
    dirname(provenancePath),
    `.${basename(provenancePath)}.${token}.tmp`,
  );
  await fs.mkdir(dirname(provenancePath));
  try {
    await fs.writeFile(tempPath, serialized);

    // Do not stamp rights onto bytes or provenance that changed mid-operation.
    const currentArtifactBytes = await fs.readFile(artifactPath);
    assertArtifactBinding(provenance, currentArtifactBytes);
    const currentProvenanceBytes = await fs.readFile(provenancePath);
    if (sha256Hex(currentProvenanceBytes) !== sha256Hex(originalProvenanceBytes)) {
      throw new Error("artifact provenance changed while recording rights");
    }

    await fs.rename(tempPath, provenancePath);
    return provenancePath;
  } catch (error) {
    await safeRemoveRightsFile(fs, tempPath);
    throw sanitizeError(error, options.secrets);
  }
}

export function assertArtifactRights(value: unknown): asserts value is ArtifactRights {
  parseArtifactRights(value);
}

export function parseArtifactRights(value: unknown): ArtifactRights {
  if (!isRecord(value)) throw new Error("artifact rights must be an object");
  const allowedKeys = new Set([
    "status",
    "license_id",
    "notice",
    "attribution",
    "basis",
    "reviewed_at",
  ]);
  for (const key of Object.keys(value)) {
    if (!allowedKeys.has(key)) throw new Error(`artifact rights contains unknown field: ${key}`);
  }
  if (
    value.status !== "unreviewed" &&
    value.status !== "restricted" &&
    value.status !== "redistribution-approved"
  ) {
    throw new Error("artifact rights status is invalid");
  }
  assertNonEmptyString(value.notice, "artifact rights notice");
  const attribution = stringArray(value.attribution, "artifact rights attribution");
  const basis = stringArray(value.basis, "artifact rights basis");
  const licenseId = nullableNonEmptyString(value.license_id, "artifact rights license_id");
  const reviewedAt = nullableIsoTimestamp(value.reviewed_at, "artifact rights reviewed_at");

  if (value.status === "unreviewed") {
    if (licenseId !== null) throw new Error("unreviewed artifact rights must not name a license");
    if (reviewedAt !== null) {
      throw new Error("unreviewed artifact rights must have reviewed_at=null");
    }
    return {
      status: "unreviewed",
      license_id: null,
      notice: value.notice,
      attribution,
      basis,
      reviewed_at: null,
    };
  }

  if (basis.length === 0) {
    throw new Error(`${value.status} artifact rights must record at least one basis`);
  }
  if (reviewedAt === null) {
    throw new Error(`${value.status} artifact rights must record reviewed_at`);
  }
  if (value.status === "redistribution-approved") {
    if (licenseId === null) {
      throw new Error("redistribution-approved artifact rights must name a license");
    }
    return {
      status: "redistribution-approved",
      license_id: licenseId,
      notice: value.notice,
      attribution,
      basis,
      reviewed_at: reviewedAt,
    };
  }
  return {
    status: "restricted",
    license_id: licenseId,
    notice: value.notice,
    attribution,
    basis,
    reviewed_at: reviewedAt,
  };
}

/** True only for content digests, safe relative refs, or non-private HTTPS URLs. */
export function isPortableArtifactReference(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()) return false;
  if (/^sha256:[a-f0-9]{64}$/.test(value)) return true;
  if (isTemporaryArtifactReference(value)) return false;
  if (/^(?:file|data):/i.test(value)) return false;
  if (/^(?:[a-z]:[\\/]|\\\\|\/)/i.test(value)) return false;

  try {
    const url = new URL(value);
    if (url.protocol !== "https:") return false;
    if (url.username || url.password || url.search || url.hash) return false;
    return !isPrivateHostname(url.hostname);
  } catch {
    if (value.includes(":") || value.includes("?") || value.includes("#") || value.includes("\\")) {
      return false;
    }
    const segments = value.split("/");
    return segments.every((segment) =>
      segment.length > 0 && segment !== "." && segment !== ".." && !segment.startsWith(".")
    );
  }
}

export function isTemporaryArtifactReference(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const normalized = value.trim().replaceAll("\\", "/").toLowerCase();
  if (
    normalized.startsWith("/tmp/") ||
    normalized.startsWith("/private/tmp/") ||
    normalized.startsWith("/var/folders/") ||
    normalized.includes("/appdata/local/temp/")
  ) {
    return true;
  }
  return normalized.split("/").some((segment) =>
    segment === "tmp" || segment === "temp" || segment.endsWith(".tmp")
  );
}

export function sha256Hex(value: Uint8Array | string): string {
  return createHash("sha256").update(value).digest("hex");
}

/** Hash data-URI bytes when available, otherwise hash the sanitized reference. */
export function hashInputReference(reference: string, provenanceRef?: string): InputProvenance {
  assertNonEmptyString(reference, "input reference");
  const stableRef = provenanceRef?.trim() || sanitizeReference(reference);
  const dataMatch = /^data:([^;,]+);base64,(.+)$/i.exec(reference.trim());
  if (dataMatch) {
    const bytes = decodeBase64Strict(dataMatch[2], "input reference data");
    return {
      ref: stableRef,
      sha256: sha256Hex(bytes),
      source: "content",
      bytes: bytes.length,
      media_type: dataMatch[1].toLowerCase(),
    };
  }
  return {
    ref: stableRef,
    sha256: sha256Hex(sanitizeReference(reference)),
    source: "reference",
  };
}

export function sanitizeReference(reference: string): string {
  const trimmed = reference.trim();
  const dataMatch = /^data:([^;,]+)(?:;[^,]*)?,/i.exec(trimmed);
  if (dataMatch) return `data:${dataMatch[1].toLowerCase()};base64,[REDACTED]`;

  try {
    const url = new URL(trimmed);
    if (url.protocol === "http:" || url.protocol === "https:") {
      url.username = "";
      url.password = "";
      url.search = "";
      url.hash = "";
      return url.toString();
    }
  } catch {
    // Local paths and stable caller-provided reference ids are preserved.
  }
  return trimmed;
}

export function redactSecrets(value: string, secrets: readonly string[] = []): string {
  let redacted = value;
  for (const secret of secrets) {
    if (secret.length > 0) redacted = redacted.split(secret).join("[REDACTED]");
  }

  return redacted
    .replace(/data:([^\s;,"')]+)(?:;[^,\s]*)?;base64,[A-Za-z0-9+/_=-]+/gi, "data:$1;base64,[REDACTED]")
    .replace(/((?:b64_json|base64|audio_data|image_data)["']?\s*[:=]\s*["'])[A-Za-z0-9+/_=-]+(["'])/gi, "$1[REDACTED]$2")
    .replace(/(authorization\s*[:=]\s*)(?:bearer|key)\s+[^\s,"'}]+/gi, "$1[REDACTED]")
    .replace(/(["']?(?:api[_-]?key|token|secret|credential)["']?\s*[:=]\s*["'])[^"']+(["'])/gi, "$1[REDACTED]$2")
    .replace(/\bsk-(?:or-)?[A-Za-z0-9_-]{8,}\b/g, "[REDACTED]")
    .replace(/\b[A-Za-z0-9+/]{80,}={0,2}\b/g, "[REDACTED_BASE64]");
}

export function decodeBase64Strict(value: unknown, label = "base64 data"): Uint8Array {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty base64 string`);
  }
  if (
    value.length % 4 !== 0 ||
    !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)
  ) {
    throw new Error(`${label} is not valid base64`);
  }
  const bytes = Uint8Array.from(Buffer.from(value, "base64"));
  if (bytes.length === 0) throw new Error(`${label} decoded to empty bytes`);
  return bytes;
}

export function assertMediaType(value: unknown, family: "image" | "audio" | "application"): string {
  if (typeof value !== "string") throw new Error(`${family} media type is missing`);
  const normalized = value.trim().toLowerCase();
  if (!normalized.startsWith(`${family}/`) || normalized.includes(";")) {
    throw new Error(`invalid ${family} media type: ${redactSecrets(String(value))}`);
  }
  return normalized;
}

export function assertNonEmptyString(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function readJsonObject(
  response: Response,
  label: string,
): Promise<Record<string, unknown>> {
  const text = await response.text();
  if (text.trim().length === 0) throw new Error(`${label} returned an empty response`);
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} returned invalid JSON`);
  }
  if (!isRecord(parsed)) throw new Error(`${label} returned a non-object JSON response`);
  return parsed;
}

export function assertSuccessfulResponse(response: Response, label: string): void {
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
}

export function responseMetadataFromHeaders(response: Response): ProviderResponseMetadata {
  const requestId =
    response.headers.get("x-request-id") ??
    response.headers.get("x-openrouter-request-id") ??
    response.headers.get("request-id") ??
    undefined;
  return requestId ? { requestId } : {};
}

function buildProvenance(
  input: ProvenanceInput,
  artifact: BinaryArtifact | undefined,
  options: WriteProvenanceOptions,
): ArtifactProvenance {
  assertNonEmptyString(input.provider, "provider");
  assertNonEmptyString(input.model, "model");
  assertNonEmptyString(input.prompt, "prompt");
  if (!Number.isInteger(input.attempts) || input.attempts < 1 || input.attempts > MAX_AI_ATTEMPTS) {
    throw new Error(`attempts must be an integer from 1 to ${MAX_AI_ATTEMPTS}`);
  }
  const component = input.component ?? CORE_COMPONENT;
  const tool = input.tool ?? DEFAULT_TOOL_IDENTITY;
  assertSoftwareIdentity(component, "component");
  assertSoftwareIdentity(tool, "tool");
  for (const entry of input.inputs ?? []) assertInputProvenance(entry);
  if (input.seed !== undefined && input.seed !== null && !Number.isInteger(input.seed)) {
    throw new Error("seed must be an integer or null");
  }

  const references = [...(input.refs ?? [])].map(sanitizeReference);
  const rights = input.rights === undefined ? undefined : parseArtifactRights(input.rights);

  const raw: ArtifactProvenance = {
    schema_version: 1,
    provider: input.provider,
    model: input.model,
    seed: input.seed ?? null,
    prompt: input.prompt,
    prompt_sha256: sha256Hex(input.prompt),
    references,
    refs: references,
    inputs: [...(input.inputs ?? [])].map((entry) => ({
      ...entry,
      ref: sanitizeReference(entry.ref),
    })),
    params: sanitizeForPersistence(input.params ?? {}, options.secrets) as JsonObject,
    validation: sanitizeForPersistence(input.validation ?? {}, options.secrets) as JsonObject,
    component: { ...component },
    tool: { ...tool },
    ...(artifact
      ? {
          artifact: {
            sha256: sha256Hex(artifact.bytes),
            bytes: artifact.bytes.length,
            media_type: artifact.mediaType,
          },
        }
      : {}),
    ...(rights ? { rights } : {}),
    ts: input.timestamp ?? (options.now ?? (() => new Date()))().toISOString(),
    attempts: input.attempts,
    retries: input.attempts - 1,
    ...(input.response
      ? { response: sanitizeForPersistence(input.response, options.secrets) as JsonObject }
      : {}),
  };
  if (rights?.status === "redistribution-approved") {
    assertPortableProvenanceReferences(raw as unknown as Record<string, unknown>);
  }
  return sanitizeForPersistence(raw, options.secrets) as unknown as ArtifactProvenance;
}

function parseProvenanceObject(bytes: Uint8Array): Record<string, unknown> {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("artifact provenance is not valid UTF-8");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("artifact provenance is not valid JSON");
  }
  if (!isRecord(parsed)) throw new Error("artifact provenance must be an object");
  return parsed;
}

function assertArtifactBinding(
  provenance: Record<string, unknown>,
  artifactBytes: Uint8Array,
): void {
  if (!isRecord(provenance.artifact)) {
    throw new Error("artifact provenance has no artifact digest");
  }
  const digest = provenance.artifact;
  if (typeof digest.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(digest.sha256)) {
    throw new Error("artifact provenance SHA-256 is invalid");
  }
  if (!Number.isInteger(digest.bytes) || (digest.bytes as number) < 0) {
    throw new Error("artifact provenance byte count is invalid");
  }
  if (artifactBytes.length !== digest.bytes || sha256Hex(artifactBytes) !== digest.sha256) {
    throw new Error("artifact bytes do not match provenance digest");
  }
}

function assertPortableProvenanceReferences(provenance: Record<string, unknown>): void {
  for (const field of ["references", "refs"] as const) {
    const references = provenance[field];
    if (references === undefined) continue;
    if (!Array.isArray(references)) throw new Error(`artifact provenance ${field} must be an array`);
    for (const reference of references) {
      if (!isPortableArtifactReference(reference)) {
        throw new Error(`redistribution-approved provenance contains an unsafe reference in ${field}`);
      }
    }
  }
  if (provenance.inputs === undefined) return;
  if (!Array.isArray(provenance.inputs)) {
    throw new Error("artifact provenance inputs must be an array");
  }
  for (const input of provenance.inputs) {
    if (!isRecord(input) || !isPortableArtifactReference(input.ref)) {
      throw new Error("redistribution-approved provenance contains unsafe input reference");
    }
  }
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value.map((entry, index) => {
    assertNonEmptyString(entry, `${label}[${index}]`);
    if (entry !== entry.trim()) throw new Error(`${label}[${index}] must be trimmed`);
    return entry;
  });
}

function nullableNonEmptyString(value: unknown, label: string): string | null {
  if (value === null) return null;
  assertNonEmptyString(value, label);
  if (value !== value.trim()) throw new Error(`${label} must be trimmed`);
  return value;
}

function nullableIsoTimestamp(value: unknown, label: string): string | null {
  if (value === null) return null;
  assertNonEmptyString(value, label);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(value)) {
    throw new Error(`${label} must be a UTC ISO-8601 timestamp or null`);
  }
  if (!Number.isFinite(Date.parse(value))) {
    throw new Error(`${label} must be a valid UTC ISO-8601 timestamp or null`);
  }
  return value;
}

function isPrivateHostname(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[/, "").replace(/\]$/, "");
  if (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    host === "::1" ||
    /^(?:fc|fd|fe[89ab])[a-f0-9:]*$/i.test(host)
  ) {
    return true;
  }
  const ipv4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!ipv4) return false;
  const octets = ipv4.slice(1).map(Number);
  if (octets.some((part) => part > 255)) return true;
  return octets[0] === 0 || octets[0] === 10 || octets[0] === 127 ||
    (octets[0] === 169 && octets[1] === 254) ||
    (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
    (octets[0] === 192 && octets[1] === 168);
}

function assertSoftwareIdentity(value: SoftwareIdentity, label: string): void {
  assertNonEmptyString(value.name, `${label}.name`);
  assertNonEmptyString(value.version, `${label}.version`);
}

function assertInputProvenance(value: InputProvenance): void {
  assertNonEmptyString(value.ref, "input.ref");
  if (!/^[a-f0-9]{64}$/.test(value.sha256)) throw new Error("input.sha256 must be lowercase SHA-256");
  if (value.bytes !== undefined && (!Number.isInteger(value.bytes) || value.bytes < 0)) {
    throw new Error("input.bytes must be a non-negative integer");
  }
}

function sanitizeForPersistence(value: unknown, secrets: readonly string[] = [], key = ""): JsonValue {
  if (value === null || typeof value === "boolean" || typeof value === "number") return value;
  if (typeof value === "string") {
    if (/(?:api[_-]?key|authorization|token|secret|credential)/i.test(key)) {
      return "[REDACTED]";
    }
    if (/^data:[^,]+,/i.test(value)) return sanitizeReference(value);
    return redactSecrets(value, secrets);
  }
  if (Array.isArray(value)) {
    return value.map((entry) => sanitizeForPersistence(entry, secrets, key));
  }
  if (isRecord(value)) {
    const result: JsonObject = {};
    for (const [childKey, childValue] of Object.entries(value)) {
      if (childValue !== undefined) {
        result[childKey] = sanitizeForPersistence(childValue, secrets, childKey);
      }
    }
    return result;
  }
  throw new Error(`provenance contains unsupported value at ${key || "root"}`);
}

function sanitizeError(error: unknown, secrets: readonly string[] = []): Error {
  const source = error instanceof Error ? error : new Error(String(error));
  const sanitized = new Error(redactSecrets(source.message, secrets));
  sanitized.name = source.name;
  return sanitized;
}

function abortError(signal: AbortSignal, secrets: readonly string[] = []): Error {
  const reason = signal.reason;
  const message = reason instanceof Error ? reason.message : typeof reason === "string" ? reason : "cancelled";
  const error = new Error(redactSecrets(`AI operation cancelled: ${message}`, secrets));
  error.name = "AbortError";
  return error;
}

function throwIfAborted(signal: AbortSignal | undefined, secrets: readonly string[] = []): void {
  if (signal?.aborted) throw abortError(signal, secrets);
}

function linkAbortSignal(source: AbortSignal | undefined, target: AbortController): () => void {
  if (!source) return () => {};
  const abort = () => target.abort();
  if (source.aborted) abort();
  else source.addEventListener("abort", abort, { once: true });
  return () => source.removeEventListener("abort", abort);
}

async function sleepWithSignal(
  sleep: (delayMs: number, signal?: AbortSignal) => Promise<void>,
  delayMs: number,
  signal: AbortSignal | undefined,
  secrets: readonly string[] = [],
): Promise<void> {
  throwIfAborted(signal, secrets);
  if (!signal) {
    await sleep(delayMs);
    return;
  }
  await Promise.race([
    sleep(delayMs, signal),
    new Promise<never>((_resolve, reject) => {
      const abort = () => reject(abortError(signal, secrets));
      signal.addEventListener("abort", abort, { once: true });
    }),
  ]);
  throwIfAborted(signal, secrets);
}

function nonEmptyOr(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim() : fallback;
}

function nonNegativeFinite(value: number | undefined, fallback: number): number {
  return value !== undefined && Number.isFinite(value) && value >= 0 ? value : fallback;
}

function positiveFinite(value: number | undefined, fallback: number): number {
  return value !== undefined && Number.isFinite(value) && value > 0 ? value : fallback;
}

function defaultSleep(delayMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, delayMs);
    if (signal) {
      signal.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(abortError(signal));
        },
        { once: true },
      );
    }
  });
}

function mediaFamily(mediaType: string): "image" | "audio" | "application" {
  if (mediaType.startsWith("image/")) return "image";
  if (mediaType.startsWith("audio/")) return "audio";
  return "application";
}

async function pathExists(fs: AtomicFileSystem, path: string): Promise<boolean> {
  try {
    await fs.access(path);
    return true;
  } catch {
    return false;
  }
}

async function safeRemove(fs: AtomicFileSystem, path: string): Promise<void> {
  try {
    await fs.rm(path);
  } catch {
    // Best-effort cleanup; rollback failures are surfaced separately.
  }
}

async function safeRemoveRightsFile(fs: ArtifactRightsFileSystem, path: string): Promise<void> {
  try {
    await fs.rm(path);
  } catch {
    // Best-effort cleanup; the original sidecar remains authoritative.
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
