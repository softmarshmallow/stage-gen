// Player: the tile painter: the peering-mask neighbour rule looked up in the atlas's 47-mask table, drawn from the atlas bytes on a canvas, with presets, atlas toggles and the highlighted sheet cell.
//
// Moved from the [data-painter] section of the retired showcase's page script: same logic,
// same constants and the same comments, typed.
// Root: [data-painter], with its config. Hooks inside it: [data-shape], [data-atlas], canvas,
// [data-sheet], [data-highlight].

import type { Mount } from "./dom";

/** One atlas the painter draws from: blocks/Painter.tsx writes it into the config. */
interface PainterAtlas {
  readonly label: string;
  readonly src: string;
  readonly cell: number;
  readonly columns: number;
  readonly rows: number;
  /** The 47-mask table: a 3x3 neighbour mask, read row by row, to its [column, row] in the sheet. */
  readonly lookup: Readonly<Record<string, readonly [number, number]>>;
}

/** The [data-painter] config: rows of "0" and "1", the preset shapes by button name, the atlases. */
export interface PainterConfig {
  readonly start: readonly string[];
  readonly shapes: Readonly<Record<string, readonly string[]>>;
  readonly atlases: readonly PainterAtlas[];
}

type Cell = 0 | 1;
/** One canvas per tile of a loaded sheet, by "column,row". */
type Sheet = Record<string, HTMLCanvasElement>;

// Tile painter: the pipeline's neighbour rule (peering_mask), looked up in the atlas's own 47-mask
// table and drawn from its exact bytes. Past the frame it does what the game does at a map's edge:
// the side columns and the bottom row carry on, so the ground does not end in a finished rim there.
export const mount: Mount<PainterConfig> = (box, cfg) => {
  const controller = new AbortController(), { signal } = controller;
  const canvas = box.querySelector("canvas")!, ctx = canvas.getContext("2d")!;
  const W = cfg.start[0].length, H = cfg.start.length, C = cfg.atlases[0].cell, mark = box.querySelector<HTMLElement>("[data-highlight]")!;
  canvas.width = W * C; canvas.height = H * C;
  const sheets: (Sheet | null)[] = cfg.atlases.map(() => null);
  let current = 0, grid: Cell[][], paint: Cell | null = null;
  const inside = (x: number, y: number) => x >= 0 && y >= 0 && x < W && y < H;
  const fit = (rows: readonly string[]): Cell[][] => {  // centred across, sitting on the bottom row; cropped or padded to the grid
    const out = Array.from({ length: H }, () => Array<Cell>(W).fill(0)), dx = Math.floor((W - rows[0].length) / 2), dy = H - rows.length;
    rows.forEach((row, y) => [...row].forEach((v, x) => { if (inside(x + dx, y + dy)) out[y + dy][x + dx] = v === "1" ? 1 : 0; }));
    return out;
  };
  const at = (x: number, y: number): Cell => y < 0 ? 0 : grid[Math.min(y, H - 1)][Math.min(Math.max(x, 0), W - 1)];
  const mask = (x: number, y: number) => { const n = at(x, y - 1), e = at(x + 1, y), s = at(x, y + 1), w = at(x - 1, y);
    return [n & w & at(x - 1, y - 1), n, n & e & at(x + 1, y - 1), w, 1, e, s & w & at(x - 1, y + 1), s, s & e & at(x + 1, y + 1)].join(""); };
  const tile = (x: number, y: number) => inside(x, y) && grid[y][x] ? cfg.atlases[current].lookup[mask(x, y)] : null;
  function draw(): void {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "rgba(113,113,122,0.18)"; ctx.lineWidth = 2;
    const sheet = sheets[current];
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const t = tile(x, y);
      if (!t) ctx.strokeRect(x * C + 1, y * C + 1, C - 2, C - 2);
      else if (sheet) ctx.drawImage(sheet[t[0] + "," + t[1]], x * C, y * C);
    }
  }
  function load(i: number): void {
    if (sheets[i]) return draw();
    const a = cfg.atlases[i], img = new Image();
    img.onload = () => {  // one canvas per tile, so scaling never samples a neighbouring tile
      if (signal.aborted) return;
      const cells: Sheet = {};
      for (let y = 0; y < a.rows; y++) for (let x = 0; x < a.columns; x++) {
        const c = document.createElement("canvas"); c.width = c.height = a.cell;
        c.getContext("2d")!.drawImage(img, x * a.cell, y * a.cell, a.cell, a.cell, 0, 0, a.cell, a.cell);
        cells[x + "," + y] = c;
      }
      sheets[i] = cells; if (i === current) draw();
    };
    img.src = a.src;
  }
  const cellAt = (e: PointerEvent): [number, number] => { const r = canvas.getBoundingClientRect(); return [Math.floor((e.clientX - r.left) / r.width * W), Math.floor((e.clientY - r.top) / r.height * H)]; };
  function point(x: number, y: number): void {
    const t = tile(x, y), a = cfg.atlases[current];
    mark.classList.toggle("hidden", !t);
    if (t) Object.assign(mark.style, { left: t[0] / a.columns * 100 + "%", top: t[1] / a.rows * 100 + "%", width: 100 / a.columns + "%", height: 100 / a.rows + "%" });
  }
  let last: [number, number] | null = null;
  const stroke = (x: number, y: number) => {  // every cell on the line from the last one, so a fast drag leaves no gaps
    const [x0, y0] = last || [x, y], steps = Math.max(Math.abs(x - x0), Math.abs(y - y0), 1);
    for (let i = 0; i <= steps; i++) {
      const cx = Math.round(x0 + (x - x0) * i / steps), cy = Math.round(y0 + (y - y0) * i / steps);
      if (inside(cx, cy)) grid[cy][cx] = paint!;
    }
    last = [x, y]; draw();
  };
  canvas.addEventListener("pointerdown", e => {
    const [x, y] = cellAt(e); if (!inside(x, y)) return;
    paint = grid[y][x] ? 0 : 1; last = null; canvas.setPointerCapture(e.pointerId); stroke(x, y); point(x, y);
  }, { signal });
  canvas.addEventListener("pointermove", e => {
    const [x, y] = cellAt(e);
    if (paint !== null && (!last || last[0] !== x || last[1] !== y)) stroke(x, y);
    point(x, y);
  }, { signal });
  canvas.addEventListener("pointerup", () => { paint = null; }, { signal });
  canvas.addEventListener("pointerleave", () => { if (paint === null) mark.classList.add("hidden"); }, { signal });
  box.querySelectorAll<HTMLElement>("[data-shape]").forEach(b => b.addEventListener("click", () => { grid = fit(cfg.shapes[b.dataset.shape!]); draw(); }, { signal }));
  box.querySelectorAll<HTMLElement>("[data-atlas]").forEach(b => b.addEventListener("click", () => {
    current = +b.dataset.atlas!;
    box.querySelectorAll("[data-atlas]").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    box.querySelector<HTMLImageElement>("[data-sheet]")!.src = cfg.atlases[current].src; mark.classList.add("hidden"); load(current);
  }, { signal }));
  grid = fit(cfg.start); load(0);
  return () => controller.abort();
};
