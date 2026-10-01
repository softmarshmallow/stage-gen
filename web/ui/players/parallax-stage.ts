// Player: the parallax stage: a map's layers and its ground under the page's tuning, with
// the walker on the map's own grid, the layer table and the game placement.
//
// Moved from the parallax stage section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-parallax-stage], with its config. Hooks inside it: [data-stage], [data-world],
// [data-layers], [data-map], [data-opt], [data-placement], [data-hint].

import type { Mount } from "./dom";
import {
  announce, byDepth, detailOf, layerTable, parallaxBand, syncTable, TUNINGS, tuneOf,
  type Band, type ParallaxLayer, type ParallaxMap, type StageConfig, type Stepped, type Tune,
} from "./parallax";

export const mount: Mount<StageConfig> = (root, cfg) => {
  const box = root as Stepped;
  const controller = new AbortController(), { signal } = controller;
  const [VW, VH] = cfg.view, walker = cfg.walker;
  const WALK = 1.4 * walker.unit, RUN = 3.2 * walker.unit, JUMP = 5.2 * walker.unit, FALL = 13 * walker.unit, EDGE = 180;
  const $ = <E extends Element = HTMLElement>(sel: string): E => box.querySelector<E>(sel)!;
  const stage = $("[data-stage]"), world = $("[data-world]"), rows = $("[data-layers]");
  const opt = { auto: true, flat: false, marks: false }, keys = new Set<string>(), hidden = new Set<string>();
  const st = { x: 0, feet: 0, vy: 0, grounded: true, face: 1, state: "idle", t: 0, jump: false };
  const me = "stage-" + Math.random();
  let map!: ParallaxMap, bands: Band[] = [], ground!: HTMLDivElement, body!: HTMLDivElement;
  Object.values(walker.states).forEach(s => { new Image().src = s.src; });

  // The map's own grid is the level: a cell is solid where it says 1, and every top edge is a
  // one-way platform. Below the grid is floor.
  const solid = (x: number, y: number): boolean => {
    const c = Math.floor(x / map.tile), r = Math.floor((y - map.ground.top) / map.tile);
    if (c < 0 || c >= map.grid[0].length || r < 0) return false;
    return r >= map.grid.length || map.grid[r][c] === "1";
  };
  const groundAt = (x: number): number => {
    const c = Math.floor(x / map.tile);
    let r = map.grid.length;
    while (r > 0 && map.grid[r - 1][c] === "1") r -= 1;
    return map.ground.top + r * map.tile;
  };
  const tune = (): void => { bands.forEach(b => b.place()); announce(map, me); };
  const load = (id: string): void => {
    map = cfg.maps.find(m => m.id === id)!;
    world.replaceChildren();
    const layers = map.layers.slice().sort(byDepth);
    bands = layers.filter(l => l.plane !== "foreground").map(l => parallaxBand(world, map, l, VW, VH));
    ground = document.createElement("div");
    ground.style.cssText = `position:absolute;left:0;top:${map.ground.top}px;width:${map.ground.width}px;height:${map.ground.height}px;`
      + `background-image:url("${map.ground.src}");background-size:100% 100%`;
    world.appendChild(ground);
    body = document.createElement("div");
    body.style.cssText = "position:absolute;background-repeat:no-repeat";
    world.appendChild(body);
    bands = bands.concat(layers.filter(l => l.plane === "foreground").map(l => parallaxBand(world, map, l, VW, VH)));
    hidden.clear();
    layerTable(map, rows, hidden, retuned => { if (retuned) tune(); draw(); }, signal);
    st.x = Math.min(map.width / 2, 1500); st.face = 1; st.feet = groundAt(st.x); st.vy = 0; st.grounded = true;
    box.querySelectorAll<HTMLElement>("[data-map]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.map === id)));
    draw();
  };
  const setAll = (pick: (l: ParallaxLayer) => Tune): void => { map.layers.forEach(l => Object.assign(tuneOf(map, l), pick(l))); syncTable(map, rows); tune(); draw(); };
  const move = (dt: number): void => {
    let dir = (keys.has("ArrowRight") ? 1 : 0) - (keys.has("ArrowLeft") ? 1 : 0), fast = keys.has("Shift");
    if (opt.auto) {
      if (st.x > map.width - EDGE) st.face = -1; else if (st.x < EDGE) st.face = 1;
      dir = st.face; fast = false;
    }
    let blocked = false;
    if (dir) {
      st.face = dir;
      const nx = Math.min(Math.max(st.x + dir * (fast ? RUN : WALK) * dt, EDGE / 2), map.width - EDGE / 2);
      if (!solid(nx, st.feet - 1)) st.x = nx;
      else {
        // A step no higher than one tile is walked up; anything taller is a wall.
        let top = map.ground.top + Math.floor((st.feet - 1 - map.ground.top) / map.tile) * map.tile;
        while (solid(nx, top - 1) && st.feet - top < map.tile) top -= map.tile;
        if (st.grounded && st.feet - top <= map.tile && !solid(nx, top - 1)) { st.feet = top; st.x = nx; } else blocked = true;
      }
    }
    if ((st.jump || (opt.auto && blocked)) && st.grounded) { st.vy = JUMP; st.grounded = false; st.t = 0; }
    st.jump = false;
    if (st.grounded && !solid(st.x, st.feet + 1)) { st.grounded = false; st.vy = 0; st.t = 10; }
    if (!st.grounded) {
      st.vy -= FALL * dt;
      const next = st.feet - st.vy * dt;
      let landed = false;
      if (st.vy <= 0) {
        for (let y = map.ground.top + Math.ceil((st.feet - map.ground.top) / map.tile) * map.tile; y <= next; y += map.tile) {
          if (solid(st.x, y + 1) && !solid(st.x, y - 1)) { st.feet = y; st.vy = 0; st.grounded = landed = true; break; }
        }
      }
      if (!landed) st.feet = next;
    }
    const state = !st.grounded ? "jump" : dir ? (fast ? "run" : "walk") : "idle";
    if (state !== st.state) { st.state = state; if (state !== "jump") st.t = 0; }
  };
  const draw = (): void => {
    const s = stage.clientWidth / VW, camera = Math.min(Math.max(st.x - VW / 2, 0), map.width - VW);
    world.style.transform = `scale(${s})`;
    bands.forEach(b => {
      const off = hidden.has(b.layer.id);
      b.picture.style.display = off ? "none" : "";
      b.marks.style.display = off || !opt.marks ? "none" : "";
      b.scroll(camera, opt.flat ? 1 : tuneOf(map, b.layer).parallax);
    });
    ground.style.transform = `translateX(${-camera}px)`;
    const m = walker.states[st.state], k = walker.unit * m.rebase / walker.per_unit, w = m.cell[0] * k, h = m.cell[1] * k;
    const i = Math.floor(st.t * (m.fps || 1));
    const frame = m.frames[st.state === "jump" ? Math.min(i, m.frames.length - 1) : i % m.frames.length];
    Object.assign(body.style, {
      width: `${w}px`, height: `${h}px`, left: `${st.x - camera - w / 2}px`, top: `${st.feet - h}px`,
      backgroundImage: `url("${m.src}")`, backgroundSize: `${m.columns * w}px ${h}px`, backgroundPosition: `${-frame * w}px 0`,
      transform: m.mirror && st.face < 0 ? "scaleX(-1)" : "",
    });
  };
  const step = (dt: number): void => { st.t += dt; move(dt); draw(); };
  box.step = step;  // lets a test advance the stage by hand

  box.querySelectorAll<HTMLElement>("[data-map]").forEach(b => b.addEventListener("click", () => load(b.dataset.map!), { signal }));
  box.querySelectorAll<HTMLInputElement>("[data-opt]").forEach(input => input.addEventListener("change", () => { opt[input.dataset.opt as keyof typeof opt] = input.checked; draw(); }, { signal }));
  $('[data-placement="game"]').addEventListener("click", () => setAll(TUNINGS.game), { signal });
  document.addEventListener("parallax-tuning", e => {
    if (map && detailOf(e).map === map.id && detailOf(e).source !== me) { bands.forEach(b => b.place()); syncTable(map, rows); }
  }, { signal });
  // While the stage has focus it owns the arrow keys and Space, so they move the character and never scroll the page.
  const OWNED = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "Shift"];
  stage.addEventListener("keydown", e => {
    if (!OWNED.includes(e.key)) return;
    e.preventDefault();
    $("[data-hint]").classList.add("hidden");
    if (e.key !== "Shift" && opt.auto) { opt.auto = false; $<HTMLInputElement>('[data-opt="auto"]').checked = false; }
    if ((e.key === "ArrowUp" || e.key === " ") && !e.repeat) st.jump = true;
    keys.add(e.key);
  }, { signal });
  stage.addEventListener("keyup", e => keys.delete(e.key), { signal });
  stage.addEventListener("blur", () => keys.clear(), { signal });
  stage.addEventListener("pointerdown", () => stage.focus({ preventScroll: true }), { signal });
  const resized = new ResizeObserver(() => map && draw());
  resized.observe(stage);
  load(cfg.maps[0].id);
  let last = performance.now(), frameId = 0;
  const loop = (now: number): void => { step(Math.min(0.05, (now - last) / 1000)); last = now; frameId = requestAnimationFrame(loop); };
  frameId = requestAnimationFrame(loop);
  return () => {
    controller.abort();
    resized.disconnect();
    cancelAnimationFrame(frameId);
    delete box.step;
  };
};
