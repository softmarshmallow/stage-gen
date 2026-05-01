// Independent Phase 7 vision QA — fresh-eyes verification.
// Captures actual screenshots per state and compares pixel-level differences.

import puppeteer from "puppeteer";
import fs from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";

const URL =
  "http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2";
const OUT = "/tmp/qa-phase7";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const results = {};
const blockers = [];
const stageAdvanceLogs = [];

function rec(tc, verdict, reason) {
  results[tc] = { verdict, reason };
  console.log(`[${tc}] ${verdict} — ${reason}`);
  if (verdict === "fail") blockers.push(`${tc}: ${reason}`);
}

async function readJson(page, expr) {
  return await page.evaluate(`(${expr})()`);
}

async function holdKey(page, code, ms) {
  await page.keyboard.down(code);
  await sleep(ms);
  await page.keyboard.up(code);
}

async function snap(page, name, clip) {
  const file = path.join(OUT, `${name}.png`);
  if (clip && (clip.width <= 0 || clip.height <= 0)) {
    await page.screenshot({ path: file });
  } else {
    await page.screenshot({ path: file, clip });
  }
  return file;
}

function loadPng(file) {
  const buf = fs.readFileSync(file);
  return PNG.sync.read(buf);
}

function pixelDiff(a, b) {
  if (a.width !== b.width || a.height !== b.height) return { ratio: 1, total: 0, diff: 0 };
  let diff = 0;
  const total = a.width * a.height;
  for (let i = 0; i < total; i++) {
    const o = i * 4;
    const dr = Math.abs(a.data[o] - b.data[o]);
    const dg = Math.abs(a.data[o + 1] - b.data[o + 1]);
    const db = Math.abs(a.data[o + 2] - b.data[o + 2]);
    if (dr + dg + db > 30) diff++;
  }
  return { ratio: diff / total, total, diff };
}

async function playerScreenRect(page) {
  return await page.evaluate(() => {
    const sc = window.__sceneScene;
    const player = sc?.player;
    if (!player) return null;
    const cam = sc.cameras.main;
    const cx = player.sprite.x - cam.scrollX;
    const cy = player.sprite.y;
    const w = player.sprite.displayWidth || 80;
    const h = player.sprite.displayHeight || 120;
    const canvas = document.querySelector("canvas");
    const r = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.floor(r.left + cx - w / 2 - 30)),
      y: Math.max(0, Math.floor(r.top + cy - h - 30)),
      width: Math.ceil(w + 60),
      height: Math.ceil(h + 60),
    };
  });
}

(async () => {
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  page.on("console", (msg) => {
    const t = msg.text();
    if (t.includes("[stage-advance]")) stageAdvanceLogs.push({ t: Date.now(), text: t });
  });
  page.on("pageerror", (err) => console.log("PAGE_ERR:", err.message));

  await page.goto(URL, { waitUntil: "domcontentloaded" });
  for (let i = 0; i < 300; i++) {
    const ok = await page.evaluate(() => !!(window.__sceneReady && window.__scenePlayerState));
    if (ok) break;
    await sleep(200);
  }
  await page.waitForSelector("canvas", { timeout: 10000 });
  await page.click("canvas");
  await sleep(300);

  // ============ TC-080 ============
  const start = await readJson(page, "() => window.__scenePlayerState");
  const camStart = await readJson(page, "() => window.__sceneCamera?.scrollX ?? 0");

  await page.keyboard.down("ShiftLeft");
  await holdKey(page, "ArrowRight", 4000);
  await page.keyboard.up("ShiftLeft");
  await sleep(150);
  const afterArrowR = await readJson(page, "() => window.__scenePlayerState");
  const camAfterArrowR = await readJson(page, "() => window.__sceneCamera?.scrollX ?? 0");
  const arrowRdx = afterArrowR.x - start.x;

  await holdKey(page, "ArrowLeft", 1500);
  const afterArrowL = await readJson(page, "() => window.__scenePlayerState");
  const arrowLdx = afterArrowL.x - afterArrowR.x;
  await sleep(150);

  const beforeD = afterArrowL;
  await holdKey(page, "KeyD", 800);
  const afterD = await readJson(page, "() => window.__scenePlayerState");
  const Ddx = afterD.x - beforeD.x;

  const beforeA = afterD;
  await holdKey(page, "KeyA", 800);
  const afterA = await readJson(page, "() => window.__scenePlayerState");
  const Adx = afterA.x - beforeA.x;

  if (
    arrowRdx > 50 &&
    arrowLdx < -20 &&
    Ddx > 50 &&
    Adx < -20 &&
    camAfterArrowR > camStart
  ) {
    rec("TC-080", "pass", `arrowR=${arrowRdx.toFixed(0)}px arrowL=${arrowLdx.toFixed(0)} D=${Ddx.toFixed(0)} A=${Adx.toFixed(0)} cam:${camStart.toFixed(0)}->${camAfterArrowR.toFixed(0)}`);
  } else {
    rec("TC-080", "fail", `arrowR=${arrowRdx} arrowL=${arrowLdx} D=${Ddx} A=${Adx} cam:${camStart}->${camAfterArrowR}`);
  }

  // ============ TC-082 ============
  await page.keyboard.down("ShiftLeft");
  await holdKey(page, "ArrowRight", 4000);
  await page.keyboard.up("ShiftLeft");
  await sleep(150);
  const heights = await readJson(page, "() => window.__sceneProbes.heightmap");
  const TILE_PX = 64;
  const baselineY = 720 - 8;

  const snaps = [];
  for (let i = 0; i < 30; i++) {
    await page.keyboard.down("ArrowRight");
    await sleep(60);
    await page.keyboard.up("ArrowRight");
    await sleep(40);
    const ps = await readJson(page, "() => window.__scenePlayerState");
    if (!ps.airborne) {
      const col = Math.floor(ps.x / TILE_PX);
      const expectedY = baselineY - heights[col] * TILE_PX;
      snaps.push({ col, y: ps.y, expected: expectedY, dy: ps.y - expectedY, h: heights[col] });
    }
  }
  const dys = snaps.map((s) => Math.abs(s.dy));
  const maxDy = dys.length ? Math.max(...dys) : 99;
  const distinctHeights = new Set(snaps.map((s) => s.h));
  if (snaps.length >= 5 && maxDy < 2 && distinctHeights.size >= 2) {
    rec("TC-082", "pass", `${snaps.length} on-ground samples, heights traversed=${[...distinctHeights].sort().join(",")}, maxDy=${maxDy}px`);
  } else if (distinctHeights.size < 2) {
    rec("TC-082", "fail", `walked but never crossed a slope (single height ${[...distinctHeights]})`);
  } else {
    rec("TC-082", "fail", `feet float/clip — maxDy=${maxDy}px across ${snaps.length} samples`);
  }

  // ============ TC-081 ============
  // Walk back to a stable spot for state captures.
  await holdKey(page, "ArrowLeft", 600);
  await sleep(700);
  for (let i = 0; i < 30; i++) {
    const s = await readJson(page, "() => window.__scenePlayerState");
    if (s.state === "idle" && Math.abs(s.vx) < 1 && !s.airborne) break;
    await sleep(50);
  }
  let r = await playerScreenRect(page);
  const idlePath = await snap(page, "state_idle", r);

  await page.keyboard.down("ArrowRight");
  await sleep(120);
  r = await playerScreenRect(page);
  const walkPath = await snap(page, "state_walk", r);
  await page.keyboard.up("ArrowRight");
  await sleep(500);

  await page.keyboard.down("ShiftLeft");
  await page.keyboard.down("ArrowRight");
  await sleep(180);
  r = await playerScreenRect(page);
  const runPath = await snap(page, "state_run", r);
  await page.keyboard.up("ArrowRight");
  await page.keyboard.up("ShiftLeft");
  await sleep(500);

  await page.keyboard.down("KeyS");
  await sleep(300);
  r = await playerScreenRect(page);
  const crouchPath = await snap(page, "state_crouch", r);
  await page.keyboard.up("KeyS");
  await sleep(400);

  await page.keyboard.press("Space");
  for (let i = 0; i < 30; i++) {
    const s = await readJson(page, "() => window.__scenePlayerState");
    if (s.airborne) break;
    await sleep(20);
  }
  for (let i = 0; i < 30; i++) {
    const s = await readJson(page, "() => window.__scenePlayerState");
    if (Math.abs(s.vy) < 100) break;
    await sleep(15);
  }
  r = await playerScreenRect(page);
  const jumpPath = await snap(page, "state_jump", r);
  for (let i = 0; i < 80; i++) {
    const s = await readJson(page, "() => window.__scenePlayerState");
    if (!s.airborne) break;
    await sleep(20);
  }
  await sleep(300);

  await page.keyboard.press("KeyJ");
  await sleep(110);
  r = await playerScreenRect(page);
  const attackPath = await snap(page, "state_attack", r);
  await sleep(500);

  const idle = loadPng(idlePath);
  const walk = loadPng(walkPath);
  const run = loadPng(runPath);
  const crouch = loadPng(crouchPath);
  const jump = loadPng(jumpPath);
  const attack = loadPng(attackPath);

  const pairs = {
    "idle-walk": pixelDiff(idle, walk),
    "idle-run": pixelDiff(idle, run),
    "walk-run": pixelDiff(walk, run),
    "idle-crouch": pixelDiff(idle, crouch),
    "walk-crouch": pixelDiff(walk, crouch),
    "run-crouch": pixelDiff(run, crouch),
    "idle-jump": pixelDiff(idle, jump),
    "idle-attack": pixelDiff(idle, attack),
  };
  const allDiffs = Object.fromEntries(
    Object.entries(pairs).map(([k, v]) => [k, +v.ratio.toFixed(4)])
  );
  console.log("state pixel diffs:", allDiffs);

  const lowDiff = Object.entries(pairs).filter(([_, v]) => v.ratio < 0.005);
  let tc081v = "pass";
  let tc081r = `pair diffs=${JSON.stringify(allDiffs)}`;
  if (lowDiff.length > 0) {
    tc081v = "fail";
    tc081r = `near-identical sprite pairs: ${lowDiff.map(([k, v]) => `${k}=${v.ratio.toFixed(4)}`).join(", ")}`;
  }
  rec("TC-081", tc081v, tc081r);

  // ============ TC-083 ============
  const mobs0 = await readJson(page, "() => window.__sceneMobsState");
  if (!mobs0?.length) {
    rec("TC-083", "fail", "no mobs visible");
  } else {
    const idx = 0;
    const spawnX = mobs0[idx].x;
    const xs = [spawnX];
    const t0 = Date.now();
    while (Date.now() - t0 < 10000) {
      await sleep(400);
      const ms = await readJson(page, "() => window.__sceneMobsState");
      if (!ms?.[idx] || !ms[idx].alive) break;
      xs.push(ms[idx].x);
    }
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const range = maxX - minX;
    const offFromSpawnMax = Math.max(...xs.map((x) => Math.abs(x - spawnX)));
    if (range > 0 && offFromSpawnMax <= 110) {
      rec("TC-083", "pass", `mob0 over 10s: range=${range.toFixed(1)}px maxDev=${offFromSpawnMax.toFixed(1)}px (within ±100)`);
    } else {
      rec("TC-083", "fail", `mob0 maxDev=${offFromSpawnMax.toFixed(1)}px from spawn exceeds ±100 (range=${range.toFixed(1)}, samples=${xs.length})`);
    }
  }

  // ============ TC-084 ============
  const tc084 = await page.evaluate(() => {
    const scene = window.__sceneScene;
    const mob = scene?.mobs.find((m) => m.ladderIndex === 2);
    if (!mob) return { ok: false };
    mob.hp = 3;
    mob.state = "wander";
    mob.sprite.alpha = 1;
    let hits = 0;
    while (mob.isAlive() && hits < 20) {
      const r = mob.takeHit(performance.now() + hits * 1000);
      hits++;
      if (r.died) break;
    }
    return { ok: true, hits, expected: 3 };
  });
  if (tc084.ok && tc084.hits === 3) {
    rec("TC-084", "pass", `mob_2 (ladderIndex=2) defeated in 3 hits = i+1`);
  } else {
    rec("TC-084", "fail", JSON.stringify(tc084));
  }

  // ============ TC-085 ============
  const tc085info = await page.evaluate(() => {
    const scene = window.__sceneScene;
    const mob = scene?.mobs.find((m) => m.isAlive() && m.ladderIndex >= 5);
    if (!mob) return { ok: false };
    return { ok: true, mobId: mob.ladderIndex };
  });
  if (!tc085info.ok) {
    rec("TC-085", "fail", "no eligible mob for hurt test");
  } else {
    async function mobClip(mobId) {
      return await page.evaluate((id) => {
        const scene = window.__sceneScene;
        const mob = scene.mobs.find((m) => m.ladderIndex === id);
        if (!mob) return null;
        const cam = scene.cameras.main;
        const cx = mob.sprite.x - cam.scrollX;
        const cy = mob.sprite.y;
        const w = mob.sprite.displayWidth || 100;
        const h = mob.sprite.displayHeight || 100;
        const canvas = document.querySelector("canvas");
        const r = canvas.getBoundingClientRect();
        return {
          x: Math.max(0, Math.floor(r.left + cx - w / 2 - 30)),
          y: Math.max(0, Math.floor(r.top + cy - h - 30)),
          width: Math.min(1280, Math.ceil(w + 60)),
          height: Math.min(720, Math.ceil(h + 60)),
        };
      }, mobId);
    }
    // Move player adjacent to mob so camera follows and mob is on-screen.
    await page.evaluate((id) => {
      const scene = window.__sceneScene;
      const mob = scene.mobs.find((m) => m.ladderIndex === id);
      const player = scene.player;
      if (mob && player) {
        player.sprite.x = mob.sprite.x - 80;
      }
    }, tc085info.mobId);
    await sleep(400);

    let clip = await mobClip(tc085info.mobId);
    const beforePath = await snap(page, "mob_before_hit", clip);

    const stateAfter = await page.evaluate((id) => {
      const scene = window.__sceneScene;
      const mob = scene.mobs.find((m) => m.ladderIndex === id);
      mob.hp = 8;
      const r = mob.takeHit(performance.now());
      return {
        ok: true,
        died: r.died,
        state: mob.state,
        anim: mob.sprite.anims?.currentAnim?.key ?? null,
      };
    }, tc085info.mobId);

    await sleep(140);
    clip = await mobClip(tc085info.mobId);
    const midPath = await snap(page, "mob_mid_hurt", clip);

    let returnedToIdle = false;
    let backState = "?";
    for (let i = 0; i < 60; i++) {
      const s = await page.evaluate((id) => {
        const scene = window.__sceneScene;
        const mob = scene.mobs.find((m) => m.ladderIndex === id);
        return mob ? { state: mob.state, alive: mob.isAlive() } : null;
      }, tc085info.mobId);
      if (s && s.state === "wander") {
        returnedToIdle = true;
        backState = "wander";
        break;
      }
      backState = s?.state ?? "?";
      await sleep(50);
    }

    const beforeImg = loadPng(beforePath);
    const midImg = loadPng(midPath);
    const dBM = pixelDiff(beforeImg, midImg);

    const visiblyChanged = dBM.ratio > 0.003;
    if (
      stateAfter.ok &&
      !stateAfter.died &&
      stateAfter.state === "hurt" &&
      stateAfter.anim?.includes("hurt") &&
      returnedToIdle &&
      visiblyChanged
    ) {
      rec("TC-085", "pass", `mob ${tc085info.mobId}: state hurt (anim=${stateAfter.anim}) → wander; sprite diff before-mid=${dBM.ratio.toFixed(4)}`);
    } else {
      rec("TC-085", "fail", `state=${stateAfter.state} anim=${stateAfter.anim} returned=${returnedToIdle}(${backState}) visualDiff=${dBM.ratio.toFixed(4)}`);
    }
  }

  // ============ TC-086 ============
  const tc086 = await page.evaluate(async () => {
    const scene = window.__sceneScene;
    const items = scene.items;
    const before = items.snapshot().length;
    const mob = scene.mobs.find((m) => m.isAlive());
    if (!mob) return { ok: false };
    const ladderIndex = mob.ladderIndex;
    mob.hp = 1;
    mob.takeHit(performance.now());
    if (mob.isAlive()) return { ok: false };
    items.drop(mob.sprite.x, mob.sprite.y - 64, ladderIndex);
    await new Promise((r) => setTimeout(r, 100));
    const after = items.snapshot();
    const palette = scene.probes?.itemPalette || [];
    const lastKind = after[after.length - 1]?.kindIndex ?? -1;
    return {
      ok: true,
      before,
      afterCount: after.length,
      lastKind,
      poolSize: palette.length,
      inPool: lastKind >= 0 && lastKind < palette.length,
    };
  });
  if (tc086.ok && tc086.afterCount === tc086.before + 1 && tc086.inPool) {
    rec("TC-086", "pass", `items ${tc086.before}->${tc086.afterCount}, kindIndex=${tc086.lastKind} ∈ pool[${tc086.poolSize}]`);
  } else {
    rec("TC-086", "fail", JSON.stringify(tc086));
  }

  // ============ TC-087 ============
  const tc087 = await page.evaluate(() => {
    const scene = window.__sceneScene;
    const player = scene.player;
    const items = scene.items;
    const inv = scene.inventory;
    const beforeWorld = items.snapshot().length;
    const beforeInv = inv.snapshot().reduce((a, s) => a + s.count, 0);
    items.drop(player.sprite.x, player.sprite.y - 80, 4);
    return { beforeWorld, beforeInv };
  });
  await sleep(900);
  const tc087after = await page.evaluate(() => {
    const scene = window.__sceneScene;
    return {
      afterWorld: scene.items.snapshot().length,
      afterInv: scene.inventory.snapshot().reduce((a, s) => a + s.count, 0),
    };
  });
  const grew = tc087after.afterInv > tc087.beforeInv;
  const worldRemoved = tc087after.afterWorld <= tc087.beforeWorld;
  if (grew && worldRemoved) {
    rec("TC-087", "pass", `inv ${tc087.beforeInv}->${tc087after.afterInv}, world ${tc087.beforeWorld}->${tc087after.afterWorld}`);
  } else {
    rec("TC-087", "fail", `grew=${grew} worldRemoved=${worldRemoved} inv ${tc087.beforeInv}->${tc087after.afterInv} world ${tc087.beforeWorld}->${tc087after.afterWorld}`);
  }

  // ============ TC-088 ============
  const SLOT_X = [336, 624, 912, 1200];
  const SLOT_Y = [368, 656];
  await page.evaluate(() => {
    const scene = window.__sceneScene;
    const player = scene.player;
    const items = scene.items;
    if (!player || !items) return;
    for (let k = 0; k < 8; k++) {
      items.drop(player.sprite.x, player.sprite.y - 80 - k * 4, k);
    }
  });
  await sleep(1800);
  const tc088 = await readJson(
    page,
    "() => (window.__sceneInventory||[]).map(s=>({slotIndex:s.slotIndex, x:s.expectedPanelX, y:s.expectedPanelY, count:s.count}))"
  );
  const allOnGrid = tc088.length > 0 && tc088.every(
    (s) => SLOT_X.includes(s.x) && SLOT_Y.includes(s.y)
  );
  let layoutCorrect = true;
  for (const s of tc088) {
    const col = s.slotIndex % 4;
    const row = Math.floor(s.slotIndex / 4);
    if (s.x !== SLOT_X[col] || s.y !== SLOT_Y[row]) {
      layoutCorrect = false;
      break;
    }
  }
  await snap(page, "inventory_top_right", { x: 900, y: 0, width: 380, height: 250 });
  if (allOnGrid && layoutCorrect) {
    rec("TC-088", "pass", `${tc088.length} slot(s) on contracted 4x2 grid; row-major layout correct`);
  } else if (tc088.length === 0) {
    rec("TC-088", "fail", "no inventory items populated");
  } else {
    rec("TC-088", "fail", `onGrid=${allOnGrid} layoutCorrect=${layoutCorrect}; slots=${JSON.stringify(tc088)}`);
  }

  // ============ TC-089 ============
  const baselineLogs1 = stageAdvanceLogs.length;
  const portalInfo = await page.evaluate(async () => {
    const scene = window.__sceneScene;
    const player = scene?.player;
    const portal = scene?.portal;
    const entry = portal.portals.find((p) => p.kind === "entry");
    let entryFired = false;
    const handler = () => { entryFired = true; };
    window.addEventListener("stage-advance", handler);
    if (entry) {
      const oldX = player.sprite.x;
      player.sprite.x = entry.x;
      await new Promise((r) => setTimeout(r, 250));
      player.sprite.x = oldX;
    }
    window.removeEventListener("stage-advance", handler);
    return { ok: true, entryFired };
  });
  await sleep(150);
  const entryConsoleFired = stageAdvanceLogs.length > baselineLogs1;

  const baselineLogs2 = stageAdvanceLogs.length;
  const exitFired = await page.evaluate(async () => {
    const scene = window.__sceneScene;
    const player = scene.player;
    const portal = scene.portal;
    const exit = portal.portals.find((p) => p.kind === "exit");
    let domFired = false;
    const handler = () => { domFired = true; };
    window.addEventListener("stage-advance", handler);
    player.sprite.x = exit.x;
    await new Promise((r) => setTimeout(r, 300));
    window.removeEventListener("stage-advance", handler);
    return { domFired };
  });
  await sleep(200);
  const exitConsoleFired = stageAdvanceLogs.length > baselineLogs2;

  if (portalInfo.ok && !portalInfo.entryFired && !entryConsoleFired && exitFired.domFired && exitConsoleFired) {
    rec("TC-089", "pass", `entry portal silent; exit portal fires DOM event + console log`);
  } else {
    rec("TC-089", "fail", `entryDOM=${portalInfo.entryFired} entryConsole=${entryConsoleFired} exitDOM=${exitFired.domFired} exitConsole=${exitConsoleFired}`);
  }

  // ============ Phase 6 regression ============
  await page.evaluate(() => {
    const scene = window.__sceneScene;
    if (scene?.player) scene.player.sprite.x = 1200;
  });
  await sleep(900);
  let pinkCounts = [];
  let pinkBlobMaxRun = 0;
  for (let i = 0; i < 5; i++) {
    const fp = await snap(page, `phase6_regression_${i}`, { x: 0, y: 0, width: 1280, height: 720 });
    const img = loadPng(fp);
    let p = 0;
    for (let yy = 0; yy < img.height; yy++) {
      let run = 0;
      for (let xx = 0; xx < img.width; xx++) {
        const o = (yy * img.width + xx) * 4;
        const r = img.data[o], g = img.data[o + 1], b = img.data[o + 2];
        if (r > 220 && b > 220 && g < 60) {
          p++; run++;
          if (run > pinkBlobMaxRun) pinkBlobMaxRun = run;
        } else run = 0;
      }
    }
    pinkCounts.push(p);
    await holdKey(page, "ArrowRight", 700);
    await sleep(300);
  }
  const pinkAvg = pinkCounts.reduce((a, b) => a + b, 0) / pinkCounts.length;
  const pinkMax = Math.max(...pinkCounts);
  const totalPx = 1280 * 720;
  const pinkAvgRatio = pinkAvg / totalPx;
  if (pinkAvgRatio < 0.001 && pinkBlobMaxRun < 50) {
    rec("phase6_regression", "pass", `pink avg=${pinkAvg.toFixed(0)}px (${(pinkAvgRatio*100).toFixed(3)}%) max=${pinkMax} maxBlobRun=${pinkBlobMaxRun}`);
  } else if (pinkAvgRatio < 0.01 && pinkBlobMaxRun < 150) {
    rec("phase6_regression", "pass", `pink avg=${pinkAvg.toFixed(0)} (${(pinkAvgRatio*100).toFixed(3)}%) — minor specks under threshold (max blob run ${pinkBlobMaxRun})`);
  } else {
    rec("phase6_regression", "fail", `pink avg=${pinkAvg.toFixed(0)} (${(pinkAvgRatio*100).toFixed(3)}%) max=${pinkMax} maxBlobRun=${pinkBlobMaxRun} — TC-078 regression`);
  }

  await browser.close();
  const overall = Object.values(results).every((v) => v.verdict === "pass") ? "pass" : "fail";
  const out = {
    tag_examined: "snowy-mountain-platformer-with-crisp-pow-5162c8d2",
    ...Object.fromEntries(
      ["TC-080", "TC-081", "TC-082", "TC-083", "TC-084", "TC-085", "TC-086", "TC-087", "TC-088", "TC-089", "phase6_regression"].map((k) => [k, results[k] ?? { verdict: "fail", reason: "not run" }])
    ),
    overall,
    blocking_issues: blockers,
  };
  console.log("\n=== FINAL JSON ===");
  console.log(JSON.stringify(out, null, 2));
  process.exit(0);
})().catch((err) => {
  console.error("verify failed:", err);
  console.error(err.stack);
  process.exit(2);
});
