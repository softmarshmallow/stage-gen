import puppeteer from "puppeteer";
const URL = "http://localhost:3000/play/snowy-mountain-platformer-with-crisp-pow-5162c8d2";
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
await page.goto(URL, { waitUntil: "domcontentloaded" });
for (let i=0;i<300;i++){const ok=await page.evaluate(()=>!!(window.__sceneReady && window.__sceneMobsState));if(ok)break;await sleep(200);}
await sleep(500);
// Dump actual spawnX from internal state.
const info = await page.evaluate(() => {
  const scene = window.__sceneScene;
  const m = scene.mobs[0];
  return {
    spawnX: m["spawnX"],
    wanderMin: m["wanderMin"],
    wanderMax: m["wanderMax"],
    currentX: m.sprite.x,
    spawnCol: m["opts"]?.spawnCol,
    ladderIndex: m.ladderIndex,
  };
});
console.log("mob0 internals:", info);
// Now sample x for 12s.
const xs = [];
const t0 = Date.now();
while (Date.now() - t0 < 12000) {
  await sleep(200);
  const x = await page.evaluate(() => window.__sceneScene.mobs[0].sprite.x);
  xs.push(x);
}
const minX = Math.min(...xs), maxX = Math.max(...xs);
console.log(`samples=${xs.length} min=${minX.toFixed(1)} max=${maxX.toFixed(1)} range=${(maxX-minX).toFixed(1)}`);
console.log(`devFromSpawn min=${(info.spawnX - minX).toFixed(1)} max=${(maxX - info.spawnX).toFixed(1)}`);
console.log(`bound respected: minX>=${info.wanderMin} (${minX>=info.wanderMin-1}) maxX<=${info.wanderMax} (${maxX<=info.wanderMax+1})`);
await browser.close();
