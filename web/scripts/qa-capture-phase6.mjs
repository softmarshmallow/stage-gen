#!/usr/bin/env node
// Phase 6 QA: capture screenshots from running scene via CDP/headless.
// Uses puppeteer-core if available, else falls back to a no-op message.
//
// Usage: node web/scripts/qa-capture-phase6.mjs <out-dir>
//
// Strategy: navigate to the play page, wait for window.__sceneReady,
// take pairs/triples of screenshots at known camera scroll positions
// for TC-073 (seams), TC-076 (mob frames), and snapshots for the rest.

import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const OUT_DIR = process.argv[2] || './web/scripts/qa-screenshots/phase6-fresh';
const URL = 'http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2';

mkdirSync(OUT_DIR, { recursive: true });

let puppeteer;
try {
  puppeteer = (await import('puppeteer')).default;
} catch {
  try {
    puppeteer = (await import('puppeteer-core')).default;
  } catch {
    console.error('Neither puppeteer nor puppeteer-core available — install one or run via Preview MCP.');
    process.exit(2);
  }
}

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });

async function shot(name) {
  const file = path.join(OUT_DIR, name);
  await page.screenshot({ path: file, type: 'png', clip: { x: 0, y: 0, width: 1280, height: 720 } });
  return file;
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// TC-070 / TC-079 baseline
const probes = await page.evaluate(() => {
  const p = window.__sceneProbes; const out = {};
  for (const k of Object.keys(p)) { try { out[k] = typeof p[k] === 'function' ? p[k]() : p[k]; } catch (e) { out[k] = 'err:' + e.message; } }
  return out;
});
writeFileSync(path.join(OUT_DIR, 'probes.json'), JSON.stringify(probes, null, 2));

// TC-073 seam: capture three frames spaced over a parallax half-width while scrolling.
await shot('seam_a.png');
await sleep(1500);
await shot('seam_b.png');
await sleep(1500);
await shot('seam_c.png');

// TC-076 mob frame cycling.
await shot('mob_t0.png');
await sleep(220);
await shot('mob_t1.png');

// General snapshots.
await shot('overview.png');

await browser.close();
console.log('captures saved to', OUT_DIR);
