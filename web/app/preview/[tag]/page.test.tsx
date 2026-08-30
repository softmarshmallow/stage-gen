import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { GAMEPLAY_AUTOMATION_MODE } from "@/lib/sideview-platformer/automation";
import { preparedRuntimeManifestFixture } from "@/lib/shell/prepared-runtime.fixture";
import { runDirFor } from "@/lib/shell/runs";
import PreviewPage from "./page";

const originalAutomationFlag = process.env.STAGE_GEN_GAMEPLAY_AUTOMATION;
const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(
    cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })),
  );
  if (originalAutomationFlag === undefined) {
    delete process.env.STAGE_GEN_GAMEPLAY_AUTOMATION;
  } else {
    process.env.STAGE_GEN_GAMEPLAY_AUTOMATION = originalAutomationFlag;
  }
});

describe("preview route automation shell", () => {
  test("renders only the exact 1280x720 gameplay canvas shell", async () => {
    process.env.STAGE_GEN_GAMEPLAY_AUTOMATION = "1";
    const tag = `automation-shell-contract-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify(preparedRuntimeManifestFixture()),
      "utf8",
    );

    const page = await PreviewPage({
      params: Promise.resolve({ tag }),
      searchParams: Promise.resolve({ automation: GAMEPLAY_AUTOMATION_MODE }),
    });
    const markup = renderToStaticMarkup(page);

    expect(markup).toBe(
      '<main data-testid="gameplay-canvas-only-shell" style="width:1280px;height:720px;margin:0;padding:0;overflow:hidden"><div aria-label="optional scrolling-game preview" data-automation="gameplay-v2" style="width:1280px;height:720px;margin:0 auto;background:#000"></div></main>',
    );
    expect(markup).not.toContain("preview-transparency-mode");
    expect(markup).not.toContain("[ ◂ back ]");
    expect(markup).not.toContain("stage-gen / optional scrolling preview");
  });
});
