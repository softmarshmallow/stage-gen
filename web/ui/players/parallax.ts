// What the three parallax players share: layers placed and scrolled as the game does, the
// tuning one page holds per map, and the layer table. The players are parallax-loop.ts (the
// hero loop), parallax-stage.ts (the stage with the walker) and parallax-playground.ts.
//
// Moved from the parallax sections of the retired showcase's page script, from
// parallaxTuning to the end: same logic, same constants and the same comments, typed.

/** One layer of a map, as the record's parallax output carries it (snake_case, as in record.json). */
export interface ParallaxLayer {
  readonly id: string;
  readonly plane: string;
  readonly order: number;
  readonly parallax: number;
  readonly src: string;
  readonly baked: number;
  readonly width: number;
  readonly height: number;
  readonly anchor: string;
  readonly offset: number;
  readonly scale: number;
  readonly dy: number;
  readonly game_scale: number;
  readonly how: string;
  readonly period: number;
  readonly cuts: number;
  readonly marks: string;
}

/** One map: its layers, the ground composed from its atlas, and the grid that is its level. */
export interface ParallaxMap {
  readonly id: string;
  readonly label: string;
  readonly width: number;
  readonly walk_surface: number;
  readonly reference: { readonly src: string; readonly file: string };
  readonly ground: { readonly src: string; readonly width: number; readonly height: number; readonly top: number };
  readonly grid: readonly string[];
  readonly tile: number;
  readonly layers: readonly ParallaxLayer[];
}

/** One of the walker's strips. */
export interface WalkerState {
  readonly src: string;
  readonly columns: number;
  readonly cell: readonly [number, number];
  readonly frames: readonly number[];
  readonly fps: number | null;
  readonly rebase: number;
  readonly mirror: boolean;
}

/** The character that walks the stage's ground. */
export interface ParallaxWalker {
  readonly states: Readonly<Record<string, WalkerState>>;
  readonly per_unit: number;
  readonly unit: number;
}

export interface LoopConfig {
  readonly maps: readonly ParallaxMap[];
  readonly view: readonly [number, number];
}

export interface StageConfig extends LoopConfig {
  readonly walker: ParallaxWalker;
}

/** A layer's placement and speed under the page's tuning. */
export interface Tune {
  dy: number;
  scale: number;
  parallax: number;
}

export interface Band {
  readonly layer: ParallaxLayer;
  readonly picture: HTMLDivElement;
  readonly marks: HTMLDivElement;
  place(): void;
  scroll(camera: number, speed: number): void;
}

/** A player root that a test can advance by hand. */
export type Stepped = HTMLElement & { step?: (dt: number) => void };

interface TuningDetail {
  readonly map: string;
  readonly source: string;
}

// Parallax layers placed and scrolled the way the game does, under the page's tuning. The hero loop
// and the stage share one tuning per map, so a change in the stage's table shows in both.
const parallaxTuning: Record<string, Record<string, Tune>> = {};
export const tuneOf = (map: ParallaxMap, layer: ParallaxLayer): Tune =>
  ((parallaxTuning[map.id] ??= {})[layer.id] ??= { dy: layer.dy, scale: layer.scale, parallax: layer.parallax });
export const announce = (map: ParallaxMap, source: string): void => {
  document.dispatchEvent(new CustomEvent<TuningDetail>("parallax-tuning", { detail: { map: map.id, source } }));
};
export const TUNINGS: Readonly<Record<"tuned" | "game", (l: ParallaxLayer) => Tune>> = {
  tuned: (l) => ({ dy: l.dy, scale: l.scale, parallax: l.parallax }),
  game: (l) => ({ dy: 0, scale: l.game_scale, parallax: l.parallax }),
};
const LAYER_HOW: Readonly<Record<string, string>> = {
  seam_repaint: "Repainted through its wrap",
  none: "Looped as drawn",
  mirror_repeat: "Reflected; it is a plain gradient",
};
const layerName = (id: string): string => id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const layerTop = (layer: ParallaxLayer, h: number, walk: number, VH: number): number => {
  const o = layer.offset;
  if (layer.anchor === "canvas_cover") return 0;
  if (layer.anchor === "screen_top") return o * h;
  if (layer.anchor === "screen_center") return VH / 2 - h / 2 + o * h;
  return (layer.anchor === "screen_bottom" ? VH : walk) - (1 - o) * h;
};
export const byDepth = (a: ParallaxLayer, b: ParallaxLayer): number =>
  Number(a.plane === "foreground") - Number(b.plane === "foreground") || a.order - b.order;
export const parallaxBand = (world: HTMLElement, map: ParallaxMap, layer: ParallaxLayer, VW: number, VH: number): Band => {
  const make = (image: string): HTMLDivElement => {
    const d = document.createElement("div");
    d.style.cssText = `position:absolute;left:0;width:${VW}px;background-repeat:repeat-x;background-image:url("${image}")`;
    world.appendChild(d);
    return d;
  };
  const picture = make(layer.src), marks = make(layer.marks);
  marks.style.display = "none";
  let w = layer.width;
  const band: Band = {
    layer, picture, marks,
    place() {
      const t = tuneOf(map, layer), h = layer.height * t.scale;
      w = layer.width * t.scale;
      const top = layerTop(layer, h, map.walk_surface, VH) + t.dy;
      for (const d of [picture, marks]) Object.assign(d.style, { top: `${top}px`, height: `${h}px`, backgroundSize: `${w}px ${h}px` });
    },
    scroll(camera, speed) { picture.style.backgroundPositionX = marks.style.backgroundPositionX = `${-((camera * speed) % w)}px`; },
  };
  band.place();
  return band;
};

// One row per layer, shown or not, with its speed, height and size under the page's tuning.
// `changed(true)` means the tuning moved; `changed(false)` that only visibility did.
// `signal` is the owning player's: its rows stop answering when that player unmounts.
export const layerTable = (map: ParallaxMap, tbody: HTMLElement, hidden: Set<string>, changed: (retuned: boolean) => void, signal: AbortSignal): void => {
  const cell = "border-b border-zinc-200 py-2 pr-4 dark:border-zinc-800";
  const field = "rounded-sm border border-zinc-300 px-1.5 py-0.5 tabular-nums dark:border-zinc-700 dark:bg-zinc-900";
  tbody.replaceChildren(...map.layers.slice().sort(byDepth).map(l => {
    const tr = document.createElement("tr"), t = tuneOf(map, l);
    const how = LAYER_HOW[l.how] + (l.cuts ? `, cut back in at ${l.cuts} places` : "");
    tr.dataset.layer = l.id;
    tr.innerHTML = `<td class="${cell}"><input data-show type="checkbox" checked class="accent-zinc-900"></td>`
      + `<td class="${cell} pr-6">${layerName(l.id)}<span class="text-zinc-400"> · ${l.plane === "foreground" ? "in front" : "behind"}</span></td>`
      + `<td class="${cell} whitespace-nowrap text-zinc-500"><input data-tune="parallax" type="number" step="0.02" min="0" max="3" value="${t.parallax}" class="${field} w-16">× the camera</td>`
      + `<td class="${cell} tabular-nums text-zinc-500">${l.period} px</td>`
      + `<td class="${cell} text-zinc-500">${how}</td>`
      + `<td class="${cell} whitespace-nowrap"><input data-tune="dy" type="number" step="2" min="-400" max="400" value="${t.dy}" class="${field} w-20"> px</td>`
      + `<td class="${cell} whitespace-nowrap"><input data-tune="scale" type="number" step="0.01" min="0.3" max="3" value="${t.scale}" class="${field} w-20">×</td>`;
    tr.querySelector("[data-show]")!.addEventListener("change", e => { (e.target as HTMLInputElement).checked ? hidden.delete(l.id) : hidden.add(l.id); changed(false); }, { signal });
    tr.querySelectorAll<HTMLInputElement>("[data-tune]").forEach(input => input.addEventListener("input", () => {
      const v = parseFloat(input.value);
      if (Number.isFinite(v)) { tuneOf(map, l)[input.dataset.tune as keyof Tune] = v; changed(true); }
    }, { signal }));
    return tr;
  }));
};
export const syncTable = (map: ParallaxMap, tbody: HTMLElement): void => tbody.querySelectorAll<HTMLElement>("tr").forEach(tr => {
  const t = tuneOf(map, map.layers.find(l => l.id === tr.dataset.layer)!);
  for (const key of ["parallax", "dy", "scale"] as const) tr.querySelector<HTMLInputElement>(`[data-tune="${key}"]`)!.value = String(t[key]);
});

/** The `parallax-tuning` event's detail. */
export const detailOf = (e: Event): TuningDetail => (e as CustomEvent<TuningDetail>).detail;
