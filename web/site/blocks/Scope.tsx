// <Scope>: What the workflow is for, what it is not for, and what to expect, as three plain lists.
// Port of the retired showcase's `scope` component.

import { isValidElement, type ReactElement, type ReactNode } from "react";
import type { BlockProps } from "./shared";
import { blockName, MdxError, nodesOf, textOf } from "./shared";

export type ScopeProps = Record<string, never>;

const SCOPE_HEADINGS: Readonly<Record<string, string>> = {
  Works: "Works well",
  Limit: "Not expected to work",
  Tip: "Good to know",
};

const HOLDS = `<Scope> holds only ${Object.keys(SCOPE_HEADINGS)
  .map((n) => `<${n}>`)
  .join(", ")}`;

const WIDTHS: Readonly<Record<number, string>> = { 1: "", 2: "md:grid-cols-2", 3: "md:grid-cols-3" };

type Entry = ReactElement<{ children?: ReactNode }>;

export default function Scope({ children }: BlockProps<ScopeProps>): ReactElement {
  const items = nodesOf(children).filter(
    (child): child is Entry => isValidElement(child) && /^[A-Z]/.test(blockName(child) ?? ""),
  );
  if (items.some((c) => !(String(blockName(c)) in SCOPE_HEADINGS))) throw new MdxError(HOLDS);
  const columns: ReactElement[] = [];
  for (const [name, heading] of Object.entries(SCOPE_HEADINGS)) {
    const entries = items.filter((c) => blockName(c) === name).map((c) => textOf(c.props.children));
    if (entries.length > 0) {
      columns.push(
        <div key={name}>
          <h3 className="text-sm font-medium">{heading}</h3>
          <ul className="mt-2 divide-y divide-zinc-200 text-sm text-zinc-700 dark:divide-zinc-800 dark:text-zinc-300">
            {entries.map((e, i) => (
              <li key={i} className="py-2">
                {e}
              </li>
            ))}
          </ul>
        </div>,
      );
    }
  }
  // The showcase had no width for an empty <Scope> and failed on it; so does this.
  const width = WIDTHS[columns.length];
  if (width === undefined) throw new MdxError(HOLDS);
  return <div className={`mt-6 grid gap-x-10 gap-y-8 ${width}`}>{columns}</div>;
}
