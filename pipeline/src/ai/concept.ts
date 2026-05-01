// Concept-stage generator.
//
// Wave 1, single-shot text-to-image call producing the world's painterly
// concept art. The output is the style root for every downstream image in
// the pipeline — so this stage MUST land first and MUST be opaque (no chroma
// key). See docs/spec/asset-contracts.md "World concept" + agent-prompts.md.
//
// Contract:
//   - Output: out/<tag>/concept_<tag>.png
//   - Size:   1536 × 1024 (3:2 landscape) — verified post-decode; mismatch retries.
//   - Wraps the SDK call in withRetry (5 blind retries with backoff per
//     AGENTS.md). Empty bytes / dimension mismatch / SDK errors all retry.
//   - Writes a sidecar concept_<tag>.png.meta.json (prompt, model, params, ts).

import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import sharp from "sharp";
import { generateImage } from "./client.ts";
import { withRetry } from "./retry.ts";
import { writeMeta } from "../meta.ts";

const CANVAS_W = 1536;
const CANVAS_H = 1024;

export interface ConceptArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
}

export interface ConceptResult {
  imagePath: string;
  metaPath: string;
}

function buildConceptPrompt(theme: string): string {
  // Verbatim shape from docs/spec/agent-prompts.md `generate_concept`.
  return (
    `2D side-scrolling platformer scene concept art, wide cinematic landscape view.\n` +
    `Theme: ${theme}.\n` +
    `Compose clear DEPTH: distant background (sky, distant mountains, soft atmosphere), middle (mid-distance trees / rolling hills), foreground (close trees / grass / near rocks).\n` +
    `Hand-painted painterly look. Single image, fully opaque — this is a STYLE REFERENCE, not a sprite. NO magenta chroma key, NO transparent regions, no text or labels.`
  );
}

export async function generateConcept(args: ConceptArgs): Promise<ConceptResult> {
  const { prompt, tag, runDir, model } = args;
  await mkdir(runDir, { recursive: true });
  const imagePath = join(runDir, `concept_${tag}.png`);

  const promptText = buildConceptPrompt(prompt);
  const sizeStr = `${CANVAS_W}x${CANVAS_H}`;

  const bytes = await withRetry(
    async () => {
      const result = await generateImage({
        model,
        prompt: promptText,
        size: sizeStr as `${number}x${number}`,
        providerOptions: { openai: { moderation: "low" } },
        // SDK-internal retries on top of our outer loop, per gpt-image-2.md.
        maxRetries: 3,
      });
      // Pull bytes from whichever shape the SDK version returns.
      const out: any = (result as any).image ?? (result as any).images?.[0];
      if (!out) throw new Error("generateImage returned no image");
      const u8: Uint8Array | undefined =
        out.uint8Array ??
        (out.base64 ? new Uint8Array(Buffer.from(out.base64, "base64")) : undefined);
      if (!u8 || u8.length === 0) throw new Error("generateImage returned empty bytes");

      // Verify dimensions — silent failure mode per AGENTS.md (retry on mismatch).
      const meta = await sharp(Buffer.from(u8)).metadata();
      if (meta.width !== CANVAS_W || meta.height !== CANVAS_H) {
        throw new Error(
          `concept dimensions mismatch: got ${meta.width}x${meta.height}, want ${CANVAS_W}x${CANVAS_H}`,
        );
      }
      return u8;
    },
    { label: "concept", retries: 5 },
  );

  await writeFile(imagePath, bytes);
  const metaPath = await writeMeta(imagePath, {
    stage: "concept",
    prompt,
    ts: new Date().toISOString(),
    model,
    params: {
      size: sizeStr,
      moderation: "low",
    },
    extra: {
      promptText,
      width: CANVAS_W,
      height: CANVAS_H,
      bytes: bytes.length,
    },
  });

  return { imagePath, metaPath };
}
