import { describe, expect, test } from "bun:test";
import { parseArtifactPreview, parseLegacyMotion, parallaxOffset } from "./artifact-preview";

import { parallaxFixture } from "./artifact-preview.fixture";

describe("artifact preview adapters", () => {
  test("parallax orders supplied layers and applies separate camera motion", () => {
    const preview = parseArtifactPreview(parallaxFixture(), "preview");
    expect(preview?.supported).toBe(true);
    if (!preview?.supported) throw new Error("expected supported preview");
    expect(preview.content.layers.map((layer) => layer.layerId)).toEqual(["sky", "near"]);
    expect(parallaxOffset(preview.content.layers[0], 100, 50)).toEqual([-10, -5]);
    expect(parallaxOffset(preview.content.layers[1], 100, 50)).toEqual([-70, -20]);
  });

  test.each(["../outside.png", "/outside.png", "https://example.com/a.png", "layers/%2e%2e/a.png", "layers\\outside.png"])("refuses unsafe layer ref %s", (assetRef) => {
    const value = parallaxFixture();
    value.layers[0].asset_ref = assetRef;
    expect(() => parseArtifactPreview(value, "preview")).toThrow("portable run-local");
  });

  test("refuses invalid geometry, nonfinite motion, and duplicate layers", () => {
    const value = parallaxFixture();
    expect(() => parseArtifactPreview({ ...value, canvas: { width: 0, height: 720 } }, "preview")).toThrow("canvas.width");
    expect(() => parseArtifactPreview({ ...value, layers: [] }, "preview")).toThrow("layers");
    expect(() => parseArtifactPreview({ ...value, layers: [value.layers[0], value.layers[0]] }, "preview")).toThrow("unique");
    value.layers[0].parallax = Infinity;
    expect(() => parseArtifactPreview(value, "preview")).toThrow("finite");
  });

  test("unknown preview kind uses ordinary artifact fallback; malformed envelope fails", () => {
    expect(parseArtifactPreview({ kind: "user-owned-volume-v1", dimensions: [1, 2, 3] }, "preview")).toEqual({ supported: false, kind: "user-owned-volume-v1" });
    expect(() => parseArtifactPreview({ canvas: {} }, "preview")).toThrow("kind");
    expect(() => parseArtifactPreview([], "preview")).toThrow("object");
  });

  test.each([0, 17, 64, 1.5])("historical strip contract still refuses %s frames", (count) => {
    expect(() => parseLegacyMotion({ frame_count: count }, "motion")).toThrow("frame_count");
  });

  test("retains legacy playback fields and refuses nonpositive speed", () => {
    expect(parseLegacyMotion({ frame_count: 4, mode: "once", canonical_frame_indices: [0, 2], frames_per_second: 8 }, "motion")).toEqual({ frameCount: 4, mode: "once", canonicalFrameIndices: [0, 2], framesPerSecond: 8 });
    expect(() => parseLegacyMotion({ frame_count: 4, frames_per_second: 0 }, "motion")).toThrow("positive");
  });
});
