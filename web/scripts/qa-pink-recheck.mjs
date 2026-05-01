import puppeteer from 'puppeteer';
import { writeFileSync } from 'node:fs';
const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto('http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2', { waitUntil: 'networkidle2' });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60000 });
await new Promise(r => setTimeout(r, 1500));

const result = await page.evaluate(() => {
  const c = document.querySelector('canvas');
  const tmp = document.createElement('canvas');
  tmp.width = c.width; tmp.height = c.height;
  const ctx = tmp.getContext('2d');
  ctx.drawImage(c, 0, 0);
  const data = ctx.getImageData(0, 0, c.width, c.height).data;
  // find all pixels where R+B significantly exceed G (any pinkish hue)
  let count = 0;
  const samples = [];
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i], g = data[i+1], b = data[i+2];
    if (r > 180 && b > 130 && g < 150 && (r - g) > 50 && (b - g) > 30) {
      count++;
      if (samples.length < 10 && Math.random() < 0.001) {
        const idx = i / 4;
        samples.push({ x: idx % c.width, y: Math.floor(idx / c.width), r, g, b });
      }
    }
  }
  return { count, total: c.width * c.height, ratio: count / (c.width * c.height), samples };
});
console.log(JSON.stringify(result, null, 2));
writeFileSync('./web/scripts/qa-screenshots/phase6-fresh/pink_recheck.json', JSON.stringify(result, null, 2));
await browser.close();
