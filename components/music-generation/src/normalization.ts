import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { readFile, rm, writeFile } from "node:fs/promises";
import { basename, dirname, extname, join, resolve } from "node:path";
import {
  DEFAULT_TOOL_IDENTITY,
  isPortableArtifactReference,
  isTemporaryArtifactReference,
  isRecord,
  parseArtifactRights,
  redactSecrets,
  sha256Hex,
  writeArtifactWithProvenance,
  type ArtifactRights,
  type InputProvenance,
  type JsonObject,
  type SoftwareIdentity,
} from "@stage-gen/core";

export const DEFAULT_TARGET_INTEGRATED_LUFS = -16;
export const DEFAULT_TARGET_TRUE_PEAK_DBTP = -1.5;
export const DEFAULT_MAX_TRUE_PEAK_DBTP = -1.0;
export const DEFAULT_TARGET_LRA = 11;
export const DEFAULT_AUDIO_PROCESS_TIMEOUT_MS = 120_000;
export const MUSIC_NORMALIZATION_COMPONENT = {
  name: "@stage-gen/music-generation",
  version: "0.0.0",
} as const;

export type NormalizedAudioFormat = "mp3" | "wav";

export interface ProcessCommandOptions {
  signal?: AbortSignal;
  timeoutMs: number;
}

export interface ProcessCommandResult {
  stdout: string;
  stderr: string;
}

export type AudioProcessRunner = (
  command: string,
  args: readonly string[],
  options: ProcessCommandOptions,
) => Promise<ProcessCommandResult>;

export interface FfmpegAudioNormalizerConfig {
  ffmpegPath?: string;
  ffprobePath?: string;
  run?: AudioProcessRunner;
  now?: () => Date;
  tool?: SoftwareIdentity;
  timeoutMs?: number;
}

export interface AudioNormalizationRequest {
  sourcePath: string;
  sourceProvenancePath: string;
  /** Stable lineage id. Defaults to `sha256:<source content digest>`. */
  sourceRef?: string;
  artifactPath: string;
  outputFormat?: NormalizedAudioFormat;
  targetIntegratedLufs?: number;
  targetTruePeakDbtp?: number;
  maxTruePeakDbtp?: number;
  targetLra?: number;
  silenceFloorLufs?: number;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface AudioNormalizationResult {
  artifactPath: string;
  provenancePath: string;
  bytes: Uint8Array;
  mediaType: string;
  sourceSha256: string;
  outputSha256: string;
  durationSeconds: number;
  integratedLufs: number;
  truePeakDbtp: number;
  ffmpegVersion: string;
}

interface LoudnormMeasurement {
  integratedLufs: number;
  truePeakDbtp: number;
  lra: number;
  threshold: number;
  targetOffset: number;
}

interface SourceProvenance {
  provider: string;
  model: string;
  seed: number | null;
  prompt: string;
  references: string[];
  params: Record<string, unknown>;
  validation: Record<string, unknown>;
  response?: Record<string, unknown>;
  inputs: InputProvenance[];
  component?: SoftwareIdentity;
  tool?: SoftwareIdentity;
  ts?: string;
  attempts: number;
  artifact: {
    sha256: string;
    bytes: number;
    media_type: string;
  };
  rights?: ArtifactRights;
}

export interface FfmpegAudioNormalizer {
  normalize(request: AudioNormalizationRequest): Promise<AudioNormalizationResult>;
}

export function createFfmpegAudioNormalizer(
  config: FfmpegAudioNormalizerConfig = {},
): FfmpegAudioNormalizer {
  const ffmpegPath = nonEmpty(config.ffmpegPath, "ffmpeg");
  const ffprobePath = nonEmpty(config.ffprobePath, "ffprobe");
  const run = config.run ?? runProcessCommand;
  const defaultTimeoutMs = positiveFinite(
    config.timeoutMs,
    DEFAULT_AUDIO_PROCESS_TIMEOUT_MS,
  );

  return {
    async normalize(request): Promise<AudioNormalizationResult> {
      validateNormalizationRequest(request);
      const sourcePath = resolve(request.sourcePath);
      const artifactPath = resolve(request.artifactPath);
      const sourceProvenancePath = resolve(request.sourceProvenancePath);
      if (sourcePath === artifactPath) {
        throw new Error("audio normalization source and artifact paths must differ");
      }

      const outputFormat = request.outputFormat ?? inferFormat(artifactPath);
      const targetIntegratedLufs = finiteOr(
        request.targetIntegratedLufs,
        DEFAULT_TARGET_INTEGRATED_LUFS,
      );
      const targetTruePeakDbtp = finiteOr(
        request.targetTruePeakDbtp,
        DEFAULT_TARGET_TRUE_PEAK_DBTP,
      );
      const maxTruePeakDbtp = finiteOr(
        request.maxTruePeakDbtp,
        DEFAULT_MAX_TRUE_PEAK_DBTP,
      );
      const targetLra = positiveFinite(request.targetLra, DEFAULT_TARGET_LRA);
      const silenceFloorLufs = finiteOr(request.silenceFloorLufs, -70);
      const timeoutMs = positiveFinite(request.timeoutMs, defaultTimeoutMs);
      if (targetTruePeakDbtp > maxTruePeakDbtp) {
        throw new Error("targetTruePeakDbtp must not exceed maxTruePeakDbtp");
      }

      const sourceBytes = new Uint8Array(await readFile(sourcePath));
      if (sourceBytes.length === 0) throw new Error("audio normalization source is empty");
      const source = parseSourceProvenance(
        JSON.parse(await readFile(sourceProvenancePath, "utf8")),
      );
      const sourceSha256 = sha256Hex(sourceBytes);
      if (source.artifact.sha256 !== sourceSha256 || source.artifact.bytes !== sourceBytes.length) {
        throw new Error("audio normalization source does not match its provenance digest");
      }
      const sourceRef = request.sourceRef?.trim() || `sha256:${sourceSha256}`;
      if (isTemporaryArtifactReference(sourceRef)) {
        throw new Error("audio normalization sourceRef must not identify a temporary path");
      }
      const references = source.references.map((reference) =>
        isTemporaryArtifactReference(reference)
          ? `sha256:${sha256Hex(reference)}`
          : reference
      );
      const inputs = source.inputs.map((input) => ({
        ...input,
        ref: isTemporaryArtifactReference(input.ref)
          ? `sha256:${input.sha256}`
          : input.ref,
      }));
      if (source.rights?.status === "redistribution-approved") {
        for (const reference of [...references, ...inputs.map((input) => input.ref), sourceRef]) {
          if (!isPortableArtifactReference(reference)) {
            throw new Error(
              "redistribution-approved audio provenance contains an unsafe reference",
            );
          }
        }
      }
      const ffmpegVersionResult = await run(
        ffmpegPath,
        ["-version"],
        { signal: request.signal, timeoutMs },
      );
      const ffmpegVersion = firstNonEmptyLine(ffmpegVersionResult.stdout);
      if (!ffmpegVersion.toLowerCase().startsWith("ffmpeg version")) {
        throw new Error("ffmpeg version output was not recognized");
      }

      const sourceMeasurement = await measureLoudness({
        run,
        ffmpegPath,
        path: sourcePath,
        targetIntegratedLufs,
        targetTruePeakDbtp,
        targetLra,
        signal: request.signal,
        timeoutMs,
      });
      const token = randomUUID();
      const normalizedTemp = join(
        dirname(artifactPath),
        `.${basename(artifactPath)}.${token}.normalized.${outputFormat}`,
      );
      const filter = loudnormFilter({
        targetIntegratedLufs,
        targetTruePeakDbtp,
        targetLra,
        measured: sourceMeasurement,
      });

      try {
        const normalizeArgs = [
          "-hide_banner",
          "-nostdin",
          "-y",
          "-i",
          sourcePath,
          "-map_metadata",
          "-1",
          "-vn",
          "-af",
          filter,
          "-fflags",
          "+bitexact",
          "-flags:a",
          "+bitexact",
          ...codecArgs(outputFormat),
          normalizedTemp,
        ];
        await run(ffmpegPath, normalizeArgs, { signal: request.signal, timeoutMs });

        const finalMeasurement = await measureLoudness({
          run,
          ffmpegPath,
          path: normalizedTemp,
          targetIntegratedLufs,
          targetTruePeakDbtp,
          targetLra,
          signal: request.signal,
          timeoutMs,
        });
        if (finalMeasurement.truePeakDbtp > maxTruePeakDbtp + 0.01) {
          throw new Error(
            `normalized audio true peak ${finalMeasurement.truePeakDbtp.toFixed(2)} dBTP exceeds ${maxTruePeakDbtp.toFixed(2)} dBTP`,
          );
        }
        if (
          finalMeasurement.integratedLufs <= silenceFloorLufs ||
          finalMeasurement.truePeakDbtp <= silenceFloorLufs
        ) {
          throw new Error("normalized audio is silent or below the validation floor");
        }

        const probe = await probeAudio({
          run,
          ffprobePath,
          path: normalizedTemp,
          signal: request.signal,
          timeoutMs,
        });
        const outputBytes = new Uint8Array(await readFile(normalizedTemp));
        const mediaType = outputFormat === "mp3" ? "audio/mpeg" : "audio/wav";
        assertAudioSignature(outputBytes, mediaType);
        const outputSha256 = sha256Hex(outputBytes);
        const postprocessParams = {
          processor: "ffmpeg",
          version: ffmpegVersion,
          filter: "loudnorm",
          filter_params: {
            integrated_lufs: targetIntegratedLufs,
            true_peak_dbtp: targetTruePeakDbtp,
            lra: targetLra,
            linear: true,
          },
          measured_source: measurementFacts(sourceMeasurement),
          codec: outputFormat === "mp3" ? "libmp3lame" : "pcm_s16le",
          output_format: outputFormat,
        };
        const provenancePath = await writeArtifactWithProvenance(
          artifactPath,
          { bytes: outputBytes, mediaType },
          {
            provider: source.provider,
            model: source.model,
            seed: source.seed,
            prompt: source.prompt,
            refs: references,
            inputs: [
              ...inputs,
              {
                ref: sourceRef,
                sha256: sourceSha256,
                source: "content",
                bytes: sourceBytes.length,
                media_type: sourceMediaType(sourcePath),
              },
            ],
            params: {
              generation: source.params,
              generation_timestamp: source.ts ?? null,
              references,
              postprocess: postprocessParams,
            },
            validation: {
              generation: source.validation,
              postprocess: {
                non_silent: true,
                integrated_lufs: finalMeasurement.integratedLufs,
                true_peak_dbtp: finalMeasurement.truePeakDbtp,
                max_true_peak_dbtp: maxTruePeakDbtp,
                duration_seconds: probe.durationSeconds,
                format_name: probe.formatName,
                bit_rate: probe.bitRate,
                signature: "matched",
              },
            },
            component: MUSIC_NORMALIZATION_COMPONENT,
            tool: source.tool ?? config.tool ?? DEFAULT_TOOL_IDENTITY,
            timestamp: config.now?.().toISOString(),
            attempts: source.attempts,
            response: {
              generation: source.response ?? {},
              postprocess: {
                source_sha256: sourceSha256,
                output_sha256: outputSha256,
                source_bytes: sourceBytes.length,
                output_bytes: outputBytes.length,
                ffmpeg_version: ffmpegVersion,
              },
            },
            ...(source.rights ? { rights: source.rights } : {}),
          },
        );

        return {
          artifactPath,
          provenancePath,
          bytes: outputBytes,
          mediaType,
          sourceSha256,
          outputSha256,
          durationSeconds: probe.durationSeconds,
          integratedLufs: finalMeasurement.integratedLufs,
          truePeakDbtp: finalMeasurement.truePeakDbtp,
          ffmpegVersion,
        };
      } finally {
        await rm(normalizedTemp, { force: true });
      }
    },
  };
}

export async function runProcessCommand(
  command: string,
  args: readonly string[],
  options: ProcessCommandOptions,
): Promise<ProcessCommandResult> {
  if (options.signal?.aborted) throw abortError(options.signal);
  const timeoutMs = positiveFinite(options.timeoutMs, DEFAULT_AUDIO_PROCESS_TIMEOUT_MS);
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, [...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let totalBytes = 0;
    let settled = false;
    let timedOut = false;
    const maxOutputBytes = 4 * 1024 * 1024;

    const finishReject = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      rejectPromise(error);
    };
    const finishResolve = (result: ProcessCommandResult) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolvePromise(result);
    };
    const collect = (target: Buffer[], chunk: Buffer) => {
      totalBytes += chunk.length;
      if (totalBytes > maxOutputBytes) {
        child.kill("SIGKILL");
        finishReject(new Error(`${command} diagnostic output exceeded 4 MiB`));
        return;
      }
      target.push(chunk);
    };
    child.stdout.on("data", (chunk: Buffer) => collect(stdout, chunk));
    child.stderr.on("data", (chunk: Buffer) => collect(stderr, chunk));
    child.on("error", (error) => finishReject(new Error(redactSecrets(error.message))));
    child.on("close", (code, signal) => {
      const result = {
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      };
      if (timedOut) {
        finishReject(new Error(`${command} timed out after ${timeoutMs}ms`));
      } else if (options.signal?.aborted) {
        finishReject(abortError(options.signal));
      } else if (code !== 0) {
        const diagnostic = redactSecrets(result.stderr.trim()).slice(-800);
        finishReject(
          new Error(
            `${command} exited with ${code ?? `signal ${signal ?? "unknown"}`}${diagnostic ? `: ${diagnostic}` : ""}`,
          ),
        );
      } else {
        finishResolve(result);
      }
    });

    const onAbort = () => child.kill("SIGKILL");
    options.signal?.addEventListener("abort", onAbort, { once: true });
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);
    function cleanup() {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onAbort);
    }
  });
}

async function measureLoudness(args: {
  run: AudioProcessRunner;
  ffmpegPath: string;
  path: string;
  targetIntegratedLufs: number;
  targetTruePeakDbtp: number;
  targetLra: number;
  signal?: AbortSignal;
  timeoutMs: number;
}): Promise<LoudnormMeasurement> {
  const filter = `loudnorm=I=${formatNumber(args.targetIntegratedLufs)}:TP=${formatNumber(args.targetTruePeakDbtp)}:LRA=${formatNumber(args.targetLra)}:print_format=json`;
  const result = await args.run(
    args.ffmpegPath,
    ["-hide_banner", "-nostdin", "-i", args.path, "-af", filter, "-f", "null", "-"],
    { signal: args.signal, timeoutMs: args.timeoutMs },
  );
  return parseLoudnormJson(result.stderr);
}

async function probeAudio(args: {
  run: AudioProcessRunner;
  ffprobePath: string;
  path: string;
  signal?: AbortSignal;
  timeoutMs: number;
}): Promise<{ durationSeconds: number; formatName: string; bitRate: number | null }> {
  const result = await args.run(
    args.ffprobePath,
    [
      "-v",
      "error",
      "-show_entries",
      "format=format_name,duration,bit_rate",
      "-of",
      "json",
      args.path,
    ],
    { signal: args.signal, timeoutMs: args.timeoutMs },
  );
  let parsed: unknown;
  try {
    parsed = JSON.parse(result.stdout);
  } catch {
    throw new Error("ffprobe returned invalid JSON");
  }
  if (!isRecord(parsed) || !isRecord(parsed.format)) {
    throw new Error("ffprobe returned no format metadata");
  }
  const durationSeconds = numberFromUnknown(parsed.format.duration, "ffprobe duration");
  if (durationSeconds <= 0) throw new Error("ffprobe duration must be positive");
  const formatName = typeof parsed.format.format_name === "string"
    ? parsed.format.format_name
    : "unknown";
  const bitRate = parsed.format.bit_rate === undefined
    ? null
    : numberFromUnknown(parsed.format.bit_rate, "ffprobe bit rate");
  return { durationSeconds, formatName, bitRate };
}

function parseLoudnormJson(stderr: string): LoudnormMeasurement {
  const end = stderr.lastIndexOf("}");
  const start = stderr.lastIndexOf("{", end);
  if (start < 0 || end < start) throw new Error("ffmpeg loudnorm returned no measurement JSON");
  let parsed: unknown;
  try {
    parsed = JSON.parse(stderr.slice(start, end + 1));
  } catch {
    throw new Error("ffmpeg loudnorm returned invalid measurement JSON");
  }
  if (!isRecord(parsed)) throw new Error("ffmpeg loudnorm measurement is not an object");
  return {
    integratedLufs: numberFromUnknown(parsed.input_i, "loudnorm input_i"),
    truePeakDbtp: numberFromUnknown(parsed.input_tp, "loudnorm input_tp"),
    lra: numberFromUnknown(parsed.input_lra, "loudnorm input_lra"),
    threshold: numberFromUnknown(parsed.input_thresh, "loudnorm input_thresh"),
    targetOffset: numberFromUnknown(parsed.target_offset, "loudnorm target_offset"),
  };
}

function loudnormFilter(args: {
  targetIntegratedLufs: number;
  targetTruePeakDbtp: number;
  targetLra: number;
  measured: LoudnormMeasurement;
}): string {
  return [
    `loudnorm=I=${formatNumber(args.targetIntegratedLufs)}`,
    `TP=${formatNumber(args.targetTruePeakDbtp)}`,
    `LRA=${formatNumber(args.targetLra)}`,
    `measured_I=${formatNumber(args.measured.integratedLufs)}`,
    `measured_TP=${formatNumber(args.measured.truePeakDbtp)}`,
    `measured_LRA=${formatNumber(args.measured.lra)}`,
    `measured_thresh=${formatNumber(args.measured.threshold)}`,
    `offset=${formatNumber(args.measured.targetOffset)}`,
    "linear=true",
    "print_format=summary",
  ].join(":");
}

function codecArgs(format: NormalizedAudioFormat): string[] {
  if (format === "mp3") {
    return [
      "-codec:a",
      "libmp3lame",
      "-b:a",
      "192k",
      "-ar",
      "44100",
      "-ac",
      "2",
      "-id3v2_version",
      "3",
    ];
  }
  return ["-codec:a", "pcm_s16le", "-ar", "44100", "-ac", "2"];
}

function parseSourceProvenance(value: unknown): SourceProvenance {
  if (!isRecord(value)) throw new Error("source provenance must be an object");
  if (typeof value.provider !== "string" || value.provider.length === 0) {
    throw new Error("source provenance provider is missing");
  }
  if (typeof value.model !== "string" || value.model.length === 0) {
    throw new Error("source provenance model is missing");
  }
  if (typeof value.prompt !== "string" || value.prompt.length === 0) {
    throw new Error("source provenance prompt is missing");
  }
  if (!Number.isInteger(value.attempts) || (value.attempts as number) < 1) {
    throw new Error("source provenance attempts is invalid");
  }
  const seed = typeof value.seed === "number" && Number.isInteger(value.seed)
    ? value.seed
    : null;
  const referenceValue = Array.isArray(value.references)
    ? value.references
    : Array.isArray(value.refs)
      ? value.refs
      : [];
  const references = referenceValue.filter((entry): entry is string => typeof entry === "string");
  const inputs = Array.isArray(value.inputs)
    ? value.inputs.filter(isInputProvenance)
    : [];
  if (!isRecord(value.artifact)) {
    throw new Error("source provenance artifact digest is missing");
  }
  const artifactSha256 = value.artifact.sha256;
  const artifactBytes = value.artifact.bytes;
  const artifactMediaType = value.artifact.media_type;
  if (typeof artifactSha256 !== "string" || !/^[a-f0-9]{64}$/.test(artifactSha256)) {
    throw new Error("source provenance artifact SHA-256 is invalid");
  }
  if (!Number.isInteger(artifactBytes) || (artifactBytes as number) < 0) {
    throw new Error("source provenance artifact byte count is invalid");
  }
  if (typeof artifactMediaType !== "string" || !artifactMediaType.startsWith("audio/")) {
    throw new Error("source provenance artifact media type is invalid");
  }
  const rights = value.rights === undefined ? undefined : parseArtifactRights(value.rights);
  return {
    provider: value.provider,
    model: value.model,
    seed,
    prompt: value.prompt,
    references,
    params: isRecord(value.params) ? value.params : {},
    validation: isRecord(value.validation) ? value.validation : {},
    ...(isRecord(value.response) ? { response: value.response } : {}),
    inputs,
    ...(isSoftwareIdentity(value.component) ? { component: value.component } : {}),
    ...(isSoftwareIdentity(value.tool) ? { tool: value.tool } : {}),
    ...(typeof value.ts === "string" ? { ts: value.ts } : {}),
    attempts: value.attempts as number,
    artifact: {
      sha256: artifactSha256,
      bytes: artifactBytes as number,
      media_type: artifactMediaType,
    },
    ...(rights ? { rights } : {}),
  };
}

function isInputProvenance(value: unknown): value is InputProvenance {
  return isRecord(value) &&
    typeof value.ref === "string" &&
    typeof value.sha256 === "string" &&
    /^[a-f0-9]{64}$/.test(value.sha256) &&
    (value.source === "content" || value.source === "reference");
}

function isSoftwareIdentity(value: unknown): value is SoftwareIdentity {
  return isRecord(value) &&
    typeof value.name === "string" && value.name.length > 0 &&
    typeof value.version === "string" && value.version.length > 0;
}

function measurementFacts(value: LoudnormMeasurement): JsonObject {
  return {
    integrated_lufs: value.integratedLufs,
    true_peak_dbtp: value.truePeakDbtp,
    lra: value.lra,
    threshold: value.threshold,
    target_offset: value.targetOffset,
  };
}

function validateNormalizationRequest(request: AudioNormalizationRequest): void {
  for (const [label, value] of [
    ["sourcePath", request.sourcePath],
    ["sourceProvenancePath", request.sourceProvenancePath],
    ["artifactPath", request.artifactPath],
  ] as const) {
    if (typeof value !== "string" || value.trim().length === 0) {
      throw new Error(`${label} must be a non-empty string`);
    }
  }
  if (request.outputFormat && !["mp3", "wav"].includes(request.outputFormat)) {
    throw new Error("outputFormat must be mp3 or wav");
  }
  if (
    request.sourceRef !== undefined &&
    (typeof request.sourceRef !== "string" || request.sourceRef.trim().length === 0)
  ) {
    throw new Error("sourceRef must be a non-empty string when provided");
  }
}

function inferFormat(path: string): NormalizedAudioFormat {
  const extension = extname(path).toLowerCase();
  if (extension === ".mp3") return "mp3";
  if (extension === ".wav") return "wav";
  throw new Error("normalized audio artifact must use .mp3 or .wav");
}

function sourceMediaType(path: string): string {
  const extension = extname(path).toLowerCase();
  if (extension === ".wav") return "audio/wav";
  return "audio/mpeg";
}

function assertAudioSignature(bytes: Uint8Array, mediaType: string): void {
  const mp3 = mediaType === "audio/mpeg" &&
    ((bytes.length >= 3 && String.fromCharCode(...bytes.slice(0, 3)) === "ID3") ||
      (bytes.length >= 2 && bytes[0] === 0xff && (bytes[1] & 0xe0) === 0xe0));
  const wav = mediaType === "audio/wav" && bytes.length >= 12 &&
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WAVE";
  if (!mp3 && !wav) throw new Error("normalized audio signature does not match its format");
}

function numberFromUnknown(value: unknown, label: string): number {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) throw new Error(`${label} must be finite`);
  return number;
}

function formatNumber(value: number): string {
  if (!Number.isFinite(value)) throw new Error("audio filter parameter must be finite");
  return Number(value.toFixed(4)).toString();
}

function firstNonEmptyLine(value: string): string {
  const line = value.split(/\r?\n/).find((entry) => entry.trim().length > 0);
  if (!line) throw new Error("ffmpeg version output was empty");
  return line.trim();
}

function abortError(signal: AbortSignal): Error {
  const reason = signal.reason;
  const message = reason instanceof Error ? reason.message : typeof reason === "string" ? reason : "cancelled";
  const error = new Error(redactSecrets(`audio process cancelled: ${message}`));
  error.name = "AbortError";
  return error;
}

function finiteOr(value: number | undefined, fallback: number): number {
  return value !== undefined && Number.isFinite(value) ? value : fallback;
}

function positiveFinite(value: number | undefined, fallback: number): number {
  return value !== undefined && Number.isFinite(value) && value > 0 ? value : fallback;
}

function nonEmpty(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim() : fallback;
}
