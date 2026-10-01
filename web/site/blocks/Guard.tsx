// <Guard>: One row of <Guards>.
// Port of the retired showcase's `guard` component.

import type { ReactElement } from "react";
import type { BlockProps } from "./shared";
import { CELL, inline, NodeLink, textOf } from "./shared";

export interface GuardProps {
  readonly node: string;
  readonly how: string;
}

export default function Guard({ page, children, node, how }: BlockProps<GuardProps>): ReactElement {
  return (
    <tr>
      <td className={`${CELL} w-2/5`}>{textOf(children)}</td>
      <td className={`${CELL} whitespace-nowrap`}>
        <NodeLink page={page} node={node} />
      </td>
      <td className={`${CELL} text-zinc-500`}>{inline(how)}</td>
    </tr>
  );
}
