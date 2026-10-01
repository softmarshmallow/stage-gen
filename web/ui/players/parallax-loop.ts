// Player: the hero's parallax loop: the map's layers alone, scrolling without end at the
// page's tuning; its map buttons also swap the reference picture beside it.
//
// Moved from the parallax loop section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-parallax-loop], with its config. Hooks inside it: [data-loop], [data-world],
// [data-loop-map]; the reference is the enclosing grid's [data-loop-reference].

import type { Mount } from "./dom";
import {
  byDepth, detailOf, parallaxBand, tuneOf,
  type LoopConfig, type Band, type ParallaxMap, type Stepped,
} from "./parallax";

export const mount: Mount<LoopConfig> = (root, cfg) => {
  const box = root as Stepped;
  const controller = new AbortController(), { signal } = controller;
  const [VW, VH] = cfg.view;
  const view = box.querySelector<HTMLElement>("[data-loop]")!, world = box.querySelector<HTMLElement>("[data-world]")!;
  const SPEED = 110;  // camera pixels a second in the game's 1280x720 view
  let map!: ParallaxMap, bands: Band[] = [], camera = 0;
  const reference = box.closest(".grid")?.querySelector("[data-loop-reference]");
  const load = (id: string): void => {
    map = cfg.maps.find(m => m.id === id)!;
    world.replaceChildren();
    bands = map.layers.slice().sort(byDepth).map(l => parallaxBand(world, map, l, VW, VH));
    box.querySelectorAll<HTMLElement>("[data-loop-map]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.loopMap === id)));
    if (reference) {
      reference.querySelector("img")!.src = map.reference.src;
      reference.querySelector("p")!.textContent = map.reference.file;
    }
  };
  const draw = (): void => { world.style.transform = `scale(${view.clientWidth / VW})`; bands.forEach(b => b.scroll(camera, tuneOf(map, b.layer).parallax)); };
  box.step = dt => { camera += SPEED * dt; draw(); };  // lets a test advance the loop by hand
  box.querySelectorAll<HTMLElement>("[data-loop-map]").forEach(b => b.addEventListener("click", () => { load(b.dataset.loopMap!); draw(); }, { signal }));
  document.addEventListener("parallax-tuning", e => { if (map && detailOf(e).map === map.id) bands.forEach(b => b.place()); }, { signal });
  load(cfg.maps[0].id);
  let last = performance.now(), frameId = 0;
  const loop = (now: number): void => { box.step!(Math.min(0.05, (now - last) / 1000)); last = now; frameId = requestAnimationFrame(loop); };
  frameId = requestAnimationFrame(loop);
  return () => {
    controller.abort();
    cancelAnimationFrame(frameId);
    delete box.step;
  };
};
