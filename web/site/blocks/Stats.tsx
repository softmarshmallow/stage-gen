// <Stats>: A row of <Stat> figures.
// Port of the retired showcase's `stats` component.

import type { ReactElement } from "react";
import type { BlockProps } from "./shared";
import { childrenOf } from "./shared";

export type StatsProps = Record<string, never>;

export default function Stats({ children }: BlockProps<StatsProps>): ReactElement {
  return <div className="mt-10 flex flex-wrap gap-x-16 gap-y-6">{childrenOf(children, "Stat")}</div>;
}
