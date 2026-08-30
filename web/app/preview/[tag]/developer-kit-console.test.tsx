import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { GAMEPLAY_AUTOMATION_MODE } from "@/lib/sideview-platformer/automation";
import type { DeveloperKit } from "@/lib/sideview-platformer/developer-kit";
import { runDirFor } from "@/lib/shell/runs";
import PreviewPage from "./page";
import { DeveloperKitBar } from "./PreviewCanvas";

const MELEE: DeveloperKit = { weaponClass: "melee_dps_v1", projectileId: null };
const RANGED: DeveloperKit = { weaponClass: "ranged_dps_v1", projectileId: "paperwing_dart" };

function bar(active: DeveloperKit | null): string {
  return renderToStaticMarkup(
    <DeveloperKitBar kits={[MELEE, RANGED]} active={active} onSelect={() => {}} />,
  );
}

describe("the developer kit bar", () => {
  test("renders a button per kit, not a link", () => {
    // The switch acts on the running scene. A link would navigate, and navigating throws away the
    // map, the level and the position that made the comparison worth making.
    const markup = bar(null);

    expect(markup).toContain('data-testid="developer-kit-option-melee_dps_v1"');
    expect(markup).toContain('data-testid="developer-kit-option-ranged_dps_v1:paperwing_dart"');
    expect(markup).toContain("<button");
    expect(markup).not.toContain("<a ");
    expect(markup).not.toContain("href");
  });

  test("the package's own kit is marked, and is the one selected by default", () => {
    const markup = bar(null);

    expect(markup).toContain("·authored");
    expect(markup).toContain("as published");
    expect(markup).toMatch(/melee_dps_v1"[^>]*aria-pressed="true"/);
  });

  test("an override moves the pressed control and says so in words", () => {
    const markup = bar(RANGED);

    expect(markup).toMatch(/ranged_dps_v1:paperwing_dart"[^>]*aria-pressed="true"/);
    expect(markup).toContain("developer override — not what this run published");
    expect(markup).not.toContain("as published");
  });

  test("a throwing kit names the round it throws", () => {
    // Two throwing kits differ only by their round, so the round is what tells them apart.
    expect(bar(null)).toContain("ranged_dps_v1 (paperwing_dart)");
  });
});

// The console is client-rendered from what the running scene reports, so the server markup carries
// none of it. What is still worth pinning on the server is the property that matters most: a
// fixed-frame capture shell must stay exactly what it was.

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

describe("the preview shell", () => {
  test("renders no kit console on the server, in either shell", async () => {
    process.env.STAGE_GEN_GAMEPLAY_AUTOMATION = "1";
    const tag = `kit-console-server-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify({ schema_version: 10, kind: "prepared-game-runtime-v10" }),
      "utf8",
    );

    const ordinary = renderToStaticMarkup(
      await PreviewPage({
        params: Promise.resolve({ tag }),
        searchParams: Promise.resolve({}),
      }),
    );
    const automation = renderToStaticMarkup(
      await PreviewPage({
        params: Promise.resolve({ tag }),
        searchParams: Promise.resolve({ automation: GAMEPLAY_AUTOMATION_MODE }),
      }),
    );

    expect(ordinary).not.toContain("developer-kit-console");
    expect(ordinary).toContain("preview-transparency-mode");
    // The capture shell is exactly the canvas and nothing else; the console never reaches it,
    // because a transcript digest carries no record of an override.
    expect(automation).toBe(
      '<main data-testid="gameplay-canvas-only-shell" style="width:1280px;height:720px;margin:0;padding:0;overflow:hidden"><div aria-label="optional scrolling-game preview" data-automation="gameplay-v2" style="width:1280px;height:720px;margin:0 auto;background:#000"></div></main>',
    );
  });
});
