import { describe, expect, test } from "bun:test";
import { fxBlockFixture, parseFxBlock } from "./fx";

describe("parseFxBlock", () => {
  test("parses the published block into frozen runtime shapes", () => {
    const block = parseFxBlock(fxBlockFixture());
    expect(block.cutIn?.frame.maskPolygon).toHaveLength(4);
    expect(block.cutIn?.frame.asset).toBe("fx/cut_in/frame.png");
    expect(block.cutIn?.portraits[0]?.portraitId).toBe("stage_start");
    expect(block.moments[0]).toEqual({
      moment: "stage_start",
      effect: "cut_in",
      portraitId: "stage_start",
      choreography: "tear_reveal_v1",
    });
    expect(Object.isFrozen(block)).toBe(true);
    expect(Object.isFrozen(block.cutIn?.frame.maskPolygon)).toBe(true);
  });

  test("refuses a moment, effect, or choreography outside the closed vocabularies", () => {
    for (const [key, value] of [
      ["moment", "fever_start"],
      ["effect", "wipe"],
      ["choreography", "slam_v1"],
    ] as const) {
      const document = fxBlockFixture();
      (document.moments as Record<string, unknown>[])[0][key] = value;
      expect(() => parseFxBlock(document)).toThrow(`moments[0].${key} must be one of`);
    }
  });

  test("refuses a binding that names a portrait the block does not publish", () => {
    const document = fxBlockFixture();
    (document.moments as Record<string, unknown>[])[0].portrait_id = "fever";
    expect(() => parseFxBlock(document)).toThrow("does not publish");
    const bare = fxBlockFixture();
    bare.cut_in = null;
    expect(() => parseFxBlock(bare)).toThrow("does not publish");
  });

  test("refuses a mask polygon that cannot be drawn", () => {
    const document = fxBlockFixture();
    const cutIn = document.cut_in as Record<string, Record<string, unknown>>;
    cutIn.frame.mask_polygon = [[0, 0.3], [1, 0.3]];
    expect(() => parseFxBlock(document)).toThrow("at least three vertices");
    cutIn.frame.mask_polygon = [[0, 0.3], [1.2, 0.3], [1, 0.7]];
    expect(() => parseFxBlock(document)).toThrow("inside the unit canvas");
  });

  test("accepts a frame that publishes no outline at all", () => {
    // A shape no single outline describes publishes null rather than a polygon that
    // lies; the runtime clips with the plate's alpha and never reads it.
    const document = fxBlockFixture();
    const cutIn = document.cut_in as Record<string, Record<string, unknown>>;
    cutIn.frame.mask_polygon = null;
    expect(parseFxBlock(document).cutIn?.frame.maskPolygon).toBeNull();
  });

  test("refuses a portrait without a finite positive placement", () => {
    const document = fxBlockFixture();
    const cutIn = document.cut_in as Record<string, Record<string, unknown>[]>;
    cutIn.portraits[0].placement = { scale: 0, x: 0.5, y: 0.5 };
    expect(() => parseFxBlock(document)).toThrow("placement.scale must be positive");
    cutIn.portraits[0].placement = { scale: 0.4, x: Number.NaN, y: 0.5 };
    expect(() => parseFxBlock(document)).toThrow("placement.x must be a finite number");
    delete cutIn.portraits[0].placement;
    expect(() => parseFxBlock(document)).toThrow("placement must be an object");
    const block = parseFxBlock(fxBlockFixture());
    expect(block.cutIn?.portraits[0]?.placement).toEqual({ scale: 0.44, x: 0.5, y: 0.53 });
  });

  test("refuses a layout or alpha policy the runtime does not draw", () => {
    const document = fxBlockFixture();
    const cutIn = document.cut_in as Record<string, Record<string, unknown>>;
    cutIn.frame.layout = "cut_in_frame_2048_v1";
    expect(() => parseFxBlock(document)).toThrow("frame.layout must be one of");
  });
});
