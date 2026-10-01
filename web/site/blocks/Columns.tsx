// <Columns>: Blocks split into one to three columns at each ## heading.
// Port of the retired showcase's `columns` component.

import type { ReactElement, ReactNode } from "react";
import type { BlockProps } from "./shared";
import { blockName, MdxError, nodesOf } from "./shared";

export type ColumnsProps = Record<string, never>;

const WIDTHS: Readonly<Record<number, string>> = { 1: "", 2: "lg:grid-cols-2", 3: "lg:grid-cols-3" };

export default function Columns({ children }: BlockProps<ColumnsProps>): ReactElement {
  // A sentence written inline in the tag is not blocks.
  if (typeof children === "string") throw new MdxError("<Columns> holds blocks");
  const blocks = nodesOf(children);
  const groups: ReactNode[][] = [];
  for (const block of blocks) {
    if (blockName(block) === "h2" || groups.length === 0) groups.push([]);
    groups[groups.length - 1].push(block);
  }
  const width = WIDTHS[groups.length];
  if (width === undefined) throw new MdxError("<Columns> holds one to three columns");
  return (
    <div className={`grid gap-x-12 ${width}`}>
      {groups.map((group, i) => (
        <div key={i}>{group}</div>
      ))}
    </div>
  );
}
