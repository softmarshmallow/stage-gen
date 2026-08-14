import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rm } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import sharp from "sharp";
import {
  writeArtifactWithProvenance,
  type ArtifactProvenance,
  type JsonObject,
} from "@stage-gen/core";
import { aiRequestControl, imageGenerator } from "./client.ts";
import { normalizeImageBytes } from "./normalize-image.ts";
import type { TransparencyMode } from "../../../../src/config.ts";
import { transparencyPromptFragment } from "./transparency-prompt.ts";
import { applyTransparency } from "../post/transparency.ts";

export interface ImageGenArgs {
  stage: string;
  userPrompt: string;
  promptText: string;
  refs?: string[];
  outPath: string;
  width: number;
  height: number;
  model: string;
  /** Omit for opaque artifacts. Transparent assets retain `<stem>.raw.png`. */
  transparencyMode?: TransparencyMode;
  extra?: Record<string, unknown>;
}

export interface ImageGenResult {
  imagePath: string;
  metaPath: string;
}

export async function generateImageAsset(args: ImageGenArgs): Promise<ImageGenResult> {
  const {
    stage,
    promptText,
    refs = [],
    outPath,
    width,
    height,
    extra,
    transparencyMode,
  } = args;
  await mkdir(dirname(outPath), { recursive: true });

  const retainedRawPath = transparencyMode ? rawPathFor(outPath) : outPath;
  if (process.env.STAGE_GEN_FORCE !== "1") {
    if (!transparencyMode && (await validCache(outPath, width, height))) {
      return { imagePath: outPath, metaPath: `${outPath}.meta.json` };
    }
    if (
      transparencyMode &&
      (await validCache(retainedRawPath, width, height, transparencyMode))
    ) {
      if (await validTransparencyCache(outPath, retainedRawPath, transparencyMode, width, height)) {
        return { imagePath: outPath, metaPath: `${outPath}.meta.json` };
      }
      const derived = await applyTransparency({
        mode: transparencyMode,
        rawPath: retainedRawPath,
        canonicalPath: outPath,
        width,
        height,
        stage,
      });
      return { imagePath: derived.imagePath, metaPath: derived.metaPath };
    }
  }

  const inputReferences = await Promise.all(
    refs.map(async (path) => ({
      url: `data:image/png;base64,${Buffer.from(await readFile(path)).toString("base64")}`,
      provenanceRef: path,
    })),
  );
  const providerPath = join(
    dirname(retainedRawPath),
    `.${basename(retainedRawPath)}.provider-${randomUUID()}.png`,
  );
  const control = aiRequestControl();
  const effectivePrompt = promptForImageAsset(promptText, transparencyMode);

  try {
    const result = await imageGenerator().generate({
      prompt: effectivePrompt,
      artifactPath: providerPath,
      inputReferences,
      aspectRatio: ratio(width, height),
      quality: "high",
      background: "opaque",
      moderation: "low",
      signal: control.signal,
      timeoutMs: control.timeoutMs,
      metadata: {
        stage,
        user_prompt: args.userPrompt,
        requested_width: width,
        requested_height: height,
        ...(transparencyMode ? { transparency_mode: transparencyMode } : {}),
        ...(extra ?? {}),
      },
      validate: async ({ bytes, mediaType }) => {
        if (mediaType !== "image/png") {
          throw new Error(`${stage}: expected image/png, received ${mediaType}`);
        }
        const metadata = await sharp(Buffer.from(bytes), { failOn: "error" }).metadata();
        if (!metadata.width || !metadata.height) {
          throw new Error(`${stage}: provider image has invalid dimensions`);
        }
        return { source_width: metadata.width, source_height: metadata.height };
      },
    });

    const normalized = await normalizeImageBytes(result.bytes, {
      width,
      height,
      signal: control.signal,
    });
    const source = parseProvenance(await readFile(result.provenancePath, "utf8"));
    const sourceMetadata = isObject(source.params.metadata) ? source.params.metadata : {};
    const normalization = normalized.record as unknown as JsonObject;
    const metaPath = await writeArtifactWithProvenance(
      retainedRawPath,
      { bytes: normalized.bytes, mediaType: "image/png" },
      {
        provider: source.provider,
        model: source.model,
        seed: source.seed,
        prompt: source.prompt,
        refs: source.refs,
        inputs: [
          ...source.inputs,
          {
            ref: `provider-output:${stage}`,
            source: "content",
            sha256: normalized.record.source.sha256,
            bytes: normalized.record.source.bytes,
            media_type: "image/png",
          },
        ],
        params: {
          ...source.params,
          metadata: { ...sourceMetadata, normalization },
          postprocess: [normalization],
        },
        validation: {
          ...source.validation,
          exact_contract_dimensions: true,
          output_width: width,
          output_height: height,
          output_sha256: normalized.record.output.sha256,
        },
        component: { name: "@stage-gen/stage-gen", version: "0.0.0" },
        tool: normalized.record.tool,
        attempts: source.attempts,
        response: {
          ...(source.response ?? {}),
          source_component: source.component,
          source_artifact_sha256: normalized.record.source.sha256,
        },
      },
    );
    if (!transparencyMode) {
      return { imagePath: outPath, metaPath };
    }
    const derived = await applyTransparency({
      mode: transparencyMode,
      rawPath: retainedRawPath,
      canonicalPath: outPath,
      width,
      height,
      stage,
    });
    return { imagePath: derived.imagePath, metaPath: derived.metaPath };
  } finally {
    await Promise.all([
      rm(providerPath, { force: true }),
      rm(`${providerPath}.meta.json`, { force: true }),
    ]);
  }
}

export function promptForImageAsset(
  promptText: string,
  transparencyMode?: TransparencyMode,
): string {
  return transparencyMode
    ? `${promptText.trim()}\n\n${transparencyPromptFragment(transparencyMode)}`
    : promptText;
}

async function validTransparencyCache(
  canonicalPath: string,
  retainedRawPath: string,
  mode: TransparencyMode,
  width: number,
  height: number,
): Promise<boolean> {
  try {
    const [bytes, rawBytes, rawMeta, canonicalMeta] = await Promise.all([
      readFile(canonicalPath),
      readFile(retainedRawPath),
      readFile(`${retainedRawPath}.meta.json`, "utf8"),
      readFile(`${canonicalPath}.meta.json`, "utf8"),
    ]);
    const provenance = parseProvenance(canonicalMeta);
    const source = parseProvenance(rawMeta);
    const metadata = await sharp(bytes, { failOn: "error" }).metadata();
    const transparency = isObject(provenance.params.transparency)
      ? (provenance.params.transparency as Record<string, unknown>)
      : undefined;
    return (
      provenance.artifact?.sha256 === sha256(bytes) &&
      source.artifact?.sha256 === sha256(rawBytes) &&
      metadata.width === width &&
      metadata.height === height &&
      metadata.hasAlpha === true &&
      transparency?.mode === mode &&
      transparency?.raw_sha256 === sha256(rawBytes) &&
      transparency?.retained_raw_path === retainedRawPath &&
      provenance.validation.alpha_nontrivial === true
    );
  } catch {
    return false;
  }
}

async function validCache(
  path: string,
  width: number,
  height: number,
  transparencyMode?: TransparencyMode,
): Promise<boolean> {
  try {
    const [bytes, rawMeta] = await Promise.all([
      readFile(path),
      readFile(`${path}.meta.json`, "utf8"),
    ]);
    const provenance = parseProvenance(rawMeta);
    if (provenance.artifact?.sha256 !== sha256(bytes)) return false;
    const metadata = await sharp(bytes, { failOn: "error" }).metadata();
    if (metadata.width !== width || metadata.height !== height) return false;
    const provenanceMetadata = provenance.params.metadata;
    const metadataRecord = isObject(provenanceMetadata)
      ? (provenanceMetadata as Record<string, unknown>)
      : undefined;
    const normalization = metadataRecord?.normalization;
    return (
      isObject(normalization) &&
      provenance.validation.exact_contract_dimensions === true &&
      (transparencyMode === undefined ||
        metadataRecord?.transparency_mode === transparencyMode)
    );
  } catch {
    return false;
  }
}

function parseProvenance(raw: string): ArtifactProvenance {
  const parsed: unknown = JSON.parse(raw);
  if (!isObject(parsed) || parsed.schema_version !== 1 || !isObject(parsed.params)) {
    throw new Error("provider provenance is invalid");
  }
  return parsed as unknown as ArtifactProvenance;
}

function isObject(value: unknown): value is Record<string, any> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function ratio(width: number, height: number): `${number}:${number}` {
  const divisor = gcd(width, height);
  return `${width / divisor}:${height / divisor}`;
}

function gcd(a: number, b: number): number {
  let x = Math.abs(a);
  let y = Math.abs(b);
  while (y > 0) [x, y] = [y, x % y];
  return x || 1;
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function rawPathFor(canonicalPath: string): string {
  return canonicalPath.toLowerCase().endsWith(".png")
    ? `${canonicalPath.slice(0, -4)}.raw.png`
    : `${canonicalPath}.raw.png`;
}
