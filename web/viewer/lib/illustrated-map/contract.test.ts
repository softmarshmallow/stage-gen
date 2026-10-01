import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "bun:test";
import {
  imagePixelToMapCoordinate,
  parseIllustratedMapManifest,
  sortFeaturesByLabelPriority,
} from "./contract";

function fixture(): Record<string, any> {
  return JSON.parse(
    readFileSync(
      path.resolve(import.meta.dir, "../../public/demo/map/ashen-reaches.json"),
      "utf8",
    ),
  );
}

describe("illustrated map manifest", () => {
  test("parses the exact demo contract", () => {
    const parsed = parseIllustratedMapManifest(fixture());

    expect(parsed.kind).toBe("illustrated-map-manifest-v1");
    expect(parsed.coordinate_space).toEqual({
      kind: "image-pixel-v1",
      origin: "top_left",
      x_axis: "right",
      y_axis: "down",
      width: 1536,
      height: 1024,
    });
    expect(parsed.features).toHaveLength(11);
    expect(parsed.features[0].feature_id).toBe("frostglass-hold");
    expect(parsed.raster.media_type).toBe("image/png");
  });

  test("adapts top-left image pixels only at the renderer boundary", () => {
    expect(imagePixelToMapCoordinate([270, 96], 1024)).toEqual([270, 928]);
    expect(imagePixelToMapCoordinate([0, 1023], 1024)).toEqual([0, 1]);
  });

  test("sorts label collision priority without treating array order as meaning", () => {
    const parsed = parseIllustratedMapManifest(fixture());
    const sorted = [...parsed.features].sort(sortFeaturesByLabelPriority);

    expect(sorted[0].feature_id).toBe("hollow-crown");
    expect(sorted.at(-1)?.feature_id).toBe("needlewatch");
  });

  test("rejects unknown fields, duplicate IDs, unsafe paths, and out-of-bounds points", () => {
    const withUnknown = fixture();
    withUnknown.features[0].label.llm_confidence = 0.9;
    expect(() => parseIllustratedMapManifest(withUnknown)).toThrow("unknown field");

    const withDuplicate = fixture();
    withDuplicate.features[1].feature_id = withDuplicate.features[0].feature_id;
    expect(() => parseIllustratedMapManifest(withDuplicate)).toThrow(
      "feature_id values must be unique",
    );

    const withUnsafePath = fixture();
    withUnsafePath.raster.path = "../private.png";
    expect(() => parseIllustratedMapManifest(withUnsafePath)).toThrow(
      "portable relative POSIX path",
    );

    const outOfBounds = fixture();
    outOfBounds.features[0].geometry.coordinates = [1536, 20];
    expect(() => parseIllustratedMapManifest(outOfBounds)).toThrow(
      "point lies outside the source image",
    );
  });

  test("rejects dimension drift and malformed content digests", () => {
    const dimensionsDrifted = fixture();
    dimensionsDrifted.raster.width = 1500;
    expect(() => parseIllustratedMapManifest(dimensionsDrifted)).toThrow(
      "dimensions must match the coordinate space",
    );

    const badDigest = fixture();
    badDigest.raster.sha256 = "not-a-digest";
    expect(() => parseIllustratedMapManifest(badDigest)).toThrow("invalid format");
  });
});
