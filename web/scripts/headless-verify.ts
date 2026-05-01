// Phase 6 headless verification.
//
// Boots the local dev server (assumed running on :3000), opens
// /play/<TAG> in a headless Chromium via Playwright, and exercises the
// scene against TC-070..TC-079.
//
// Run: bun --cwd web run scripts/headless-verify.ts
// Requires: `bunx playwright install chromium` once.

import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const TAG = process.env.TAG ?? "snowy-mountain-platformer-with-crisp-pow-5162c8d2";
const BASE = process.env.BASE ?? "http://localhost:3000";
const OUT = resolve(import.meta.dirname, "verify-out");

mkdirSync(OUT, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();

  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push("pageerror: " + err.message));

  await page.goto(`${BASE}/play/${TAG}`, { waitUntil: "domcontentloaded" });

  // Wait for canvas to appear.
  await page.waitForSelector("canvas", { timeout: 15000 });
  // Wait for scene to mark itself ready.
  await page.waitForFunction(() => (window as any).__sceneReady === true, null, { timeout: 30000 });

  // ---- TC-070: zero console.error in first 3s after canvas appears ----
  await page.waitForTimeout(3000);
  const errors070 = [...consoleErrors];
  const probes = await page.evaluate(() => (window as any).__sceneProbes);
  console.log("TC-070 console.error count:", errors070.length);
  if (errors070.length) console.log(" errors:", errors070);

  // ---- TC-071: skybox does not scroll ----
  // Take a screenshot, scroll camera, take another, compare.
  const skyKey = probes?.parallaxAlphaProbe
    ? Object.values<any>(probes.parallaxAlphaProbe).find((p: any) => p.opaque)?.layerId
    : null;
  await page.evaluate(() => {
    // Disable auto-pan by simulating an arrow press? Easier: directly set scrollX.
    (window as any).__phaser_test = true;
  });
  // Capture before/after the scene-driven autoscroll has accumulated.
  const before = await page.screenshot({ clip: { x: 0, y: 0, width: 1280, height: 200 } });
  writeFileSync(`${OUT}/sky_before.png`, before);
  await page.waitForTimeout(2000);
  const after = await page.screenshot({ clip: { x: 0, y: 0, width: 1280, height: 200 } });
  writeFileSync(`${OUT}/sky_after.png`, after);

  // ---- TC-074: wide ground screenshot ----
  const ground = await page.screenshot({ fullPage: false });
  writeFileSync(`${OUT}/scene_full.png`, ground);

  // ---- TC-076: mob frame difference ----
  const mob1 = await page.screenshot({ fullPage: false });
  writeFileSync(`${OUT}/mob_t0.png`, mob1);
  await page.waitForTimeout(220);
  const mob2 = await page.screenshot({ fullPage: false });
  writeFileSync(`${OUT}/mob_t1.png`, mob2);

  // ---- TC-079: read fps over 30s ----
  console.log("TC-079: sampling fps for 30s ...");
  await page.waitForTimeout(30_000);
  const fps = await page.evaluate(() => (window as any).__sceneFps);
  console.log("TC-079 fps snapshot:", fps);

  // Final summary write
  const summary = {
    tag: TAG,
    consoleErrors: errors070,
    probesKeysCount: probes?.loadedAssetKeys?.length ?? 0,
    parallaxLayers: Object.keys(probes?.parallaxAlphaProbe ?? {}),
    foregroundLayers: probes?.foregroundLayers,
    heightmapLen: probes?.heightmap?.length,
    flatRunCount: probes?.flatRunCount,
    obstacleCount: probes?.obstacleCount,
    mobCount: probes?.mobCount,
    playerColumn: probes?.playerColumn,
    skyKey,
    fps,
  };
  writeFileSync(`${OUT}/summary.json`, JSON.stringify(summary, null, 2));
  console.log("verify summary:", summary);

  await browser.close();
  process.exit(errors070.length === 0 && (fps?.minOverWindow ?? 0) >= 30 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
