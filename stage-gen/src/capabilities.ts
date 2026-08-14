import { createHash, randomUUID } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { basename, dirname, extname, join, resolve } from "node:path";
import sharp from "sharp";
import type { ArtifactRights } from "@stage-gen/core";
import { createFalBackgroundRemover } from "@stage-gen/background-removal";
import {
  createOpenRouterImageGenerator,
  type ImageAspectRatio,
} from "@stage-gen/image-generation";
import {
  createFfmpegAudioNormalizer,
  createOpenRouterMusicGenerator,
  type AudioNormalizationRequest,
  type AudioNormalizationResult,
  type MusicGenerationRequest,
  type MusicGenerationResult,
  type MusicOutputFormat,
} from "@stage-gen/music-generation";
import { assertCapabilities, type StageGenConfig } from "./config.ts";

export interface CapabilityArtifactResult {
  artifactPath: string;
  provenancePath: string;
  mediaType: string;
  bytes: number;
  attempts: number;
}

export interface GenerateImageOptions {
  prompt: string;
  outputPath: string;
  aspectRatio?: ImageAspectRatio;
  referencePaths?: string[];
}

export async function generateImageArtifact(
  options: GenerateImageOptions,
  config: StageGenConfig,
  signal?: AbortSignal,
): Promise<CapabilityArtifactResult> {
  assertCapabilities(config, ["image-generation"]);
  const output = resolve(options.outputPath);
  if (extname(output).toLowerCase() !== ".png") {
    throw new Error("generate-image output must use a .png extension");
  }
  const references = await Promise.all(
    (options.referencePaths ?? []).map(async (referencePath) => {
      const path = resolve(referencePath);
      const bytes = new Uint8Array(await readFile(path));
      const mediaType = imageMediaType(bytes, extname(path));
      return {
        url: `data:${mediaType};base64,${Buffer.from(bytes).toString("base64")}`,
        provenanceRef: path,
      };
    }),
  );
  const generator = createOpenRouterImageGenerator({
    apiKey: config.openRouterApiKey!,
    model: config.imageModel,
    baseUrl: config.openRouterBaseUrl,
  });
  const result = await generator.generate({
    prompt: options.prompt,
    artifactPath: output,
    signal,
    timeoutMs: config.capabilityTimeoutMs,
    aspectRatio: options.aspectRatio ?? "1:1",
    inputReferences: references,
    quality: "high",
    background: "opaque",
    moderation: "low",
    metadata: { source: "stage-gen-headless" },
    async validate({ bytes, mediaType }) {
      if (mediaType !== "image/png") throw new Error(`expected image/png, received ${mediaType}`);
      const metadata = await sharp(Buffer.from(bytes)).metadata();
      if (!metadata.width || !metadata.height) {
        throw new Error("generated image has invalid dimensions");
      }
    },
  });
  return {
    artifactPath: output,
    provenancePath: result.provenancePath,
    mediaType: result.mediaType,
    bytes: result.bytes.length,
    attempts: result.attempts,
  };
}

export async function removeBackground(
  inputPath: string,
  outputPath: string,
  config: StageGenConfig,
  signal?: AbortSignal,
): Promise<CapabilityArtifactResult> {
  assertCapabilities(config, ["background-removal"]);
  const input = resolve(inputPath);
  const output = resolve(outputPath);
  const inputBytes = new Uint8Array(await readFile(input));
  const inputMediaType = imageMediaType(inputBytes, extname(input));
  const inputMetadata = await sharp(Buffer.from(inputBytes)).metadata();
  const remover = createFalBackgroundRemover({
    apiKey: config.falKey!,
    model: config.backgroundRemovalModel,
    baseUrl: config.falBaseUrl,
  });
  const result = await remover.remove({
    imageUrl: `data:${inputMediaType};base64,${Buffer.from(inputBytes).toString("base64")}`,
    artifactPath: output,
    signal,
    timeoutMs: config.capabilityTimeoutMs,
    outputFormat: "png",
    metadata: {
      source_path: input,
      source_sha256: createHash("sha256").update(inputBytes).digest("hex"),
    },
    validate: async ({ bytes, mediaType }) => {
      if (mediaType !== "image/png") throw new Error(`expected image/png, received ${mediaType}`);
      const metadata = await sharp(Buffer.from(bytes)).metadata();
      if (!metadata.hasAlpha) throw new Error("background removal output has no alpha channel");
      if (
        inputMetadata.width &&
        inputMetadata.height &&
        (metadata.width !== inputMetadata.width || metadata.height !== inputMetadata.height)
      ) {
        throw new Error(
          `background removal dimensions changed from ${inputMetadata.width}x${inputMetadata.height} to ${metadata.width}x${metadata.height}`,
        );
      }
    },
  });
  return {
    artifactPath: output,
    provenancePath: result.provenancePath,
    mediaType: result.mediaType,
    bytes: result.bytes.length,
    attempts: result.attempts,
  };
}

export async function generateMusic(
  prompt: string,
  outputPath: string,
  format: MusicOutputFormat,
  config: StageGenConfig,
  signal?: AbortSignal,
  runtime?: MusicCapabilityRuntime,
): Promise<CapabilityArtifactResult> {
  assertCapabilities(config, ["music-generation"]);
  const output = resolve(outputPath);
  if (extname(output).toLowerCase() !== `.${format}`) {
    throw new Error(`generate-music ${format} output must use a .${format} extension`);
  }
  const rawPath = join(
    dirname(output),
    `.${basename(output)}.${runtime?.randomId() ?? randomUUID()}.raw.${format}`,
  );
  const rawProvenancePath = `${rawPath}.meta.json`;
  const capabilityRuntime =
    runtime ??
    {
      generate: createOpenRouterMusicGenerator({
        apiKey: config.openRouterApiKey!,
        model: config.musicModel,
        baseUrl: config.openRouterBaseUrl,
      }).generate,
      normalize: createFfmpegAudioNormalizer().normalize,
      randomId: randomUUID,
    };
  try {
    const generated = await capabilityRuntime.generate({
      prompt,
      artifactPath: rawPath,
      signal,
      timeoutMs: config.capabilityTimeoutMs,
      outputFormat: format,
      metadata: { source: "stage-gen-headless" },
      rights: unreviewedGeneratedMusicRights(),
      validate({ bytes }) {
        if (bytes.length < 1024) throw new Error("music output is unexpectedly small");
      },
    });
    const normalized = await capabilityRuntime.normalize({
      sourcePath: rawPath,
      sourceProvenancePath: generated.provenancePath,
      artifactPath: output,
      outputFormat: format,
      signal,
      timeoutMs: config.capabilityTimeoutMs,
    });
    return {
      artifactPath: normalized.artifactPath,
      provenancePath: normalized.provenancePath,
      mediaType: normalized.mediaType,
      bytes: normalized.bytes.length,
      attempts: generated.attempts,
    };
  } finally {
    await Promise.all([
      rm(rawPath, { force: true }),
      rm(rawProvenancePath, { force: true }),
    ]);
  }
}

function unreviewedGeneratedMusicRights(): ArtifactRights {
  return {
    status: "unreviewed",
    license_id: null,
    notice: "No redistribution review has been recorded for this generated output.",
    attribution: [],
    basis: [],
    reviewed_at: null,
  };
}

export interface MusicCapabilityRuntime {
  generate(request: MusicGenerationRequest): Promise<MusicGenerationResult>;
  normalize(request: AudioNormalizationRequest): Promise<AudioNormalizationResult>;
  randomId(): string;
}

function imageMediaType(bytes: Uint8Array, extension: string): string {
  if (
    bytes.length >= 8 &&
    [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every(
      (value, index) => bytes[index] === value,
    )
  ) {
    return "image/png";
  }
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "image/jpeg";
  }
  if (
    bytes.length >= 12 &&
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
  ) {
    return "image/webp";
  }
  throw new Error(`unsupported image input${extension ? ` (${extension})` : ""}`);
}
