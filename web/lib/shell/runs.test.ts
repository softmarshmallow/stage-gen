import { describe, expect, test } from "bun:test";
import path from "node:path";
import { artifactPathFor, isSafeRunTag, runDirFor } from "./runs";

describe("run directory boundary", () => {
  test("accepts generated tags and rejects traversal or encoded separators", () => {
    expect(isSafeRunTag("rain-dark-stone-0123abcd")).toBe(true);
    expect(isSafeRunTag("Explicit_Tag.v3")).toBe(true);
    expect(isSafeRunTag("a")).toBe(true);
    expect(isSafeRunTag("a".repeat(128))).toBe(true);
    expect(isSafeRunTag("a".repeat(129))).toBe(false);

    for (const tag of [
      "",
      ".",
      "..",
      "../escape",
      "safe/escape",
      "safe\\escape",
      "%2e%2e",
      "safe%2Fescape",
      "safe%252Fescape",
    ]) {
      expect(isSafeRunTag(tag)).toBe(false);
      expect(() => runDirFor(tag)).toThrow("invalid run tag");
    }
  });

  test("resolves portable nested artifacts inside the selected run", () => {
    const tag = "neutral-run-0123abcd";
    const runDir = runDirFor(tag);
    expect(path.dirname(artifactPathFor(tag, "manifest.json"))).toBe(runDir);
    expect(
      artifactPathFor(tag, "content/players/wayfarer/states/idle.png"),
    ).toBe(
      path.join(runDir, "content", "players", "wayfarer", "states", "idle.png"),
    );

    for (const name of [
      "",
      ".hidden",
      "..",
      "../secret",
      "nested\\asset.png",
      "asset%2Fsecret.png",
      "asset%252Fsecret.png",
    ]) {
      expect(() => artifactPathFor(tag, name)).toThrow("invalid artifact path");
    }
  });
});
