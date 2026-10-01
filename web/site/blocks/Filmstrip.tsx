// <Filmstrip>: Three to five <Frame>s in a grid, landscape when every frame is wide.
// Port of the retired showcase's `filmstrip` component.
//
// The showcase set page.frame_box while its frames rendered; React renders children after
// the parent returns, so each frame is cloned with the box as its `_box` prop instead.

import { cloneElement, type ReactElement } from "react";
import type { BlockProps } from "./shared";
import { childrenOf, MdxError } from "./shared";

export type FilmstripProps = Record<string, never>;

const COLUMNS: Readonly<Record<number, string>> = {
  3: "md:grid-cols-3",
  4: "md:grid-cols-4",
  5: "md:grid-cols-5",
};
const LANDSCAPE_COLUMNS: Readonly<Record<number, string>> = {
  3: "md:grid-cols-3",
  4: "md:grid-cols-2",
  5: "md:grid-cols-3",
};

export default function Filmstrip({ page, children }: BlockProps<FilmstripProps>): ReactElement {
  const items = childrenOf(children, "Frame");
  let width = COLUMNS[items.length];
  if (width === undefined) throw new MdxError("<Filmstrip> holds three to five frames");

  // Landscape sheets, and pictures shown side by side, would shrink to strips in portrait boxes,
  // so they get fewer, wider columns.
  const shape = (frame: (typeof items)[number]): number => {
    const pictures = page.node(String(frame.props.node)).pictures;
    const picks = (frame.props.media as readonly number[] | undefined) ?? [0];
    let sum = 0;
    for (const i of picks) {
      const p = i < pictures.length ? pictures.at(i) : undefined;
      if (p !== undefined) sum += Number(p.width) / Number(p.height);
    }
    return sum;
  };

  const shapes = items.filter((f) => "node" in f.props).map(shape);
  const landscape = shapes.length > 0 && shapes.every((s) => s > 1.1);
  if (landscape) width = LANDSCAPE_COLUMNS[items.length];
  const box = landscape ? "aspect-[4/3]" : "aspect-[3/4]";
  return (
    <div className={`mt-6 grid grid-cols-2 gap-6 ${width}`}>
      {items.map((frame) => cloneElement(frame, { _box: box }))}
    </div>
  );
}
