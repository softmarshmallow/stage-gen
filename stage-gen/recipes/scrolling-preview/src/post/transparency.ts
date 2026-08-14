import { createHash, randomUUID } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import sharp from "sharp";
import {
  writeArtifactWithProvenance,
  type ArtifactProvenance,
  type BinaryArtifact,
  type JsonObject,
} from "@stage-gen/core";
import type {
  BackgroundMaskArtifact,
  BackgroundRemovalRequest,
  BackgroundRemovalResult,
} from "@stage-gen/background-removal";
import type { TransparencyMode } from "../../../../src/config.ts";
import { aiRequestControl, backgroundRemover } from "../ai/client.ts";

const CHROMA = { r: 255, g: 0, b: 255 } as const;
export const CHROMA_DISTANCE_THRESHOLD = 36;

export interface TransparencyResult {
  imagePath: string;
  metaPath: string;
  rawPath: string;
  rawMetaPath: string;
  mode: TransparencyMode;
  transparentPixels: number;
  nontransparentPixels: number;
}

export interface BackgroundRemovalExecutor {
  remove(request: BackgroundRemovalRequest): Promise<BackgroundRemovalResult>;
}

export interface ApplyTransparencyArgs {
  mode: TransparencyMode;
  rawPath: string;
  canonicalPath: string;
  width: number;
  height: number;
  stage: string;
  remover?: BackgroundRemovalExecutor;
  control?: { signal: AbortSignal; timeoutMs: number };
}

interface DerivedPixels {
  bytes: Uint8Array;
  transparentPixels: number;
  nontransparentPixels: number;
  processor: JsonObject;
  removal?: {
    provider: string;
    model: string;
    attempts: number;
    maskUsed: boolean;
    /** Complete, already-redacted remover sidecar captured before temp cleanup. */
    provenance: JsonObject;
  };
}

/** Derive a canonical transparent PNG without modifying the retained raw PNG. */
export async function applyTransparency(
  args: ApplyTransparencyArgs,
): Promise<TransparencyResult> {
  const rawBytes = new Uint8Array(await readFile(args.rawPath));
  const rawProvenance = parseProvenance(
    await readFile(`${args.rawPath}.meta.json`, "utf8"),
  );
  const rawMetadata = await sharp(rawBytes, { failOn: "error" }).metadata();
  if (rawMetadata.width !== args.width || rawMetadata.height !== args.height) {
    throw new Error(
      `${args.stage}: retained raw dimensions changed from ${args.width}x${args.height}`,
    );
  }

  const control = args.control ?? aiRequestControl();
  throwIfAborted(control.signal);
  const derived =
    args.mode === "ai"
      ? await deriveWithAi(args, rawBytes, control)
      : await deriveWithChroma(rawBytes, args.width, args.height, control.signal);
  throwIfAborted(control.signal);

  const rawSha256 = sha256(rawBytes);
  const outputSha256 = sha256(derived.bytes);
  const transparencyParams: JsonObject = {
    mode: args.mode,
    retained_raw_path: args.rawPath,
    canonical_path: args.canonicalPath,
    raw_sha256: rawSha256,
    output_sha256: outputSha256,
    processor: derived.processor,
    ...(derived.removal ? { removal: derived.removal } : {}),
  };
  const metadata = isRecord(rawProvenance.params.metadata)
    ? rawProvenance.params.metadata
    : {};
  const metaPath = await writeArtifactWithProvenance(
    args.canonicalPath,
    { bytes: derived.bytes, mediaType: "image/png" },
    {
      provider: rawProvenance.provider,
      model: rawProvenance.model,
      seed: rawProvenance.seed,
      prompt: rawProvenance.prompt,
      refs: [...new Set([...rawProvenance.refs, args.rawPath])],
      inputs: [
        ...rawProvenance.inputs,
        {
          ref: args.rawPath,
          source: "content",
          sha256: rawSha256,
          bytes: rawBytes.length,
          media_type: "image/png",
        },
      ],
      params: {
        ...rawProvenance.params,
        metadata: {
          ...metadata,
          transparency_mode: args.mode,
          retained_raw_path: args.rawPath,
        },
        transparency: transparencyParams,
      },
      validation: {
        ...rawProvenance.validation,
        transparency_mode: args.mode,
        dimensions_preserved: true,
        output_width: args.width,
        output_height: args.height,
        alpha_nontrivial: true,
        transparent_pixels: derived.transparentPixels,
        nontransparent_pixels: derived.nontransparentPixels,
        raw_sha256: rawSha256,
        output_sha256: outputSha256,
      },
      component: { name: "@stage-gen/stage-gen", version: "0.0.0" },
      tool:
        args.mode === "ai"
          ? { name: "ai-alpha-compositor", version: "1" }
          : { name: "global-chroma-alpha", version: "1" },
      attempts: rawProvenance.attempts,
      response: {
        ...(rawProvenance.response ?? {}),
        transparency: {
          mode: args.mode,
          retained_raw_path: args.rawPath,
          raw_sha256: rawSha256,
          output_sha256: outputSha256,
          ...(derived.removal
            ? {
                removal_provider: derived.removal.provider,
                removal_model: derived.removal.model,
                removal_attempts: derived.removal.attempts,
                removal_provenance: "inline",
                mask_used: derived.removal.maskUsed,
              }
            : {}),
        },
      },
    },
  );

  return {
    imagePath: args.canonicalPath,
    metaPath,
    rawPath: args.rawPath,
    rawMetaPath: `${args.rawPath}.meta.json`,
    mode: args.mode,
    transparentPixels: derived.transparentPixels,
    nontransparentPixels: derived.nontransparentPixels,
  };
}

async function deriveWithAi(
  args: ApplyTransparencyArgs,
  rawBytes: Uint8Array,
  control: { signal: AbortSignal; timeoutMs: number },
): Promise<DerivedPixels> {
  const executor = args.remover ?? backgroundRemover();
  const temporaryPath = join(
    dirname(args.canonicalPath),
    `.${basename(args.canonicalPath)}.removal-${randomUUID()}.png`,
  );
  let validated: DerivedPixels | undefined;
  try {
    const result = await executor.remove({
      imageUrl: `data:image/png;base64,${Buffer.from(rawBytes).toString("base64")}`,
      artifactPath: temporaryPath,
      outputFormat: "png",
      outputMask: true,
      syncMode: true,
      signal: control.signal,
      timeoutMs: control.timeoutMs,
      metadata: {
        stage: args.stage,
        transparency_mode: "ai",
        retained_raw_path: args.rawPath,
        retained_raw_sha256: sha256(rawBytes),
      },
      validate: async (artifact, context) => {
        validated = await composeRawWithProviderAlpha(
          rawBytes,
          artifact,
          context.mask,
          args.width,
          args.height,
        );
        return {
          dimensions_preserved: true,
          alpha_nontrivial: true,
          transparent_pixels: validated.transparentPixels,
          nontransparent_pixels: validated.nontransparentPixels,
          mask_used: context.mask !== undefined,
        };
      },
    });
    const composed =
      validated ??
      (await composeRawWithProviderAlpha(
        rawBytes,
        { bytes: result.bytes, mediaType: result.mediaType },
        result.mask,
        args.width,
        args.height,
      ));
    const removalProvenanceText = await readFile(result.provenancePath, "utf8");
    if (removalProvenanceText.includes(temporaryPath)) {
      throw new Error("background remover provenance contains a temporary artifact path");
    }
    const removalProvenance = parseProvenance(removalProvenanceText);
    return {
      ...composed,
      processor: {
        kind: "ai-background-removal",
        composition: "retained-raw-rgb-plus-provider-alpha",
        mask_preferred: true,
        mask_used: result.mask !== undefined,
      },
      removal: {
        provider: result.provider,
        model: result.model,
        attempts: result.attempts,
        maskUsed: result.mask !== undefined,
        provenance: removalProvenance as unknown as JsonObject,
      },
    };
  } finally {
    await Promise.all([
      rm(temporaryPath, { force: true }),
      rm(`${temporaryPath}.meta.json`, { force: true }),
    ]);
  }
}

async function deriveWithChroma(
  rawBytes: Uint8Array,
  width: number,
  height: number,
  signal: AbortSignal,
): Promise<DerivedPixels> {
  const { data, info } = await sharp(rawBytes, { failOn: "error" })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (info.width !== width || info.height !== height || info.channels !== 4) {
    throw new Error("chroma transparency input dimensions or channels are invalid");
  }
  let keyedPixels = 0;
  for (let offset = 0; offset < data.length; offset += 4) {
    if ((offset & 0x3ffff) === 0) throwIfAborted(signal);
    const distance =
      Math.abs(data[offset] - CHROMA.r) +
      Math.abs(data[offset + 1] - CHROMA.g) +
      Math.abs(data[offset + 2] - CHROMA.b);
    if (distance <= CHROMA_DISTANCE_THRESHOLD) {
      data[offset] = CHROMA.r;
      data[offset + 1] = CHROMA.g;
      data[offset + 2] = CHROMA.b;
      data[offset + 3] = 0;
      keyedPixels += 1;
    } else {
      data[offset + 3] = 255;
    }
  }
  const bytes = new Uint8Array(
    await sharp(data, { raw: { width, height, channels: 4 } }).png().toBuffer(),
  );
  const facts = assertNontrivialAlpha(data, width, height);
  return {
    bytes,
    ...facts,
    processor: {
      kind: "chroma-key",
      method: "global-color-distance-to-alpha",
      key_color: "#FF00FF",
      distance_metric: "rgb-manhattan",
      distance_threshold: CHROMA_DISTANCE_THRESHOLD,
      keyed_pixels: keyedPixels,
      connectivity: "none",
    },
  };
}

async function composeRawWithProviderAlpha(
  rawBytes: Uint8Array,
  providerOutput: BinaryArtifact,
  mask: BackgroundMaskArtifact | undefined,
  width: number,
  height: number,
): Promise<DerivedPixels> {
  if (providerOutput.mediaType !== "image/png") {
    throw new Error(`background removal expected image/png, received ${providerOutput.mediaType}`);
  }
  const source = await sharp(rawBytes, { failOn: "error" })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (source.info.width !== width || source.info.height !== height || source.info.channels !== 4) {
    throw new Error("retained raw image dimensions or channels are invalid");
  }

  const alpha = mask
    ? await alphaFromMask(mask, width, height)
    : await alphaFromRemovedImage(providerOutput.bytes, width, height);
  for (let pixel = 0; pixel < alpha.length; pixel += 1) {
    source.data[pixel * 4 + 3] = alpha[pixel];
  }
  const facts = assertNontrivialAlpha(source.data, width, height);
  const bytes = new Uint8Array(
    await sharp(source.data, { raw: { width, height, channels: 4 } }).png().toBuffer(),
  );
  return {
    bytes,
    ...facts,
    processor: {},
  };
}

async function alphaFromMask(
  mask: BackgroundMaskArtifact,
  width: number,
  height: number,
): Promise<Uint8Array> {
  const decoded = await sharp(mask.bytes, { failOn: "error" })
    .removeAlpha()
    .greyscale()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (decoded.info.width !== width || decoded.info.height !== height) {
    throw new Error("background removal mask dimensions changed");
  }
  return new Uint8Array(decoded.data);
}

async function alphaFromRemovedImage(
  bytes: Uint8Array,
  width: number,
  height: number,
): Promise<Uint8Array> {
  const metadata = await sharp(bytes, { failOn: "error" }).metadata();
  if (!metadata.hasAlpha) throw new Error("background removal returned neither a mask nor alpha");
  const decoded = await sharp(bytes, { failOn: "error" })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (decoded.info.width !== width || decoded.info.height !== height || decoded.info.channels !== 4) {
    throw new Error("background removal output dimensions or channels changed");
  }
  const alpha = new Uint8Array(width * height);
  for (let pixel = 0; pixel < alpha.length; pixel += 1) {
    alpha[pixel] = decoded.data[pixel * 4 + 3];
  }
  return alpha;
}

function assertNontrivialAlpha(
  rgba: Uint8Array,
  width: number,
  height: number,
): { transparentPixels: number; nontransparentPixels: number } {
  if (rgba.length !== width * height * 4) throw new Error("RGBA buffer size is invalid");
  let transparentPixels = 0;
  let nontransparentPixels = 0;
  for (let offset = 3; offset < rgba.length; offset += 4) {
    if (rgba[offset] < 255) transparentPixels += 1;
    if (rgba[offset] > 0) nontransparentPixels += 1;
  }
  if (transparentPixels === 0 || nontransparentPixels === 0) {
    throw new Error("transparency output must contain both transparent and nontransparent pixels");
  }
  return { transparentPixels, nontransparentPixels };
}

function parseProvenance(raw: string): ArtifactProvenance {
  const parsed: unknown = JSON.parse(raw);
  if (!isRecord(parsed) || parsed.schema_version !== 1 || !isRecord(parsed.params)) {
    throw new Error("retained raw provenance is invalid");
  }
  return parsed as unknown as ArtifactProvenance;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw signal.reason ?? new DOMException("aborted", "AbortError");
}
