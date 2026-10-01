// <Stat>: One metric of the run, formatted by its unit, with its sentence under it.
// Port of the retired showcase's `stat` component.

import type { ReactElement } from "react";
import type { BlockProps } from "./shared";
import { minutes, money, textOf } from "./shared";

export interface StatProps {
  readonly metric: string;
}

const METRIC_FORMATS: Readonly<Record<string, (value: number) => string | null>> = {
  seconds: minutes,
  usd: money,
};

export default function Stat({ page, children, metric }: BlockProps<StatProps>): ReactElement {
  const raw = page.metric(metric);
  const unit = metric.split("_").at(-1) ?? metric;
  const format = METRIC_FORMATS[unit];
  const value = format ? format(raw) : String(raw);
  return (
    <div>
      <div className="text-2xl font-medium tabular-nums">{value}</div>
      <div className="mt-1 text-sm text-zinc-500">{textOf(children)}</div>
    </div>
  );
}
