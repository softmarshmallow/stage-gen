import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";
import sharp from "sharp";
import { normalizeImageBytes } from "../recipes/scrolling-preview/src/ai/normalize-image.ts";

describe("scrolling-preview contract normalization", () => {
  test("deterministically converts noncontract provider dimensions", async () => {
    const source = new Uint8Array(
      await sharp({
        create: { width: 7, height: 5, channels: 4, background: "#8844ccff" },
      })
        .png()
        .toBuffer(),
    );

    const first = await normalizeImageBytes(source, { width: 12, height: 8 });
    const second = await normalizeImageBytes(source, { width: 12, height: 8 });
    const metadata = await sharp(Buffer.from(first.bytes)).metadata();

    expect(metadata.width).toBe(12);
    expect(metadata.height).toBe(8);
    expect(first.bytes).toEqual(second.bytes);
    expect(first.record).toEqual(second.record);
    expect(first.record.source).toMatchObject({ width: 7, height: 5 });
    expect(first.record.output.sha256).toBe(
      createHash("sha256").update(first.bytes).digest("hex"),
    );
    expect(first.record.tool.name).toBe("sharp");
    expect(first.record.tool.version).toBeTruthy();
  });
});
