// <Painter>: A small tile map you can draw on, composed live from a real atlas through its neighbour lookup.
// Port of the retired showcase's `painter` component.
// The painting itself is web/ui/players/painter.ts, mounted on [data-painter] with this config
// by <PainterPlayer>.

import type { JsonObject, JsonValue } from "@stage-gen/ui/contracts/wire";
import { capitalize } from "@/lib/page";
import PainterPlayer from "@/components/players/PainterPlayer";
import type { BlockProps } from "./shared";
import { CHECKER, childrenOf, CLIP, css, MdxError, plainOf, textOf } from "./shared";

export interface PainterProps {
  readonly start: readonly unknown[];
}

const SHAPE_WORDS: Readonly<Record<string, string>> = {
  steps: "Steps",
  concavity_and_hole: "Hollow and hole",
  one_cell_floating: "Thin ledge",
  solid_ground: "Solid block",
};

interface PainterAtlas {
  readonly label: string;
  readonly src: JsonValue | undefined;
  readonly cell: JsonValue | undefined;
  readonly columns: JsonValue | undefined;
  readonly rows: JsonValue | undefined;
  readonly lookup: JsonValue | undefined;
}

/**
 * A small tile map you can draw on, composed live from a real atlas through its neighbour lookup.
 *
 * Each <Atlas> names an atlas output of the record; the first is shown first. `start` is the
 * shape the page opens with, as rows of 0 and 1. The preset shapes are the ones the atlas was
 * validated against, plus the middle of the level it was made for.
 */
export default function Painter({ page, children, start }: BlockProps<PainterProps>) {
  const items = childrenOf(children, "Atlas");
  if (items.length === 0) throw new MdxError("<Painter> holds one or more <Atlas output=...>");
  const width = typeof start[0] === "string" ? start[0].length : -1;
  if (
    start.length === 0 ||
    start.some((r) => typeof r !== "string" || r.length !== width || /[^01]/.test(r))
  ) {
    throw new MdxError("<Painter start> is a list of equal-length rows of 0 and 1");
  }
  const rows = start as readonly string[];
  const labels = items.map((item) => textOf(item.props.children));
  const atlases: PainterAtlas[] = items.map((item, i) => {
    const name = String(item.props.output);
    const out: JsonObject | undefined = page.record.outputs[name];
    if (out === undefined || out.kind !== "atlas") {
      throw new MdxError(`<Atlas output='${name}'> is not an atlas of this run`);
    }
    return {
      // The player never reads the label; the toggle shows it as markup, the config as text.
      label: plainOf(labels[i]),
      src: out.src,
      cell: out.cell_px,
      columns: out.columns,
      rows: out.rows,
      lookup: out.lookup,
    };
  });
  const first = page.record.outputs[String(items[0].props.output)];
  if (first.level === undefined || typeof first.shapes !== "object" || first.shapes === null) {
    throw new MdxError(`<Atlas output='${String(items[0].props.output)}'> records no level and shapes`);
  }
  const shapes: Record<string, JsonValue | readonly string[]> = {
    "Start again": rows,
    "Part of the level": first.level,
  };
  for (const [k, v] of Object.entries(first.shapes as JsonObject)) {
    if (k in SHAPE_WORDS) shapes[SHAPE_WORDS[k] ?? capitalize(k.replaceAll("_", " "))] = v;
  }
  shapes.Clear = Array.from({ length: rows.length }, () => "0".repeat(width));
  const config = JSON.stringify({ start: rows, shapes, atlases });
  return (
    <PainterPlayer config={config} className="mt-6">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex gap-1.5">
          {atlases.length > 1
            ? atlases.map((_, i) => (
                <button key={i} data-atlas={i} aria-pressed={i === 0 ? "true" : "false"} className={CLIP}>
                  {labels[i]}
                </button>
              ))
            : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(shapes).map((name) => (
            <button key={name} data-shape={name} className={CLIP}>
              {name}
            </button>
          ))}
        </div>
      </div>
      <canvas className="mt-4 block w-full cursor-crosshair touch-none rounded-sm bg-zinc-50 dark:bg-zinc-900"></canvas>
      <p className="mt-3 max-w-3xl text-sm text-zinc-500">
        Click or drag to add or take away ground. Each cell looks at its eight neighbours and takes one of the 47 tiles;
        point at a cell to see which one in the atlas below.
      </p>
      <div className="relative mt-4 max-w-3xl overflow-hidden rounded-sm" style={css(CHECKER)}>
        <img data-sheet="" className="block w-full" src={String(atlases[0].src)} alt="" />
        <div
          data-highlight=""
          className="pointer-events-none absolute hidden outline-2 outline-offset-0 outline-zinc-900 dark:outline-zinc-100"
          style={css("box-shadow:0 0 0 9999px rgb(255 255 255 / 0.55)")}
        ></div>
      </div>
    </PainterPlayer>
  );
}
