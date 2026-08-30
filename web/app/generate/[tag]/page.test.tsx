import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { preparedRuntimeManifestFixture } from "@/lib/shell/prepared-runtime.fixture";
import { runDirFor } from "@/lib/shell/runs";
import GeneratePage from "./page";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(
    cleanup.splice(0).map((target) =>
      rm(target, { recursive: true, force: true }),
    ),
  );
});

describe("prepared asset explorer route", () => {
  test("renders a validated prepared manifest instead of the legacy live-run view", async () => {
    const tag = `prepared-assets-page-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify(preparedRuntimeManifestFixture()),
      "utf8",
    );

    const page = await GeneratePage({ params: Promise.resolve({ tag }) });
    const markup = renderToStaticMarkup(page);

    expect(markup).toContain("prepared asset explorer");
    expect(markup).toContain("9 closure artifacts · 8 assets · 1 provenance");
    expect(markup).toContain(`href="/preview/${tag}"`);
    expect(markup).toContain(
      `/api/assets/${tag}/content/player/concept.png`,
    );
    expect(markup).not.toContain("pipeline failed");
    expect(markup).not.toContain("waiting for pipeline output");
  });
});
