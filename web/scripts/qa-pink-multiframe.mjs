// TC-078 retry 2 verification — multi-frame pink-pixel measurement.
//
// Captures 12 frames spread across a full auto-pan cycle (~10s), counts
// pinkish pixels per frame, and reports MIN/AVG/MAX. Single-sample is
// not enough — the foreground parallax layer's worst pink-leak frame
// can be 10x its average (different x-positions expose different drift
// regions of the looped strip).
//
// Predicate matches qa-pink-recheck.mjs so numbers are comparable.
import puppeteer from 'puppeteer';
import { writeFileSync, mkdirSync } from 'node:fs';

const URL = 'http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2';
const FRAMES = 12;
const SPACING_MS = 900; // ~10.8s window — covers a full auto-pan cycle
const VIEWPORT = { width: 1280, height: 720 };

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport(VIEWPORT);
await page.setCacheEnabled(false);
await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });
// Hard-reload-ish: force texture re-decode by reload after sceneReady fires once.
await page.reload({ waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });
await new Promise((r) => setTimeout(r, 1500));

const sample = () => page.evaluate(() => new Promise((resolve) => {
  const c = document.querySelector('canvas');
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const tmp = document.createElement('canvas');
      tmp.width = c.width;
      tmp.height = c.height;
      const ctx = tmp.getContext('2d');
      ctx.drawImage(c, 0, 0);
      const data = ctx.getImageData(0, 0, c.width, c.height).data;
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i + 1], b = data[i + 2];
        if (r > 180 && b > 130 && g < 150 && (r - g) > 50 && (b - g) > 30) count++;
      }
      const total = c.width * c.height;
      resolve({ count, total, ratio: count / total });
    });
  });
}));

const results = [];
for (let i = 0; i < FRAMES; i++) {
  const r = await sample();
  results.push(r);
  process.stderr.write(`  frame ${i + 1}/${FRAMES}: pink=${r.count} (${(r.ratio * 100).toFixed(3)}%)\n`);
  if (i < FRAMES - 1) await new Promise((r) => setTimeout(r, SPACING_MS));
}

const counts = results.map((r) => r.count);
const summary = {
  url: URL,
  frames: FRAMES,
  spacingMs: SPACING_MS,
  total: results[0].total,
  min: Math.min(...counts),
  max: Math.max(...counts),
  avg: Math.round(counts.reduce((a, b) => a + b, 0) / counts.length),
  maxRatio: Math.max(...counts) / results[0].total,
  perFrame: counts,
};

console.log(JSON.stringify(summary, null, 2));
mkdirSync('./web/scripts/qa-screenshots/phase6-fresh', { recursive: true });
writeFileSync(
  './web/scripts/qa-screenshots/phase6-fresh/pink_multiframe.json',
  JSON.stringify(summary, null, 2),
);
await browser.close();
