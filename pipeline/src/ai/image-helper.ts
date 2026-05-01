// Shared helper for image-gen calls in the pipeline.
//
// One place to encapsulate the boring + load-bearing parts every generator
// needs to do identically:
//   - resolve reference image paths to bytes (concept + templates)
//   - call generateImage via the AI SDK with size + low moderation
//   - verify W/H against the asset contract — silent failure mode (per
//     AGENTS.md), retried inside withRetry
//   - write the PNG bytes to disk
//   - emit a `<artifact>.meta.json` sidecar with prompt, model, refs, params,
//     timestamp, attempts (TC-042).
//
// Generators import this and supply: prompt text, refs, output path, size.

import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { dirname } from "node:path";
import sharp from "sharp";
import { generateImage } from "./client.ts";
import { withRetry } from "./retry.ts";
import { writeMeta } from "../meta.ts";

export interface ImageGenArgs {
  /** Stage label for retry / meta. */
  stage: string;
  /** The user's world prompt (carried into the meta sidecar — not the model prompt). */
  userPrompt: string;
  /** The text prompt sent to the image model. */
  promptText: string;
  /** Reference image paths (read once, attached as bytes). Order matches the prompt's "IMAGE 1 / IMAGE 2 / ..." labels. */
  refs?: string[];
  /** Absolute output path for the PNG. */
  outPath: string;
  /** Expected canvas dimensions; mismatch triggers a retry. */
  width: number;
  height: number;
  /** Model id (env.IMAGE_MODEL). */
  model: string;
  /** Free-form bag for stage-specific notes recorded in the meta sidecar. */
  extra?: Record<string, unknown>;
  /** Override retry attempts (default 5 retries → 6 total attempts). */
  retries?: number;
}

export interface ImageGenResult {
  imagePath: string;
  metaPath: string;
}

export async function generateImageAsset(args: ImageGenArgs): Promise<ImageGenResult> {
  const {
    stage,
    userPrompt,
    promptText,
    refs = [],
    outPath,
    width,
    height,
    model,
    extra,
    retries = 5,
  } = args;

  await mkdir(dirname(outPath), { recursive: true });

  // Skip-if-exists: TC-123 contract — re-running a complete tag is a no-op.
  // If the output PNG and its meta sidecar already exist non-empty, return
  // them without calling the SDK. Set STAGE_GEN_FORCE=1 to force regeneration.
  const force = process.env.STAGE_GEN_FORCE === "1";
  if (!force) {
    const metaPath = `${outPath}.meta.json`;
    try {
      const [imgStat, metaStat] = await Promise.all([stat(outPath), stat(metaPath)]);
      if (imgStat.isFile() && imgStat.size > 0 && metaStat.isFile() && metaStat.size > 0) {
        // No file mtime / bytes change on this code path — bail before any write.
        return { imagePath: outPath, metaPath };
      }
    } catch {
      // Either file is missing — fall through to generate.
    }
  }

  // Read all refs ONCE outside the retry loop — the bytes are stable.
  const refBytes: Uint8Array[] = [];
  for (const refPath of refs) {
    refBytes.push(new Uint8Array(await readFile(refPath)));
  }

  const sizeStr = `${width}x${height}` as const;

  let attempts = 0;
  const bytes = await withRetry<Uint8Array>(
    async () => {
      attempts++;
      const promptPayload =
        refBytes.length > 0
          ? { text: promptText, images: refBytes }
          : promptText;
      const result = await generateImage({
        model,
        prompt: promptPayload as any,
        size: sizeStr,
        providerOptions: { openai: { moderation: "low" } },
        maxRetries: 3,
      });
      const out: any = (result as any).image ?? (result as any).images?.[0];
      if (!out) throw new Error(`${stage}: generateImage returned no image`);
      const u8: Uint8Array | undefined =
        out.uint8Array ??
        (out.base64 ? new Uint8Array(Buffer.from(out.base64, "base64")) : undefined);
      if (!u8 || u8.length === 0) {
        throw new Error(`${stage}: generateImage returned empty bytes`);
      }
      const meta = await sharp(Buffer.from(u8)).metadata();
      if (meta.width !== width || meta.height !== height) {
        throw new Error(
          `${stage}: dimensions mismatch — got ${meta.width}x${meta.height}, want ${width}x${height}`,
        );
      }
      return u8;
    },
    { label: stage, retries },
  );

  await writeFile(outPath, bytes);
  const metaPath = await writeMeta(outPath, {
    stage,
    prompt: userPrompt,
    ts: new Date().toISOString(),
    model,
    refs,
    params: {
      size: sizeStr,
      moderation: "low",
    },
    extra: {
      promptText,
      width,
      height,
      bytes: bytes.length,
      attempts,
      ...(extra ?? {}),
    },
  });

  return { imagePath: outPath, metaPath };
}
