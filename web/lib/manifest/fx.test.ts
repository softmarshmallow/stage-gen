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

  test("refuses a layout or alpha policy the runtime does not draw", () => {
    const document = fxBlockFixture();
    const cutIn = document.cut_in as Record<string, Record<string, unknown>>;
    cutIn.frame.layout = "cut_in_frame_2048_v1";
    expect(() => parseFxBlock(document)).toThrow("frame.layout must be one of");
  });
});
