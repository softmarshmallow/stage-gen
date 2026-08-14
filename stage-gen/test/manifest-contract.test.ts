import { describe, expect, test } from "bun:test";
import { toCanonicalManifestEntry } from "../src/manifest.ts";

describe("generic artifact transparency manifest", () => {
  test("leaves opaque artifacts unmarked", () => {
    expect(
      toCanonicalManifestEntry({ path: "background.png", provenancePath: "background.meta.json" }),
    ).toEqual({ path: "background.png", provenancePath: "background.meta.json" });
  });

  test("publishes only the canonical output while retaining raw provenance", () => {
    const entry = toCanonicalManifestEntry({
      path: "sprite.raw.png",
      provenancePath: "sprite.raw.png.meta.json",
      transparency: {
        mode: "ai",
        canonicalPath: "sprite.png",
        retainedRawPath: "sprite.raw.png",
        canonicalProvenancePath: "sprite.png.meta.json",
        rawProvenancePath: "sprite.raw.png.meta.json",
        derivation: {
          kind: "ai-background-removal",
          sourceSha256: "source",
          outputSha256: "output",
          tool: { name: "background-removal", version: "1" },
        },
      },
    });
    expect(entry.path).toBe("sprite.png");
    expect(entry.provenancePath).toBe("sprite.png.meta.json");
    expect(entry.transparency?.retainedRawPath).toBe("sprite.raw.png");
    expect(Object.keys(entry).filter((key) => key.toLowerCase().includes("raw"))).toEqual([]);
  });
});
