import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import {
  executionViewFixture,
  unfinishedExecutionViewFixture,
} from "@/lib/shell/execution-view.fixture";
import { runDirFor } from "@/lib/shell/runs";
import RunsPage from "./page";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

async function writeRun(tag: string, document: Record<string, unknown>): Promise<void> {
  const runDir = runDirFor(tag);
  cleanup.push(runDir);
  await mkdir(runDir, { recursive: true });
  await writeFile(path.join(runDir, "execution-view.json"), JSON.stringify(document), "utf8");
}

describe("runs list route", () => {
  test("lists runs that carry a view with their result badge and detail links", async () => {
    const okTag = `runs-list-ok-${process.pid}`;
    const runningTag = `runs-list-running-${process.pid}`;
    const abandonedTag = `runs-list-abandoned-${process.pid}`;
    const staleTag = `runs-list-stale-${process.pid}`;
    await writeRun(okTag, executionViewFixture());
    await writeRun(
      runningTag,
      unfinishedExecutionViewFixture(new Date().toISOString()),
    );
    // Started three days ago and never finished: this is the case that used to
    // claim to be in flight.
    await writeRun(
      abandonedTag,
      unfinishedExecutionViewFixture(new Date(Date.now() - 3 * 86_400_000).toISOString()),
    );
    await writeRun(staleTag, { ...executionViewFixture(), schema_version: 99 });

    const markup = renderToStaticMarkup(await RunsPage());

    expect(markup).toContain(`href="/runs/${okTag}"`);
    expect(markup).toContain(`href="/runs/${runningTag}"`);
    expect(markup).toContain(`href="/runs/${abandonedTag}"`);
    expect(markup).toContain(">ok<");
    expect(markup).toContain(">running<");
    expect(markup).toContain(">interrupted<");
    expect(markup).not.toContain("in flight");
    // A stale document is listed as needing a re-export, not hidden.
    expect(markup).toContain(`href="/runs/${staleTag}"`);
    expect(markup).toContain("re-export");
  });
});
