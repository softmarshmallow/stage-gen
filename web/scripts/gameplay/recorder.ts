import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";
import { GAMEPLAY_AUTOMATION_VERSION, type GameplayFixture } from "../../tests/gameplay/contracts";
import {
  GAMEPLAY_DEMO_ROOT,
  GAMEPLAY_MODEL_TAG,
  generateApprovedModelGameplayFixture,
} from "../../tests/gameplay/model-assets";
import {
  GAMEPLAY_NEXT_CLI_PATH,
  assertCaptureDirectoryIdentity,
  bindCaptureDirectoryIdentity,
  installCaptureFiles,
  runTool,
  validateFastStartMp4,
  validateGameplayRun,
  withGameplaySession,
  type CaptureDirectoryIdentity,
  type CaptureInstallOperations,
  type GameplaySessionEvidence,
} from "../../tests/gameplay/harness";
import {
  GAMEPLAY_FPS,
  GAMEPLAY_POSTER_FRAME,
  GAMEPLAY_SELECTED_FRAMES,
  GAMEPLAY_STEP_MS,
  GAMEPLAY_TIMELINE,
  type GameplayFrame,
  type GameplayKey,
  type KeyboardAction,
} from "../../tests/gameplay/timeline";
import {
  assertCanonicalSnapshotsEqual,
  assertDependencyIdentityEqual,
  linkRecorderDependencies,
  pruneNonRuntimeNextArtifacts,
  snapshotGameplayBuildInputs,
  snapshotServedNextBuild,
  validateRecorderDependencies,
  type CanonicalTreeSnapshot,
  type RecorderDependencyIdentity,
  type ServedNextBuildSnapshot,
} from "./build-binding";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIR, "../..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const REPORT_ROOT_RELATIVE = "output/playwright";
const REPORT_ROOT = path.join(REPO_ROOT, "output", "playwright");
const MAX_CAPTURE_SECONDS = 30;
const MAX_OUTPUT_FPS = 60;
const MAX_OUTPUT_WIDTH = 1_920;
const MAX_OUTPUT_HEIGHT = 1_080;
const MAX_VIDEO_BYTES = 25 * 1024 * 1024;
const MAX_POSTER_BYTES = 5 * 1024 * 1024;
const MAX_TIMELINE_BYTES = 1_000_000;
const MAX_FIXTURE_FILES = 512;
const MAX_FIXTURE_BYTES = 100 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 600_000;
const MAX_TIMEOUT_MS = 900_000;
const TOOL_VERSION_TIMEOUT_MS = 10_000;
const FFMPEG_TIMEOUT_MS = 300_000;
const FFPROBE_TIMEOUT_MS = 30_000;
const NEXT_BUILD_TIMEOUT_MS = 300_000;
const SAFE_TAG = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
const SAFE_FIXTURE_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/;
const SAFE_KEYS = new Set<GameplayKey>([
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Shift",
  "Space",
  "j",
  "s",
  "i",
]);
export const GAMEPLAY_RECORDER_BUILD_ARGV = Object.freeze([
  "node_modules/next/dist/bin/next",
  "build",
  ".",
]);
export const GAMEPLAY_RECORDING_SCHEMA_VERSION = 2 as const;
export const DEFAULT_RECORDING_OPTIONS = Object.freeze({
  mode: "record" as const,
  output: `${REPORT_ROOT_RELATIVE}/gameplay-report.mp4`,
  durationSeconds: 30,
  fps: 30,
  width: 1_280,
  height: 720,
  posterFrame: GAMEPLAY_POSTER_FRAME,
  verifyTwice: true,
  timeoutMs: DEFAULT_TIMEOUT_MS,
  source: Object.freeze({ kind: "model-demo" as const }),
});

export type GameplayRecorderSource =
  | Readonly<{ kind: "model-demo" }>
  | Readonly<{
      kind: "fixture";
      fixture: string;
      tag: string;
      timeline: string;
    }>;

export type GameplayRecorderOptions = Readonly<{
  mode: "record" | "dry-run";
  output: string;
  durationSeconds: number;
  fps: number;
  width: number;
  height: number;
  posterFrame: number;
  verifyTwice: boolean;
  timeoutMs: number;
  source: GameplayRecorderSource;
}>;

export type GameplayReportPaths = Readonly<{
  relativeVideo: string;
  relativePoster: string;
  relativeMetadata: string;
  video: string;
  poster: string;
  metadata: string;
}>;

export type RecordingProbeExpectation = Readonly<{
  width: number;
  height: number;
  fps: number;
  durationSeconds: number;
  frameCount: number;
  maxBytes?: number;
}>;

export type RecordingMp4Probe = Readonly<{
  container: "mp4";
  video_codec: "h264";
  pixel_format: "yuv420p";
  width: number;
  height: number;
  frame_rate: number;
  real_frame_rate: number;
  frame_count: number;
  duration_seconds: number;
  size_bytes: number;
  audio_codec: null;
}>;

export type RecorderMediaCommands = Readonly<{
  video: readonly string[];
  poster: readonly string[];
  probe: readonly string[];
}>;

export function recorderMediaCommands(
  options: Pick<
    GameplayRecorderOptions,
    "durationSeconds" | "fps" | "width" | "height" | "posterFrame"
  >,
): RecorderMediaCommands {
  const encodedFrameCount = options.durationSeconds * options.fps;
  const videoFilter = `scale=${options.width}:${options.height}:flags=lanczos,fps=${options.fps}`;
  return Object.freeze({
    video: Object.freeze([
      "-nostdin",
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-framerate",
      String(GAMEPLAY_FPS),
      "-start_number",
      "1",
      "-i",
      "frames/frame-%04d.png",
      "-vf",
      videoFilter,
      "-frames:v",
      String(encodedFrameCount),
      "-an",
      "-c:v",
      "libx264",
      "-preset",
      "slow",
      "-crf",
      "26",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      "recording.mp4",
    ]),
    poster: Object.freeze([
      "-nostdin",
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-i",
      `frames/frame-${String(options.posterFrame).padStart(4, "0")}.png`,
      "-vf",
      `scale=${options.width}:${options.height}:flags=lanczos`,
      "-frames:v",
      "1",
      "recording.poster.png",
    ]),
    probe: Object.freeze([
      "-v",
      "error",
      "-count_frames",
      "-show_entries",
      "format=format_name,duration,size:stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,r_frame_rate,duration,nb_frames,nb_read_frames",
      "-of",
      "json",
      "recording.mp4",
    ]),
  });
}

export function groupGameplayEventFrames(
  events: readonly Readonly<{ kind: string; frame: number }>[],
): Readonly<Record<string, readonly number[]>> {
  const grouped: Record<string, number[]> = {};
  for (const event of events) {
    (grouped[event.kind] ??= []).push(event.frame);
  }
  return Object.freeze(
    Object.fromEntries(
      Object.entries(grouped).map(([kind, frames]) => [
        kind,
        Object.freeze([...frames]),
      ]),
    ),
  );
}

export type GameplayRecordingResult = Readonly<{
  version: typeof GAMEPLAY_AUTOMATION_VERSION;
  verdict: "unreviewed";
  video: Readonly<{
    path: string;
    sha256: string;
    bytes: number;
    durationSeconds: number;
  }>;
  poster: Readonly<{ path: string; sha256: string; bytes: number }>;
  metadata: Readonly<{ path: string; sha256: string; bytes: number }>;
  deterministic: Readonly<{
    simulationFrames: number;
    duplicateVerified: boolean;
    transcriptSha256: string;
  }>;
}>;

type SourceReference = Readonly<{
  path: string;
  sha256: string;
  bytes: number;
}>;

type FixtureSnapshot = Readonly<{
  digest: string;
  files: readonly Readonly<{ name: string; sha256: string; bytes: number }>[];
}>;

type FixtureTreeFile = Readonly<{
  name: string;
  sha256: string;
  bytes: number;
  contents: Buffer;
}>;

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function throwIfCancelled(signal: AbortSignal, label: string): void {
  if (signal.aborted) throw new Error(`${label} was cancelled`);
}

function canonicalRelativePath(value: string, label: string): string {
  if (
    !value ||
    value !== value.trim() ||
    value.length > 1_024 ||
    value.includes("\0") ||
    /[\u0000-\u001f\u007f]/.test(value) ||
    value.includes("\\") ||
    path.posix.isAbsolute(value) ||
    path.posix.normalize(value) !== value ||
    value.split("/").some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error(`${label} must be a canonical repository-relative path`);
  }
  return value;
}

function parseBoundedInteger(
  value: string | undefined,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (!value || !/^(?:0|[1-9]\d*)$/.test(value)) {
    throw new Error(`${label} must be an integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be between ${minimum} and ${maximum}`);
  }
  return parsed;
}

function requireValue(args: readonly string[], index: number, flag: string): string {
  const value = args[index + 1];
  if (value === undefined || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

export function resolveGameplayReportPaths(requested: string): GameplayReportPaths {
  const relativeVideo = canonicalRelativePath(requested, "recording output");
  if (
    !relativeVideo.startsWith(`${REPORT_ROOT_RELATIVE}/`) ||
    path.posix.extname(relativeVideo) !== ".mp4" ||
    path.posix.basename(relativeVideo) !== path.posix.basename(relativeVideo).trim() ||
    !relativeVideo
      .split("/")
      .slice(2)
      .every((part) => /^[a-z0-9][a-z0-9._-]{0,127}$/.test(part)) ||
    !/^[a-z0-9][a-z0-9._-]{0,123}\.mp4$/.test(
      path.posix.basename(relativeVideo),
    )
  ) {
    throw new Error(
      `recording output must be an MP4 below ${REPORT_ROOT_RELATIVE}/`,
    );
  }
  const stem = relativeVideo.slice(0, -4);
  const relativePoster = `${stem}.poster.png`;
  const relativeMetadata = `${stem}.recording.json`;
  const relativeTargets = [relativeVideo, relativePoster, relativeMetadata];
  if (
    new Set(relativeTargets.map((target) => target.normalize("NFC").toLocaleLowerCase("en-US"))).size !==
    relativeTargets.length
  ) {
    throw new Error("recording output sibling names must be unique");
  }
  const absolute = relativeTargets.map((target) =>
    path.join(REPO_ROOT, ...target.split("/")),
  );
  if (absolute.some((target) => !target.startsWith(`${REPORT_ROOT}${path.sep}`))) {
    throw new Error("recording output escapes the report root");
  }
  return Object.freeze({
    relativeVideo,
    relativePoster,
    relativeMetadata,
    video: absolute[0]!,
    poster: absolute[1]!,
    metadata: absolute[2]!,
  });
}

export function parseGameplayRecorderArgs(
  args: readonly string[],
): GameplayRecorderOptions {
  let mode: "record" | "dry-run" = DEFAULT_RECORDING_OPTIONS.mode;
  let output: string = DEFAULT_RECORDING_OPTIONS.output;
  let durationSeconds: number = DEFAULT_RECORDING_OPTIONS.durationSeconds;
  let fps: number = DEFAULT_RECORDING_OPTIONS.fps;
  let width: number = DEFAULT_RECORDING_OPTIONS.width;
  let height: number = DEFAULT_RECORDING_OPTIONS.height;
  let posterFrame: number = DEFAULT_RECORDING_OPTIONS.posterFrame;
  let verifyTwice: boolean = DEFAULT_RECORDING_OPTIONS.verifyTwice;
  let timeoutMs: number = DEFAULT_RECORDING_OPTIONS.timeoutMs;
  let explicitPreset: string | undefined;
  let fixture: string | undefined;
  let tag: string | undefined;
  let timeline: string | undefined;
  const seen = new Set<string>();

  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index]!;
    if (!flag.startsWith("--")) throw new Error(`unexpected argument: ${flag}`);
    if (seen.has(flag)) throw new Error(`duplicate option: ${flag}`);
    seen.add(flag);
    switch (flag) {
      case "--dry-run":
        mode = "dry-run";
        break;
      case "--no-verify-twice":
        verifyTwice = false;
        break;
      case "--output":
        output = requireValue(args, index, flag);
        index += 1;
        break;
      case "--duration":
        durationSeconds = parseBoundedInteger(
          requireValue(args, index, flag),
          "duration",
          1,
          MAX_CAPTURE_SECONDS,
        );
        index += 1;
        break;
      case "--fps":
        fps = parseBoundedInteger(
          requireValue(args, index, flag),
          "fps",
          1,
          MAX_OUTPUT_FPS,
        );
        index += 1;
        break;
      case "--width":
        width = parseBoundedInteger(
          requireValue(args, index, flag),
          "width",
          320,
          MAX_OUTPUT_WIDTH,
        );
        index += 1;
        break;
      case "--height":
        height = parseBoundedInteger(
          requireValue(args, index, flag),
          "height",
          180,
          MAX_OUTPUT_HEIGHT,
        );
        index += 1;
        break;
      case "--poster-frame":
        posterFrame = parseBoundedInteger(
          requireValue(args, index, flag),
          "poster frame",
          1,
          MAX_CAPTURE_SECONDS * GAMEPLAY_FPS,
        );
        index += 1;
        break;
      case "--timeout-ms":
        timeoutMs = parseBoundedInteger(
          requireValue(args, index, flag),
          "timeout",
          1_000,
          MAX_TIMEOUT_MS,
        );
        index += 1;
        break;
      case "--preset":
        explicitPreset = requireValue(args, index, flag);
        index += 1;
        break;
      case "--fixture":
        fixture = requireValue(args, index, flag);
        index += 1;
        break;
      case "--tag":
        tag = requireValue(args, index, flag);
        index += 1;
        break;
      case "--timeline":
        timeline = requireValue(args, index, flag);
        index += 1;
        break;
      default:
        throw new Error(`unknown gameplay recorder option: ${flag}`);
    }
  }

  resolveGameplayReportPaths(output);
  if (width % 2 !== 0 || height % 2 !== 0) {
    throw new Error("recording width and height must be even for yuv420p");
  }
  const simulationFrames = durationSeconds * GAMEPLAY_FPS;
  if (posterFrame > simulationFrames) {
    throw new Error("poster frame must fall within the simulation timeline");
  }
  const hasCustomSource = fixture !== undefined || tag !== undefined || timeline !== undefined;
  if (explicitPreset !== undefined && explicitPreset !== "model-demo") {
    throw new Error("preset must be model-demo");
  }
  if (explicitPreset !== undefined && hasCustomSource) {
    throw new Error("--preset cannot be combined with fixture source options");
  }
  let source: GameplayRecorderSource;
  if (hasCustomSource) {
    if (!fixture || !tag || !timeline) {
      throw new Error("custom recording requires --fixture, --tag, and --timeline");
    }
    const safeFixture = canonicalRelativePath(fixture, "fixture");
    const safeTimeline = canonicalRelativePath(timeline, "timeline");
    if (!safeFixture.startsWith("out/") || path.posix.basename(safeFixture) !== tag) {
      throw new Error("fixture must be out/<tag> and match --tag");
    }
    if (!SAFE_TAG.test(tag)) throw new Error("recording tag is invalid");
    if (path.posix.extname(safeTimeline).toLowerCase() !== ".json") {
      throw new Error("timeline must be a JSON file");
    }
    source = Object.freeze({
      kind: "fixture",
      fixture: safeFixture,
      tag,
      timeline: safeTimeline,
    });
  } else {
    source = Object.freeze({ kind: "model-demo" });
  }
  return Object.freeze({
    mode,
    output,
    durationSeconds,
    fps,
    width,
    height,
    posterFrame,
    verifyTwice,
    timeoutMs,
    source,
  });
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

export function validateRecorderTimeline(
  value: unknown,
  expectedFrames: number,
): readonly GameplayFrame[] {
  const root = record(value, "timeline");
  if (root.schemaVersion !== 1 || root.simulationFps !== GAMEPLAY_FPS) {
    throw new Error(`timeline must use schemaVersion 1 at ${GAMEPLAY_FPS} fps`);
  }
  if (!Array.isArray(root.frames) || root.frames.length !== expectedFrames) {
    throw new Error(`timeline must contain exactly ${expectedFrames} frames`);
  }
  const pressed = new Set<GameplayKey>();
  const frames = Object.freeze(
    root.frames.map((rawFrame, index) => {
      const frame = record(rawFrame, `timeline frame ${index}`);
      if (frame.index !== index || !Array.isArray(frame.actions)) {
        throw new Error("timeline indices must be contiguous from zero");
      }
      const actions = frame.actions.map((rawAction, actionIndex) => {
        const action = record(rawAction, `timeline frame ${index} action ${actionIndex}`);
        if (
          (action.type !== "down" && action.type !== "up") ||
          typeof action.key !== "string" ||
          !SAFE_KEYS.has(action.key as GameplayKey) ||
          Object.keys(action).some((key) => key !== "type" && key !== "key")
        ) {
          throw new Error(`timeline frame ${index} contains an invalid action`);
        }
        const key = action.key as GameplayKey;
        if (action.type === "down") {
          if (pressed.has(key)) {
            throw new Error(`timeline frame ${index} presses ${key} twice`);
          }
          pressed.add(key);
        } else {
          if (!pressed.has(key)) {
            throw new Error(
              `timeline frame ${index} releases ${key} before pressing it`,
            );
          }
          pressed.delete(key);
        }
        return Object.freeze({
          type: action.type,
          key,
        }) as KeyboardAction;
      });
      if (Object.keys(frame).some((key) => key !== "index" && key !== "actions")) {
        throw new Error(`timeline frame ${index} contains unknown fields`);
      }
      return Object.freeze({ index, actions: Object.freeze(actions) });
    }),
  );
  if (pressed.size > 0) {
    throw new Error(
      `timeline leaves keys pressed: ${[...pressed].sort().join(", ")}`,
    );
  }
  return frames;
}

function modelTimeline(frameCount: number): readonly GameplayFrame[] {
  return Object.freeze(
    Array.from({ length: frameCount }, (_, index) =>
      Object.freeze({
        index,
        actions: Object.freeze([...(GAMEPLAY_TIMELINE[index]?.actions ?? [])]),
      }),
    ),
  );
}

function canonicalFraction(
  value: unknown,
): Readonly<{ numerator: number; denominator: number; value: number }> {
  if (typeof value !== "string") throw new Error("ffprobe returned an invalid frame rate");
  const match = /^([1-9]\d*)\/([1-9]\d*)$/.exec(value);
  if (!match) throw new Error("ffprobe returned an invalid frame rate");
  const numerator = Number(match[1]);
  const denominator = Number(match[2]);
  if (!Number.isSafeInteger(numerator) || !Number.isSafeInteger(denominator)) {
    throw new Error("ffprobe returned an invalid frame rate");
  }
  return Object.freeze({
    numerator,
    denominator,
    value: numerator / denominator,
  });
}

function canonicalNumber(value: unknown, label: string): number {
  if (typeof value !== "string" || !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) {
    throw new Error(`ffprobe returned an invalid ${label}`);
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`ffprobe returned an invalid ${label}`);
  return parsed;
}

function canonicalPositiveInteger(value: unknown, label: string): number {
  if (typeof value !== "string" || !/^[1-9]\d*$/.test(value)) {
    throw new Error(`ffprobe returned an invalid ${label}`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) {
    throw new Error(`ffprobe returned an invalid ${label}`);
  }
  return parsed;
}

function isExactIntegerRate(
  fraction: Readonly<{ numerator: number; denominator: number }>,
  expected: number,
): boolean {
  return (
    fraction.denominator <= Number.MAX_SAFE_INTEGER / expected &&
    fraction.numerator === expected * fraction.denominator
  );
}

export function validateRecordingMp4Probe(
  value: unknown,
  expected: RecordingProbeExpectation,
): RecordingMp4Probe {
  const root = record(value, "ffprobe result");
  const format = record(root.format, "ffprobe format");
  if (!Array.isArray(root.streams) || root.streams.length !== 1) {
    throw new Error("capture must contain exactly one video stream and no others");
  }
  const video = record(root.streams[0], "ffprobe video stream");
  const duration = canonicalNumber(format.duration, "duration");
  const size = canonicalPositiveInteger(format.size, "size");
  const averageFrameRate = canonicalFraction(video.avg_frame_rate);
  const realFrameRate = canonicalFraction(video.r_frame_rate);
  const frameCount = canonicalPositiveInteger(video.nb_frames, "frame count");
  const countedFrames = canonicalPositiveInteger(
    video.nb_read_frames,
    "counted frame count",
  );
  const streamDuration = canonicalNumber(video.duration, "stream duration");
  if (typeof format.format_name !== "string" || !format.format_name.split(",").includes("mp4")) {
    throw new Error("capture container is not MP4");
  }
  if (
    video.codec_type !== "video" ||
    video.codec_name !== "h264" ||
    video.pix_fmt !== "yuv420p"
  ) {
    throw new Error("capture must use one H.264 yuv420p video stream");
  }
  if (
    video.width !== expected.width ||
    video.height !== expected.height ||
    !isExactIntegerRate(averageFrameRate, expected.fps) ||
    !isExactIntegerRate(realFrameRate, expected.fps)
  ) {
    throw new Error(
      `capture must be exactly ${expected.width}x${expected.height} at ${expected.fps} fps`,
    );
  }
  if (
    !Number.isSafeInteger(frameCount) ||
    frameCount !== expected.frameCount ||
    countedFrames !== expected.frameCount
  ) {
    throw new Error(`capture must contain exactly ${expected.frameCount} frames`);
  }
  if (
    duration !== expected.durationSeconds ||
    streamDuration !== expected.durationSeconds
  ) {
    throw new Error(`capture duration must be ${expected.durationSeconds} seconds`);
  }
  const maxBytes = expected.maxBytes ?? MAX_VIDEO_BYTES;
  if (!Number.isSafeInteger(size) || size <= 0 || size > maxBytes) {
    throw new Error(`capture must be nonempty and no larger than ${maxBytes} bytes`);
  }
  return Object.freeze({
    container: "mp4",
    video_codec: "h264",
    pixel_format: "yuv420p",
    width: expected.width,
    height: expected.height,
    frame_rate: expected.fps,
    real_frame_rate: expected.fps,
    frame_count: frameCount,
    duration_seconds: duration,
    size_bytes: size,
    audio_codec: null,
  });
}

export function sanitizeRecorderDiagnostic(value: string): string {
  let sanitized = value.replace(
    /\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD))\s*[:=]\s*[^\s]+/gi,
    "$1=<redacted>",
  );
  for (const root of [REPO_ROOT, WEB_ROOT, process.env.HOME].filter(
    (candidate): candidate is string => Boolean(candidate),
  )) {
    sanitized = sanitized.split(root).join("<path>");
  }
  sanitized = sanitized
    .replace(
      /\bAuthorization\s*:\s*Bearer\s+[^\s]+/gi,
      "Authorization: Bearer <redacted>",
    )
    .replace(/\bBearer\s+[^\s]+/gi, "Bearer <redacted>")
    .replace(/(?:[A-Za-z]:\\|\/)(?:[^\s'"`]+[\\/])*[^\s'"`]*/g, "<path>")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "?")
    .trim();
  return sanitized.length <= 4_096 ? sanitized : `…${sanitized.slice(-4_095)}`;
}

export function assertPortableRecordingMetadata(value: unknown): void {
  const rendered = JSON.stringify(value);
  if (
    !rendered ||
    /(?:file:|data:|\/Users\/|\/private\/tmp\/|\/var\/folders\/)/i.test(rendered) ||
    /(?:[A-Za-z]:\\\\|\bAuthorization\s*:\s*Bearer\b)/i.test(rendered) ||
    /\b(?:OPENROUTER_API_KEY|FAL_KEY|[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD))\b/.test(rendered)
  ) {
    throw new Error("recording metadata contains a non-portable or sensitive value");
  }
}

export async function readBoundedRecorderInput(
  root: string,
  repositoryPath: string,
  maximumBytes: number,
): Promise<Buffer> {
  if (!path.isAbsolute(root) || !Number.isSafeInteger(maximumBytes) || maximumBytes <= 0) {
    throw new Error("recorder input root and byte limit must be bounded");
  }
  const trustedRoot = await fs.realpath(root);
  const canonical = canonicalRelativePath(repositoryPath, "source path");
  const target = path.join(trustedRoot, ...canonical.split("/"));
  if (!target.startsWith(`${trustedRoot}${path.sep}`)) throw new Error("source path escapes repository");
  const stat = await fs.lstat(target).catch(() => {
    throw new Error(`${path.posix.basename(canonical)} must be a regular file`);
  });
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0 || stat.size > maximumBytes) {
    throw new Error(`${path.posix.basename(canonical)} must be a bounded regular file`);
  }
  const real = await fs.realpath(target);
  if (real !== target) {
    throw new Error("source file must not use symlinked path components");
  }
  return await fs.readFile(target);
}

async function readRegularRepositoryFile(
  repositoryPath: string,
  maximumBytes: number,
): Promise<Buffer> {
  return await readBoundedRecorderInput(
    REPO_ROOT,
    repositoryPath,
    maximumBytes,
  );
}

async function sourceReference(repositoryPath: string): Promise<SourceReference> {
  const bytes = await readRegularRepositoryFile(repositoryPath, MAX_FIXTURE_BYTES);
  return Object.freeze({ path: repositoryPath, sha256: sha256(bytes), bytes: bytes.byteLength });
}

function portableFixtureEntryIdentity(value: string): string {
  return value.normalize("NFC").toLocaleLowerCase("en-US");
}

export function assertPortableFixtureEntries(paths: readonly string[]): void {
  const identities = new Set<string>();
  for (const value of paths) {
    const canonical = canonicalRelativePath(value, "fixture entry");
    if (
      canonical.split("/").some((segment) => !SAFE_FIXTURE_FILE.test(segment))
    ) {
      throw new Error("fixture contains an unsafe filename");
    }
    const identity = portableFixtureEntryIdentity(canonical);
    if (identities.has(identity)) {
      throw new Error("fixture entries collide by case or normalization");
    }
    identities.add(identity);
  }
}

async function snapshotFixtureTree(
  root: string,
  repositoryPath: string,
  copyTo?: string,
): Promise<FixtureSnapshot> {
  if (!path.isAbsolute(root)) {
    throw new Error("fixture root must be absolute");
  }
  const trustedRoot = await fs.realpath(root);
  const canonical = canonicalRelativePath(repositoryPath, "fixture");
  const source = path.join(trustedRoot, ...canonical.split("/"));
  if (!source.startsWith(`${trustedRoot}${path.sep}`)) {
    throw new Error("fixture path escapes repository");
  }
  const stat = await fs.lstat(source).catch(() => {
    throw new Error("fixture must be a real directory");
  });
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("fixture must be a real directory");
  }
  const real = await fs.realpath(source);
  if (real !== source) throw new Error("fixture must not use symlinked directories");

  let total = 0;
  let entryCount = 0;
  const directories: string[] = [];
  const files: FixtureTreeFile[] = [];
  const identities = new Set<string>();

  const registerEntry = (relative: string): void => {
    assertPortableFixtureEntries([relative]);
    const identity = portableFixtureEntryIdentity(relative);
    if (identities.has(identity)) {
      throw new Error("fixture entries collide by case or normalization");
    }
    identities.add(identity);
    entryCount += 1;
    if (entryCount > MAX_FIXTURE_FILES * 2) {
      throw new Error("fixture has too many entries");
    }
  };

  const visit = async (directory: string, prefix: string): Promise<void> => {
    const before = await fs.lstat(directory);
    if (!before.isDirectory() || before.isSymbolicLink()) {
      throw new Error("fixture must not contain symlinked or special directories");
    }
    const directoryReal = await fs.realpath(directory);
    if (directoryReal !== directory) {
      throw new Error("fixture must not use symlinked directories");
    }
    const names = (await fs.readdir(directory)).sort();
    if (names.length === 0) {
      throw new Error("fixture must not contain empty directories");
    }
    for (const name of names) {
      if (!SAFE_FIXTURE_FILE.test(name)) {
        throw new Error("fixture contains an unsafe filename");
      }
      const relative = prefix ? `${prefix}/${name}` : name;
      registerEntry(relative);
      const item = path.join(directory, name);
      if (!item.startsWith(`${source}${path.sep}`)) {
        throw new Error("fixture entry escapes its root");
      }
      const itemStat = await fs.lstat(item);
      if (itemStat.isSymbolicLink()) {
        throw new Error("fixture must not contain symlinks");
      }
      if (itemStat.isDirectory()) {
        directories.push(relative);
        await visit(item, relative);
        continue;
      }
      if (!itemStat.isFile() || itemStat.size <= 0) {
        throw new Error("fixture must contain only nonempty regular files");
      }
      const itemReal = await fs.realpath(item);
      if (itemReal !== item) {
        throw new Error("fixture must not use symlinked path components");
      }
      total += itemStat.size;
      if (total > MAX_FIXTURE_BYTES) {
        throw new Error("fixture exceeds the byte limit");
      }
      const contents = await fs.readFile(item);
      const after = await fs.lstat(item);
      if (
        !after.isFile() ||
        after.isSymbolicLink() ||
        after.dev !== itemStat.dev ||
        after.ino !== itemStat.ino ||
        after.size !== itemStat.size ||
        after.mtimeMs !== itemStat.mtimeMs ||
        contents.byteLength !== itemStat.size ||
        (await fs.realpath(item)) !== item
      ) {
        throw new Error("fixture changed while it was read");
      }
      files.push(
        Object.freeze({
          name: relative,
          sha256: sha256(contents),
          bytes: contents.byteLength,
          contents,
        }),
      );
      if (files.length > MAX_FIXTURE_FILES) {
        throw new Error("fixture has an invalid file count");
      }
    }
    const after = await fs.lstat(directory);
    if (
      !after.isDirectory() ||
      after.isSymbolicLink() ||
      after.dev !== before.dev ||
      after.ino !== before.ino ||
      (await fs.realpath(directory)) !== directory
    ) {
      throw new Error("fixture directory changed while it was read");
    }
  };

  await visit(source, "");
  if (files.length === 0) throw new Error("fixture has an invalid file count");
  files.sort((left, right) =>
    left.name < right.name ? -1 : left.name > right.name ? 1 : 0,
  );

  if (copyTo) {
    if (!path.isAbsolute(copyTo)) {
      throw new Error("fixture copy target must be absolute");
    }
    await fs.mkdir(copyTo, { recursive: false, mode: 0o700 });
    directories.sort(
      (left, right) =>
        left.split("/").length - right.split("/").length ||
        (left < right ? -1 : left > right ? 1 : 0),
    );
    for (const directory of directories) {
      await fs.mkdir(path.join(copyTo, ...directory.split("/")), {
        recursive: false,
        mode: 0o700,
      });
    }
    for (const file of files) {
      await fs.writeFile(
        path.join(copyTo, ...file.name.split("/")),
        file.contents,
        { flag: "wx", mode: 0o600 },
      );
    }
  }

  const publicFiles = Object.freeze(
    files.map((file) =>
      Object.freeze({ name: file.name, sha256: file.sha256, bytes: file.bytes }),
    ),
  );
  const digest = sha256(
    publicFiles.map((file) => `${file.name}:${file.sha256}\n`).join(""),
  );
  return Object.freeze({ digest, files: publicFiles });
}

export async function snapshotRecorderFixture(
  root: string,
  repositoryPath: string,
): Promise<FixtureSnapshot> {
  return await snapshotFixtureTree(root, repositoryPath);
}

async function snapshotFixtureDirectory(
  repositoryPath: string,
  copyTo?: string,
): Promise<FixtureSnapshot> {
  return await snapshotFixtureTree(REPO_ROOT, repositoryPath, copyTo);
}

async function ensureReportDirectory(
  paths: GameplayReportPaths,
): Promise<CaptureDirectoryIdentity> {
  const relativeParent = path.posix.dirname(paths.relativeVideo);
  const segments = relativeParent.split("/");
  let current = REPO_ROOT;
  for (const segment of segments) {
    current = path.join(current, segment);
    try {
      const stat = await fs.lstat(current);
      if (!stat.isDirectory() || stat.isSymbolicLink()) {
        throw new Error("recording output parent must be a real directory");
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      await fs.mkdir(current, { mode: 0o700 });
    }
  }
  const realParent = await fs.realpath(path.dirname(paths.video));
  if (!realParent.startsWith(`${REPORT_ROOT}${path.sep}`) && realParent !== REPORT_ROOT) {
    throw new Error("recording output parent escapes the report root");
  }
  const entries = await fs.readdir(path.dirname(paths.video));
  const requestedNames = [paths.video, paths.poster, paths.metadata].map((target) => path.basename(target));
  for (const requested of requestedNames) {
    const collisions = entries.filter(
      (entry) => entry.normalize("NFC").toLocaleLowerCase("en-US") === requested.normalize("NFC").toLocaleLowerCase("en-US"),
    );
    if (collisions.some((entry) => entry !== requested)) {
      throw new Error("recording output collides by case or normalization");
    }
  }
  return await bindCaptureDirectoryIdentity(path.dirname(paths.video));
}

async function readBoundedOutput(target: string, maximumBytes: number, label: string): Promise<Buffer> {
  const stat = await fs.lstat(target);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0 || stat.size > maximumBytes) {
    throw new Error(`${label} must be a bounded regular file`);
  }
  return await fs.readFile(target);
}

function validatePoster(bytes: Buffer, width: number, height: number): void {
  if (bytes.byteLength > MAX_POSTER_BYTES) throw new Error("poster exceeds the byte limit");
  let decoded: ReturnType<typeof PNG.sync.read>;
  try {
    decoded = PNG.sync.read(bytes, { checkCRC: true, skipRescale: false });
  } catch {
    throw new Error("poster must be a complete decodable PNG");
  }
  if (
    decoded.width !== width ||
    decoded.height !== height ||
    decoded.depth !== 8 ||
    decoded.colorType !== 2 ||
    decoded.alpha !== false ||
    decoded.palette !== false ||
    decoded.interlace !== false ||
    !Buffer.isBuffer(decoded.data) ||
    decoded.data.byteLength !== width * height * 4
  ) {
    throw new Error(`poster must decode as an exact ${width}x${height} 8-bit PNG`);
  }
}

async function readTimeline(
  options: GameplayRecorderOptions,
  frameCount: number,
): Promise<{ frames: readonly GameplayFrame[]; reference: SourceReference }> {
  if (options.source.kind === "model-demo") {
    return {
      frames: modelTimeline(frameCount),
      reference: await sourceReference("web/tests/gameplay/timeline.ts"),
    };
  }
  const bytes = await readRegularRepositoryFile(options.source.timeline, MAX_TIMELINE_BYTES);
  let value: unknown;
  try {
    value = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new Error("timeline must be valid UTF-8 JSON");
  }
  return {
    frames: validateRecorderTimeline(value, frameCount),
    reference: Object.freeze({
      path: options.source.timeline,
      sha256: sha256(bytes),
      bytes: bytes.byteLength,
    }),
  };
}

export type RecorderBuildBinding = Readonly<{
  applicationRoot: string;
  source: CanonicalTreeSnapshot;
  materializedSource: CanonicalTreeSnapshot;
  dependencies: RecorderDependencyIdentity;
  servedBuild: ServedNextBuildSnapshot;
}>;

async function assertRecorderInputsUnchanged(
  options: GameplayRecorderOptions,
  simulationFrameCount: number,
  buildBinding: RecorderBuildBinding,
  fixtureBefore: FixtureSnapshot,
  timelineBefore: SourceReference,
): Promise<void> {
  assertCanonicalSnapshotsEqual(
    buildBinding.source,
    await snapshotGameplayBuildInputs(WEB_ROOT),
    "recorder repository source snapshot",
  );
  assertCanonicalSnapshotsEqual(
    buildBinding.materializedSource,
    await snapshotGameplayBuildInputs(buildBinding.applicationRoot),
    "recorder materialized source snapshot",
  );
  assertDependencyIdentityEqual(
    buildBinding.dependencies,
    await validateRecorderDependencies(WEB_ROOT),
  );
  assertCanonicalSnapshotsEqual(
    buildBinding.servedBuild,
    await snapshotServedNextBuild(buildBinding.applicationRoot),
    "recorder served Next build",
  );
  const fixtureAfter =
    options.source.kind === "model-demo"
      ? await modelAssetSetSnapshot()
      : await snapshotFixtureDirectory(options.source.fixture);
  if (JSON.stringify(fixtureBefore) !== JSON.stringify(fixtureAfter)) {
    throw new Error("recording fixture changed during capture; refusing to install output");
  }
  const timelineAfter = await readTimeline(options, simulationFrameCount);
  if (timelineAfter.reference.sha256 !== timelineBefore.sha256) {
    throw new Error("recording timeline changed during capture; refusing to install output");
  }
}

export async function installRecorderCaptureAfterFinalCheck(
  entries: readonly Readonly<{ target: string; bytes: Buffer }>[],
  finalCheck: () => Promise<void>,
  signal: AbortSignal,
  directoryIdentity?: CaptureDirectoryIdentity,
  installOperations: Pick<CaptureInstallOperations, "beforeDirectoryCheck"> = {},
): Promise<void> {
  throwIfCancelled(signal, "recording final source verification");
  if (directoryIdentity) {
    await assertCaptureDirectoryIdentity(directoryIdentity);
  }
  await installCaptureFiles(entries, {
    ...installOperations,
    signal,
    directoryIdentity,
    validateBeforeCommit: finalCheck,
    validateAfterInstall: finalCheck,
  });
}

async function modelAssetSetSnapshot(): Promise<FixtureSnapshot> {
  const repositoryPath = path.relative(REPO_ROOT, GAMEPLAY_DEMO_ROOT).split(path.sep).join("/");
  return await snapshotFixtureDirectory(repositoryPath);
}

async function customFixtureFactory(
  source: Extract<GameplayRecorderSource, { kind: "fixture" }>,
  before: FixtureSnapshot,
  workspace: string,
): Promise<GameplayFixture> {
  const outRoot = path.join(workspace, "out");
  await fs.mkdir(outRoot, { mode: 0o700 });
  const runDir = path.join(outRoot, source.tag);
  const copied = await snapshotFixtureDirectory(source.fixture, runDir);
  if (copied.digest !== before.digest || JSON.stringify(copied.files) !== JSON.stringify(before.files)) {
    throw new Error("fixture changed while it was copied");
  }
  return Object.freeze({
    outRoot,
    runDir,
    tag: source.tag,
    route: `/preview/${source.tag}?automation=${GAMEPLAY_AUTOMATION_VERSION}`,
    files: Object.freeze(copied.files.map((file) => file.name)),
    digest: copied.digest,
  });
}

function mergeAbortSignal(
  external: AbortSignal | undefined,
  timeoutMs: number,
): Readonly<{ signal: AbortSignal; dispose: () => void }> {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new Error(`gameplay recording timed out after ${timeoutMs}ms`)),
    timeoutMs,
  );
  const forward = () => controller.abort(external?.reason);
  if (external?.aborted) forward();
  else external?.addEventListener("abort", forward, { once: true });
  return Object.freeze({
    signal: controller.signal,
    dispose: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", forward);
    },
  });
}

export async function createCanonicalRecorderWorkspace(
  temporaryRoot = tmpdir(),
): Promise<string> {
  const created = await fs.mkdtemp(
    path.join(temporaryRoot, "stage-gen-recorder-build-"),
  );
  const stat = await fs.lstat(created);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("recorder workspace must be a real private directory");
  }
  return await fs.realpath(created);
}

async function toolVersion(executable: "ffmpeg" | "ffprobe", signal: AbortSignal): Promise<string> {
  const result = await runTool(executable, ["-version"], {
    timeoutMs: TOOL_VERSION_TIMEOUT_MS,
    signal,
  });
  const version = result.stdout.split("\n")[0]?.trim();
  if (!version) throw new Error(`${executable} version is missing`);
  return version;
}

export function recorderDryRun(options: GameplayRecorderOptions): Readonly<Record<string, unknown>> {
  const paths = resolveGameplayReportPaths(options.output);
  return Object.freeze({
    mode: "dry-run",
    preset: options.source.kind,
    output: paths.relativeVideo,
    poster: paths.relativePoster,
    metadata: paths.relativeMetadata,
    simulation: Object.freeze({
      fps: GAMEPLAY_FPS,
      frames: options.durationSeconds * GAMEPLAY_FPS,
      durationSeconds: options.durationSeconds,
      duplicateVerification: options.verifyTwice,
    }),
    media: Object.freeze({
      width: options.width,
      height: options.height,
      fps: options.fps,
      frames: options.durationSeconds * options.fps,
      posterFrame: options.posterFrame,
    }),
  });
}

export async function buildRecorderApplication(
  applicationRoot: string,
  signal: AbortSignal,
): Promise<RecorderBuildBinding> {
  throwIfCancelled(signal, "recording build preflight");
  const source = await snapshotGameplayBuildInputs(WEB_ROOT, applicationRoot);
  const materializedSource = await snapshotGameplayBuildInputs(applicationRoot);
  assertCanonicalSnapshotsEqual(
    source,
    materializedSource,
    "recorder materialized source snapshot",
  );
  const dependencies = await validateRecorderDependencies(WEB_ROOT);
  await linkRecorderDependencies(WEB_ROOT, applicationRoot);
  const executedNextCli = path.join(
    applicationRoot,
    ...dependencies.nextCliPath.split("/"),
  );
  if (
    (await fs.realpath(executedNextCli)) !==
    (await fs.realpath(GAMEPLAY_NEXT_CLI_PATH))
  ) {
    throw new Error("recorder build CLI does not match its dependency binding");
  }
  throwIfCancelled(signal, "recording production build");
  await runTool(process.execPath, GAMEPLAY_RECORDER_BUILD_ARGV, {
    timeoutMs: NEXT_BUILD_TIMEOUT_MS,
    signal,
    cwd: applicationRoot,
  });
  await pruneNonRuntimeNextArtifacts(applicationRoot);
  assertCanonicalSnapshotsEqual(
    source,
    await snapshotGameplayBuildInputs(WEB_ROOT),
    "recorder repository source snapshot after build",
  );
  assertCanonicalSnapshotsEqual(
    materializedSource,
    await snapshotGameplayBuildInputs(applicationRoot),
    "recorder materialized source snapshot after build",
  );
  assertDependencyIdentityEqual(
    dependencies,
    await validateRecorderDependencies(WEB_ROOT),
  );
  const servedBuild = await snapshotServedNextBuild(applicationRoot);
  return Object.freeze({
    applicationRoot,
    source,
    materializedSource,
    dependencies,
    servedBuild,
  });
}

export async function recordGameplay(
  options: GameplayRecorderOptions,
  externalSignal?: AbortSignal,
): Promise<GameplayRecordingResult> {
  if (options.mode !== "record") throw new Error("dry-run options cannot record media");
  const paths = resolveGameplayReportPaths(options.output);
  const reportDirectoryIdentity = await ensureReportDirectory(paths);
  const combined = mergeAbortSignal(externalSignal, options.timeoutMs);
  const { signal } = combined;
  let recorderWorkspace: string | undefined;
  try {
    throwIfCancelled(signal, "recording preflight");
    recorderWorkspace = await createCanonicalRecorderWorkspace();
    const applicationRoot = path.join(recorderWorkspace, "source");
    const buildBinding = await buildRecorderApplication(applicationRoot, signal);
    const sourceBefore = buildBinding.source;
    const dependenciesBefore = buildBinding.dependencies;
    const servedBuild = buildBinding.servedBuild;
    const simulationFrameCount = options.durationSeconds * GAMEPLAY_FPS;
    const encodedFrameCount = options.durationSeconds * options.fps;
    const timeline = await readTimeline(options, simulationFrameCount);
    const fixtureBefore =
      options.source.kind === "model-demo"
        ? await modelAssetSetSnapshot()
        : await snapshotFixtureDirectory(options.source.fixture);
    throwIfCancelled(signal, "recording preflight");
    const selectedFrames = Object.freeze(
      [...new Set([
        options.posterFrame,
        ...GAMEPLAY_SELECTED_FRAMES.filter((frame) => frame <= simulationFrameCount),
      ])].sort((left, right) => left - right),
    );
    const prepareFixture = async (workspace: string): Promise<GameplayFixture> =>
      options.source.kind === "model-demo"
        ? await generateApprovedModelGameplayFixture(path.join(workspace, "out"))
        : await customFixtureFactory(options.source, fixtureBefore, workspace);
    const strictModelDemo =
      options.source.kind === "model-demo" &&
      simulationFrameCount === GAMEPLAY_TIMELINE.length;

    return await withGameplaySession(
      {
        prepareFixture,
        timeline: timeline.frames,
        selectedFrames,
        captureFrames: true,
        verifyDuplicate: options.verifyTwice,
        validateRun: strictModelDemo ? validateGameplayRun : undefined,
        applicationRoot,
        validateApplication: async () =>
          await assertRecorderInputsUnchanged(
            options,
            simulationFrameCount,
            buildBinding,
            fixtureBefore,
            timeline.reference,
          ),
        signal,
      },
      async (evidence: GameplaySessionEvidence, workspace: string) => {
        throwIfCancelled(signal, "recording encode");
        const captureWorkspace = await fs.realpath(workspace);
        const captureWorkspaceStat = await fs.lstat(captureWorkspace);
        if (
          !captureWorkspaceStat.isDirectory() ||
          captureWorkspaceStat.isSymbolicLink()
        ) {
          throw new Error("recording capture workspace must be a real directory");
        }
        const [ffmpegVersionBefore, ffprobeVersionBefore] = await Promise.all([
          toolVersion("ffmpeg", signal),
          toolVersion("ffprobe", signal),
        ]);
        const frames = path.join(captureWorkspace, "frames");
        const temporaryVideo = path.join(captureWorkspace, "recording.mp4");
        const temporaryPoster = path.join(
          captureWorkspace,
          "recording.poster.png",
        );
        const mediaCommands = recorderMediaCommands(options);
        await runTool("ffmpeg", mediaCommands.video, {
          timeoutMs: FFMPEG_TIMEOUT_MS,
          signal,
          cwd: captureWorkspace,
        });

        const posterSource = path.join(
          frames,
          `frame-${String(options.posterFrame).padStart(4, "0")}.png`,
        );
        await runTool("ffmpeg", mediaCommands.poster, {
          timeoutMs: FFMPEG_TIMEOUT_MS,
          signal,
          cwd: captureWorkspace,
        });
        throwIfCancelled(signal, "recording probe");

        const probeResult = await runTool("ffprobe", mediaCommands.probe, {
          timeoutMs: FFPROBE_TIMEOUT_MS,
          signal,
          cwd: captureWorkspace,
        });
        let rawProbe: unknown;
        try {
          rawProbe = JSON.parse(probeResult.stdout);
        } catch {
          throw new Error("ffprobe returned malformed JSON");
        }
        const probedMp4 = validateRecordingMp4Probe(rawProbe, {
          width: options.width,
          height: options.height,
          fps: options.fps,
          durationSeconds: options.durationSeconds,
          frameCount: encodedFrameCount,
          maxBytes: MAX_VIDEO_BYTES,
        });
        const videoBytes = await readBoundedOutput(temporaryVideo, MAX_VIDEO_BYTES, "video");
        const posterBytes = await readBoundedOutput(temporaryPoster, MAX_POSTER_BYTES, "poster");
        const probedSize = Number(record(rawProbe, "ffprobe result").format && record(record(rawProbe, "ffprobe result").format, "ffprobe format").size);
        if (probedSize !== videoBytes.byteLength) {
          throw new Error("ffprobe size does not match capture bytes");
        }
        validateFastStartMp4(videoBytes);
        validatePoster(posterBytes, options.width, options.height);
        const mp4 = Object.freeze({ ...probedMp4, fast_start: true as const });
        const sourcePosterBytes = await readBoundedOutput(
          posterSource,
          MAX_POSTER_BYTES,
          "source poster",
        );
        const sourcePosterDigest = sha256(sourcePosterBytes);
        if (
          sourcePosterDigest !==
          evidence.first.selectedFrameHashes[String(options.posterFrame)]
        ) {
          throw new Error("poster source does not match its deterministic checkpoint");
        }
        if (options.width === 1_280 && options.height === 720) {
          const sourcePixels = PNG.sync.read(sourcePosterBytes, {
            checkCRC: true,
            skipRescale: false,
          });
          const posterPixels = PNG.sync.read(posterBytes, {
            checkCRC: true,
            skipRescale: false,
          });
          if (!sourcePixels.data.equals(posterPixels.data)) {
            throw new Error("poster pixels do not match the selected checkpoint");
          }
        }

        throwIfCancelled(signal, "recording source verification");
        await assertRecorderInputsUnchanged(
          options,
          simulationFrameCount,
          buildBinding,
          fixtureBefore,
          timeline.reference,
        );
        throwIfCancelled(signal, "recording metadata");

        const [ffmpegVersion, ffprobeVersion] = await Promise.all([
          toolVersion("ffmpeg", signal),
          toolVersion("ffprobe", signal),
        ]);
        if (
          ffmpegVersion !== ffmpegVersionBefore ||
          ffprobeVersion !== ffprobeVersionBefore
        ) {
          throw new Error("recording media-tool version changed during capture");
        }
        const playwrightVersion = dependenciesBefore.packages.playwright;
        if (!playwrightVersion) throw new Error("Playwright version is missing");
        const videoDigest = sha256(videoBytes);
        const posterDigest = sha256(posterBytes);
        const metadata = {
          schemaVersion: GAMEPLAY_RECORDING_SCHEMA_VERSION,
          state: "unreviewed",
          visualReview: { status: "pending", independent: false },
          artifacts: {
            video: {
              path: paths.relativeVideo,
              mediaType: "video/mp4",
              sha256: videoDigest,
              bytes: videoBytes.byteLength,
            },
            poster: {
              path: paths.relativePoster,
              mediaType: "image/png",
              sha256: posterDigest,
              bytes: posterBytes.byteLength,
            },
          },
          source: {
            kind: options.source.kind,
            fixturePath:
              options.source.kind === "model-demo"
                ? "fixtures/gameplay-demo"
                : options.source.fixture,
            fixtureTag: evidence.fixtureTag,
            fixtureSha256: evidence.fixtureDigest,
            fixtureSetSha256: fixtureBefore.digest,
            timeline: timeline.reference,
          },
          build: {
            owner: "gameplay-recorder",
            command: {
              executable: dependenciesBefore.runtimeExecutable,
              versions: {
                runtime: process.version,
                bun: process.versions.bun ?? null,
                next: dependenciesBefore.packages.next,
              },
              argv: GAMEPLAY_RECORDER_BUILD_ARGV,
              cwd: { root: "materializedSource", relativePath: "." },
            },
            sourceSnapshot: sourceBefore,
            dependencies: dependenciesBefore,
            servedNext: servedBuild,
          },
          deterministic: {
            clock: { mode: "manual-fixed-step", stepMs: GAMEPLAY_STEP_MS },
            simulationFrames: simulationFrameCount,
            simulationDurationSeconds: options.durationSeconds,
            duplicateVerified: evidence.duplicateVerified,
            transcriptSha256: evidence.first.transcriptDigest,
            checkpointSha256: evidence.first.selectedFrameHashes,
            eventFrames: groupGameplayEventFrames(
              evidence.first.finalSnapshot.events,
            ),
            posterSourceSha256: sourcePosterDigest,
          },
          capture: {
            browser: "chromium",
            chromiumVersion: evidence.chromiumVersion,
            playwrightVersion,
            ffmpegVersion,
            ffprobeVersion,
            media: {
              width: options.width,
              height: options.height,
              fps: options.fps,
              frameCount: encodedFrameCount,
              durationSeconds: options.durationSeconds,
              representativeFrame: options.posterFrame,
            },
            commands: {
              videoEncode: {
                executable: "ffmpeg",
                version: ffmpegVersion,
                argv: mediaCommands.video,
                cwd: { root: "captureWorkspace", relativePath: "." },
              },
              posterEncode: {
                executable: "ffmpeg",
                version: ffmpegVersion,
                argv: mediaCommands.poster,
                cwd: { root: "captureWorkspace", relativePath: "." },
              },
              probe: {
                executable: "ffprobe",
                version: ffprobeVersion,
                argv: mediaCommands.probe,
                cwd: { root: "captureWorkspace", relativePath: "." },
              },
            },
            ffmpegArgs: mediaCommands.video,
            posterFfmpegArgs: mediaCommands.poster,
            ffprobeArgs: mediaCommands.probe,
            mp4,
          },
          sources: sourceBefore.files,
        };
        assertPortableRecordingMetadata(metadata);
        const metadataBytes = Buffer.from(`${JSON.stringify(metadata, null, 2)}\n`, "utf8");
        await assertCaptureDirectoryIdentity(reportDirectoryIdentity);
        await installRecorderCaptureAfterFinalCheck(
          [
            { target: paths.video, bytes: videoBytes },
            { target: paths.poster, bytes: posterBytes },
            { target: paths.metadata, bytes: metadataBytes },
          ],
          async () =>
            await assertRecorderInputsUnchanged(
              options,
              simulationFrameCount,
              buildBinding,
              fixtureBefore,
              timeline.reference,
            ),
          signal,
          reportDirectoryIdentity,
        );
        return Object.freeze({
          version: GAMEPLAY_AUTOMATION_VERSION,
          verdict: "unreviewed",
          video: Object.freeze({
            path: paths.relativeVideo,
            sha256: videoDigest,
            bytes: videoBytes.byteLength,
            durationSeconds: mp4.duration_seconds,
          }),
          poster: Object.freeze({
            path: paths.relativePoster,
            sha256: posterDigest,
            bytes: posterBytes.byteLength,
          }),
          metadata: Object.freeze({
            path: paths.relativeMetadata,
            sha256: sha256(metadataBytes),
            bytes: metadataBytes.byteLength,
          }),
          deterministic: Object.freeze({
            simulationFrames: simulationFrameCount,
            duplicateVerified: evidence.duplicateVerified,
            transcriptSha256: evidence.first.transcriptDigest,
          }),
        });
      },
    );
  } finally {
    combined.dispose();
    if (recorderWorkspace) {
      await fs.rm(recorderWorkspace, { recursive: true, force: true });
    }
  }
}
