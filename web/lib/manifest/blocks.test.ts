import { describe, expect, test } from "bun:test";
import { parseBlockTable } from "./blocks";
import { parsePreparedRuntimeManifest, PREPARED_RUNTIME_BLOCKS } from "./prepared-manifest";
import { preparedRuntimeManifestFixture } from "@/lib/shell/prepared-runtime.fixture";
import { parseRunnerRuntimeManifest, RUNNER_BLOCKS } from "@/lib/sideview-runner/contract";
import { runnerManifestFixture } from "@/lib/sideview-runner/fixture";

describe("parseBlockTable", () => {
  test("accepts every expected block at its version and keeps unknown extras", () => {
    const table = parseBlockTable(
      { a: "a-block-v1", b: "b-block-v2", extra: "extra-block-v9" },
      { a: "a-block-v1", b: "b-block-v2" },
    );
    expect(table).toEqual({ a: "a-block-v1", b: "b-block-v2", extra: "extra-block-v9" });
    expect(Object.isFrozen(table)).toBe(true);
  });

  test("names the block whose version this build does not read", () => {
    expect(() =>
      parseBlockTable({ a: "a-block-v2" }, { a: "a-block-v1" }),
    ).toThrow('manifest block "a" is published as a-block-v2; this build reads a-block-v1');
  });

  test("refuses an absent block unless it is optional", () => {
    expect(() => parseBlockTable({}, { a: "a-block-v1" })).toThrow(
      'manifest block "a" is not published',
    );
    expect(parseBlockTable({}, { a: "a-block-v1" }, { optional: ["a"] })).toEqual({});
    expect(() =>
      parseBlockTable({ a: "a-block-v3" }, { a: "a-block-v1" }, { optional: ["a"] }),
    ).toThrow('manifest block "a" is published as a-block-v3');
  });

  test("refuses a manifest with no table at all", () => {
    expect(() => parseBlockTable(undefined, { a: "a-block-v1" })).toThrow(
      "manifest blocks table is missing",
    );
  });
});

describe("per-block refusal through the genre parsers", () => {
  test("the platformer refuses one moved block by name and accepts the fixture", () => {
    const manifest = preparedRuntimeManifestFixture();
    expect(parsePreparedRuntimeManifest(manifest).blocks).toEqual(PREPARED_RUNTIME_BLOCKS);
    const moved = { ...manifest, blocks: { ...PREPARED_RUNTIME_BLOCKS, maps: "platformer-maps-block-v2" } };
    expect(() => parsePreparedRuntimeManifest(moved)).toThrow(
      'manifest block "maps" is published as platformer-maps-block-v2; this build reads platformer-maps-block-v1',
    );
  });

  test("the runner refuses one moved block by name; fx may be absent", () => {
    const manifest = runnerManifestFixture();
    const parsed = parseRunnerRuntimeManifest(manifest);
    expect(parsed.blocks.ground).toBe(RUNNER_BLOCKS.ground);
    const { fx: _fx, ...withoutFx } = RUNNER_BLOCKS;
    expect(() => parseRunnerRuntimeManifest({ ...manifest, blocks: withoutFx })).not.toThrow();
    expect(() =>
      parseRunnerRuntimeManifest({ ...manifest, blocks: { ...RUNNER_BLOCKS, ground: "runner-ground-block-v2" } }),
    ).toThrow('manifest block "ground" is published as runner-ground-block-v2');
  });
});
