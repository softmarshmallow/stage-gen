import { describe, expect, test } from "bun:test";
import {
  DEFAULT_DIALOGUE_OVERLAY_TAG,
  parseDialogueOverlayArgs,
} from "./dialogue-overlay";

describe("production dialogue overlay verifier options", () => {
  test("defaults to the generated Elowen village run", () => {
    expect(parseDialogueOverlayArgs([])).toEqual({
      tag: DEFAULT_DIALOGUE_OVERLAY_TAG,
      timeoutMs: 120_000,
    });
  });

  test("accepts one safe run tag and bounded timeout", () => {
    expect(
      parseDialogueOverlayArgs([
        "--tag",
        "storybook-village-0123abcd",
        "--timeout-ms",
        "180000",
      ]),
    ).toEqual({ tag: "storybook-village-0123abcd", timeoutMs: 180_000 });
  });

  test("rejects unsafe, duplicate, unknown, and unbounded options", () => {
    for (const args of [
      ["--tag", "../village"],
      ["--tag", "nested/village"],
      ["--tag", "village", "--tag", "other"],
      ["--timeout-ms", "9999"],
      ["--timeout-ms", "600001"],
      ["--timeout-ms", "12.5"],
      ["--output", "capture.png"],
    ]) {
      expect(() => parseDialogueOverlayArgs(args)).toThrow();
    }
  });
});
