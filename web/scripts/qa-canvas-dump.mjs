#!/usr/bin/env node
import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const OUT_DIR = './web/scripts/qa-screenshots/phase6-fresh';
const URL = 'http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2';
mkdirSync(OUT_DIR, { recursive: true });

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// Phaser by default uses preserveDrawingBuffer=false, so canvas.toDataURL after
// a render will be blank. Use page.evaluate to grab pixels via a Phaser snapshot
// or by reading directly *during* the WebGL frame.
// Simplest: ask Phaser to take a snapshot.
async function dump(name) {
  // Try phaser snapshot via game probe.
  const dataUrl = await page.evaluate(() => new Promise((resolve) => {
    const game = window.__sceneProbes && window.__sceneProbes.game ? window.__sceneProbes.game() : null;
    // Fallback: replicate frame by reading from canvas with preserveDrawingBuffer trick
    const c = document.querySelector('canvas');
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        try { resolve(c.toDataURL('image/png')); } catch (e) { resolve(null); }
      });
    });
  }));
  if (!dataUrl || dataUrl.length < 200) return null;
  const buf = Buffer.from(dataUrl.split(',')[1], 'base64');
  writeFileSync(path.join(OUT_DIR, name), buf);
  return buf.length;
}

const r1 = await dump('canvas_dump_a.png');
await sleep(220);
const r2 = await dump('canvas_dump_b.png');
console.log('dump sizes:', r1, r2);

// Also do a broader "pinkish" sample across the canvas.
const sample = await page.evaluate(() => {
  const c = document.querySelector('canvas');
  const tmp = document.createElement('canvas');
  tmp.width = c.width; tmp.height = c.height;
  const ctx = tmp.getContext('2d');
  ctx.drawImage(c, 0, 0);
  const data = ctx.getImageData(0, 0, c.width, c.height).data;
  const buckets = { exactMagenta: 0, neonPink: 0, hotPink: 0, anyPink: 0, total: 0 };
  for (let i = 0; i < data.length; i += 4) {
    buckets.total++;
    const r = data[i], g = data[i+1], b = data[i+2];
    if (r === 255 && g === 0 && b === 255) buckets.exactMagenta++;
    if (r > 240 && g < 30 && b > 240) buckets.neonPink++;
    if (r > 200 && b > 180 && g < 100) buckets.hotPink++;
    if (r - g > 80 && b - g > 50) buckets.anyPink++;
  }
  return buckets;
});
writeFileSync(path.join(OUT_DIR, 'pink_buckets.json'), JSON.stringify(sample, null, 2));

await browser.close();
console.log(JSON.stringify(sample));
