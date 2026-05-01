import puppeteer from 'puppeteer';

const URL = 'http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2';
const OUT = '/Users/universe/Desktop/stage-gen-ralph-setup/web/scripts/qa-screenshots/phase6-fresh/tc078-fresh-verify.png';

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60_000 });
await page.waitForFunction('window.__sceneReady === true', { timeout: 60_000 });
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: OUT, type: 'png' });
console.log(OUT);
await browser.close();
