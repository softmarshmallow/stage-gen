// Player: the parallax playground: a map's layers alone, scrolled by the clock, a drag or
// the arrow keys, with the layer table, the speed and the game placement.
//
// Moved from the parallax playground section of the retired showcase's page script: same
// logic, same constants and the same comments, typed.
// Root: [data-parallax-playground], with its config. Hooks inside it: [data-stage],
// [data-world], [data-layers], [data-speed], [data-speed-value], [data-play], [data-map],
// [data-opt], [data-placement], [data-hint].

import type { Mount } from "./dom";
import {
  announce, byDepth, detailOf, layerTable, parallaxBand, syncTable, TUNINGS, tuneOf,
  type Band, type LoopConfig, type ParallaxLayer, type ParallaxMap, type Stepped, type Tune,
} from "./parallax";

export const mount: Mount<LoopConfig> = (root, cfg) => {
  const box = root as Stepped;
  const controller = new AbortController(), { signal } = controller;
  const [VW, VH] = cfg.view;
  const $ = <E extends Element = HTMLElement>(sel: string): E => box.querySelector<E>(sel)!;
  const stage = $("[data-stage]"), world = $("[data-world]"), rows = $("[data-layers]"), speedInput = $<HTMLInputElement>("[data-speed]");
  const opt = { flat: false, marks: false, playing: true }, keys = new Set<string>(), hidden = new Set<string>(), me = "playground-" + Math.random();
  const KEY_SPEED = 480;  // camera pixels a second while an arrow key is held
  let map!: ParallaxMap, bands: Band[] = [], camera = 0, speed = parseFloat(speedInput.value), drag: { x: number; camera: number } | null = null;
  const tune = (): void => { bands.forEach(b => b.place()); announce(map, me); };
  const load = (id: string): void => {
    map = cfg.maps.find(m => m.id === id)!;
    world.replaceChildren();
    bands = map.layers.slice().sort(byDepth).map(l => parallaxBand(world, map, l, VW, VH));
    hidden.clear();
    layerTable(map, rows, hidden, retuned => { if (retuned) tune(); draw(); }, signal);
    box.querySelectorAll<HTMLElement>("[data-map]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.map === id)));
    draw();
  };
  const setAll = (pick: (l: ParallaxLayer) => Tune): void => { map.layers.forEach(l => Object.assign(tuneOf(map, l), pick(l))); syncTable(map, rows); tune(); draw(); };
  const draw = (): void => {
    world.style.transform = `scale(${stage.clientWidth / VW})`;
    bands.forEach(b => {
      const off = hidden.has(b.layer.id);
      b.picture.style.display = off ? "none" : "";
      b.marks.style.display = off || !opt.marks ? "none" : "";
      b.scroll(camera, opt.flat ? 1 : tuneOf(map, b.layer).parallax);
    });
  };
  const step = (dt: number): void => {
    const held = (keys.has("ArrowRight") ? 1 : 0) - (keys.has("ArrowLeft") ? 1 : 0);
    if (held) camera += held * KEY_SPEED * dt;
    else if (opt.playing && !drag) camera += speed * dt;
    draw();
  };
  box.step = step;  // lets a test advance the view by hand
  const showSpeed = (): void => {
    $("[data-speed-value]").textContent = speed === 0 ? "still" : `${Math.abs(speed)} px/s ${speed < 0 ? "←" : "→"}`;
  };
  const setPlaying = (on: boolean): void => {
    opt.playing = on;
    const b = $("[data-play]");
    b.setAttribute("aria-pressed", String(on));
    b.textContent = on ? "Pause" : "Play";
  };

  box.querySelectorAll<HTMLElement>("[data-map]").forEach(b => b.addEventListener("click", () => load(b.dataset.map!), { signal }));
  box.querySelectorAll<HTMLInputElement>("[data-opt]").forEach(input => input.addEventListener("change", () => { opt[input.dataset.opt as keyof typeof opt] = input.checked; draw(); }, { signal }));
  $("[data-play]").addEventListener("click", () => setPlaying(!opt.playing), { signal });
  speedInput.addEventListener("input", () => { speed = parseFloat(speedInput.value); showSpeed(); }, { signal });
  $('[data-placement="game"]').addEventListener("click", () => setAll(TUNINGS.game), { signal });
  document.addEventListener("parallax-tuning", e => {
    if (map && detailOf(e).map === map.id && detailOf(e).source !== me) { bands.forEach(b => b.place()); syncTable(map, rows); }
  }, { signal });
  // Dragging the picture moves the camera with the hand; the layers slide at their own speeds under it.
  stage.addEventListener("pointerdown", e => {
    stage.focus({ preventScroll: true });
    $("[data-hint]").classList.add("hidden");
    drag = { x: e.clientX, camera };
    stage.setPointerCapture(e.pointerId);
  }, { signal });
  stage.addEventListener("pointermove", e => { if (drag) camera = drag.camera - (e.clientX - drag.x) * VW / stage.clientWidth; }, { signal });
  const release = (): void => { drag = null; };
  stage.addEventListener("pointerup", release, { signal });
  stage.addEventListener("pointercancel", release, { signal });
  // While the view has focus it owns the arrow keys and Space, so they never scroll the page.
  stage.addEventListener("keydown", e => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(e.key)) return;
    e.preventDefault();
    $("[data-hint]").classList.add("hidden");
    if (e.key === " " && !e.repeat) setPlaying(!opt.playing);
    keys.add(e.key);
  }, { signal });
  stage.addEventListener("keyup", e => keys.delete(e.key), { signal });
  stage.addEventListener("blur", () => keys.clear(), { signal });
  const resized = new ResizeObserver(() => map && draw());
  resized.observe(stage);
  showSpeed();
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
