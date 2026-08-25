import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "bun:test";

const source = readFileSync(path.join(import.meta.dir, "scene.ts"), "utf8");
const assetsSource = readFileSync(path.join(import.meta.dir, "assets.ts"), "utf8");
const imageOpsSource = readFileSync(
  path.join(import.meta.dir, "image-ops.ts"),
  "utf8",
);
const playerSource = readFileSync(path.join(import.meta.dir, "player.ts"), "utf8");
const npcSource = readFileSync(path.join(import.meta.dir, "npc.ts"), "utf8");

describe("current scene manifest boundary", () => {
  test("requires every manifest fetch instead of treating 404 as supported absence", () => {
    expect(source).toContain("if (!response.ok) throw new Error");
    expect(source).toContain("return parseScrollingManifestEnvelope");
    expect(source).not.toContain('if (response.status === 404) return null');
  });

  test("reads only lower_snake_case runtime asset fields", () => {
    expect(source).toContain('const entries = manifest["runtime_assets"]');
    expect(source).toContain('const slot = entry["runtime_slot"]');
    expect(source).not.toContain('record["runtimeAssets"]');
    expect(source).not.toContain('entry["runtimeSlot"]');
  });

  test("requires measured actor scale without nullable or fixed-height actor fallbacks", () => {
    expect(source).toContain("runtimeScaleReferences(manifest)");
    expect(source).toContain("assertMeasuredActorClosure(spec)");
    expect(playerSource).toContain(
      "scaleReferences: ReadonlyMap<string, ScaleReference>",
    );
    expect(playerSource).not.toContain(
      "scaleReferences?: ReadonlyMap<string, ScaleReference>",
    );
    expect(npcSource).toContain("scaleReference: ScaleReference;");
    expect(npcSource).not.toContain("scaleReference: ScaleReference | null");
    expect(npcSource).not.toContain("spriteHeightPx");
  });

  test("uses only the current map-scoped soundtrack identity", () => {
    expect(source).toContain("game-soundtrack-v2");
    expect(source).not.toContain('soundtrack.map_scoped === true ? "v2" : "v1"');
    expect(source).not.toContain("A v1 catalog stays run-global");
  });

  test("accepts only producer-owned canonical alpha", () => {
    expect(assetsSource).toContain(
      'if (policy !== "canonical-alpha")',
    );
    expect(assetsSource).not.toContain("legacy-chroma");
    expect(assetsSource).not.toContain("chromaKeyToAlpha");
    expect(imageOpsSource).not.toContain("chromaKeyToAlpha");
    expect(imageOpsSource).not.toContain("magenta");
  });
});
