import { describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { listRuns, readRunIdentity } from "./run-index";
import { runDirFor } from "./runs";

async function withRun(
  tag: string,
  files: Readonly<Record<string, unknown>>,
  body: () => Promise<void>,
): Promise<void> {
  const runDir = runDirFor(tag);
  await mkdir(runDir, { recursive: true });
  try {
    for (const [name, document] of Object.entries(files)) {
      await writeFile(
        path.join(runDir, name),
        typeof document === "string" ? document : JSON.stringify(document),
        "utf8",
      );
    }
    await body();
  } finally {
    await rm(runDir, { recursive: true, force: true });
  }
}

describe("the run index", () => {
  test("reads only the two fields that say what a run is", async () => {
    // The index deliberately does not parse the rest: a run's gameplay contract
    // belongs to the host that plays it (decision 0061).
    await withRun(
      "run-index-kind",
      {
        "manifest.json": {
          kind: "oblique-survival-manifest-v2",
          schema_version: 1,
          ground: { size_meters: 512 },
        },
      },
      async () => {
        const entry = await readRunIdentity("run-index-kind");
        expect(entry.document).toBe("manifest.json");
        expect(entry.kind).toBe("oblique-survival-manifest-v2");
        expect(entry.schemaVersion).toBe(1);
        expect(entry.hasExecutionView).toBe(false);
      },
    );
  });

  test("lists a run whose document declares no kind rather than hiding it", async () => {
    // A run an operator cannot identify is exactly the run they want to see.
    await withRun("run-index-anonymous", { "bundle.json": { note: "no kind" } }, async () => {
      const entry = await readRunIdentity("run-index-anonymous");
      expect(entry.document).toBe("bundle.json");
      expect(entry.kind).toBeNull();
      expect(entry.schemaVersion).toBeNull();
    });
  });

  test("does not throw on a document that is not JSON", async () => {
    await withRun("run-index-broken", { "case.json": "{ not json" }, async () => {
      const entry = await readRunIdentity("run-index-broken");
      expect(entry.document).toBe("case.json");
      expect(entry.kind).toBeNull();
    });
  });

  test("skips a directory that published neither a document nor a view", async () => {
    await withRun("run-index-empty", { "notes.txt": "scratch" }, async () => {
      const listed = await listRuns();
      expect(listed.some((entry) => entry.tag === "run-index-empty")).toBe(false);
      const entry = await readRunIdentity("run-index-empty");
      expect(entry.document).toBeNull();
    });
  });

  test("lists a run that carries a view but no document", async () => {
    // A run whose document was never written still has a plan worth reading.
    await withRun("run-index-viewonly", { "execution-view.json": { kind: "x" } }, async () => {
      const listed = await listRuns();
      const entry = listed.find((row) => row.tag === "run-index-viewonly");
      expect(entry).toBeDefined();
      expect(entry?.document).toBeNull();
      expect(entry?.hasExecutionView).toBe(true);
    });
  });

  test("prefers the manifest when a run carries more than one document", async () => {
    await withRun(
      "run-index-two",
      {
        "manifest.json": { kind: "first", schema_version: 2 },
        "bundle.json": { kind: "second", schema_version: 8 },
      },
      async () => {
        const entry = await readRunIdentity("run-index-two");
        expect(entry.document).toBe("manifest.json");
        expect(entry.kind).toBe("first");
      },
    );
  });
});
