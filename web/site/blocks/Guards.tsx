// <Guards>: A table of <Guard> rows: by hand, in the graph, how.
// Port of the retired showcase's `guards` component.

import type { ReactElement } from "react";
import type { BlockProps } from "./shared";
import { childrenOf, HEAD } from "./shared";

export type GuardsProps = Record<string, never>;

export default function Guards({ children }: BlockProps<GuardsProps>): ReactElement {
  return (
    <table className="mt-4 w-full text-sm">
      <thead>
        <tr>
          <th className={HEAD}>By hand</th>
          <th className={HEAD}>In the graph</th>
          <th className={HEAD}>How</th>
        </tr>
      </thead>
      <tbody>{childrenOf(children, "Guard")}</tbody>
    </table>
  );
}
