// TC-078 verification — pink-pixel count after the runtime layer chroma-key fix.
//
// IMPORTANT: Phaser uses preserveDrawingBuffer=false by default, so reading
// the WebGL canvas via getImageData returns zeros. Two-rAF trick is needed
// to read pixels mid-flush. We also pan a few frames so the foreground
// `near_fir_grass` layer is in view.
import puppeteer from 'puppeteer';
import { writeFileSync } from 'node:fs';

const URL = 'http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2';

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });
// Let auto-pan run a bit so the foreground layer renders various positions.
await new Promise((r) => setTimeout(r, 2500));

// Use the two-rAF trick to pull a frame just after a render, into a copy
// canvas where we can read pixels without preserveDrawingBuffer issues.
const result = await page.evaluate(() => new Promise((resolve) => {
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
      const samples = [];
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i + 1], b = data[i + 2];
        // Same predicate as before: any pinkish hue (R + B significantly above G).
        if (r > 180 && b > 130 && g < 150 && (r - g) > 50 && (b - g) > 30) {
          count++;
          if (samples.length < 10 && Math.random() < 0.001) {
            const idx = i / 4;
            samples.push({ x: idx % c.width, y: Math.floor(idx / c.width), r, g, b });
          }
        }
      }
      resolve({ count, total: c.width * c.height, ratio: count / (c.width * c.height), samples });
    });
  });
}));

console.log(JSON.stringify(result, null, 2));
writeFileSync('./web/scripts/qa-screenshots/phase6-fresh/pink_recheck.json', JSON.stringify(result, null, 2));
await browser.close();
