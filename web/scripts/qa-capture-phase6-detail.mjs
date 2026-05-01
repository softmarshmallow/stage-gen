#!/usr/bin/env node
// Phase 6 detail capture: zoom and mob animation comparison.
import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const OUT_DIR = process.argv[2] || './web/scripts/qa-screenshots/phase6-fresh';
const URL = 'http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2';
mkdirSync(OUT_DIR, { recursive: true });

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });

// Pixel-sample the rendered canvas for residual magenta-ish hue.
const sample = await page.evaluate(() => {
  const c = document.querySelector('canvas');
  const tmp = document.createElement('canvas');
  tmp.width = c.width; tmp.height = c.height;
  const ctx = tmp.getContext('2d');
  ctx.drawImage(c, 0, 0);
  const data = ctx.getImageData(0, 0, c.width, c.height).data;
  let pinkish = 0; let total = 0;
  for (let i = 0; i < data.length; i += 4) {
    total++;
    const r = data[i], g = data[i+1], b = data[i+2];
    // residual magenta: high R, low G, high B
    if (r > 180 && b > 150 && g < 120 && r - g > 60) pinkish++;
  }
  return { pinkish, total, ratio: pinkish / total };
});
writeFileSync(path.join(OUT_DIR, 'pinkish_pixel_sample.json'), JSON.stringify(sample, null, 2));

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
async function shot(name) {
  await page.screenshot({ path: path.join(OUT_DIR, name), type: 'png', clip: { x: 0, y: 0, width: 1280, height: 720 } });
}

// Take 4 rapid captures 100ms apart for mob frame cycling clarity.
for (let i = 0; i < 4; i++) {
  await shot(`burst_${i}.png`);
  await sleep(100);
}

await browser.close();
console.log('detail saved');
