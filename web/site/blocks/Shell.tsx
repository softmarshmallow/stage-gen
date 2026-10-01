// <Shell>: The commands of <Try>, with a copy button.
// Port of the retired showcase's `shell` component.
//
// web/ui/players/copy.ts, through <CopyPlayer>, copies a [data-copy] button's text.

import { isValidElement, type ReactElement, type ReactNode } from "react";
import CopyPlayer from "@/components/players/CopyPlayer";
import type { BlockProps } from "./shared";
import { blockName, MdxError, nodesOf } from "./shared";

export type ShellProps = Record<string, never>;

/** The copy icon of <Agent> and <Shell> (the showcase's COPY). */
export function CopyIcon(): ReactElement {
  return (
    <svg className="size-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M3.5 10.5h-1v-8h8v1" />
    </svg>
  );
}

/** A fenced block's code: MDX hands <pre> one <code> child holding it, with its final newline. */
function codeOf(pre: ReactNode): string {
  if (!isValidElement<{ children?: ReactNode }>(pre)) return "";
  const code = pre.props.children;
  const inner = isValidElement<{ children?: ReactNode }>(code) ? code.props.children : code;
  return typeof inner === "string" ? inner.replace(/\n+$/, "") : "";
}

/** The Shell box: its blocks, and a button that copies `code`. Also used by <Try>'s declared commands. */
export function ShellBox({ blocks, code }: { blocks: ReactNode; code: string }): ReactElement {
  return (
    <div className="max-w-3xl">
      {blocks}
      <CopyPlayer
        code={code}
        className="mt-3 flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <CopyIcon />
        <span>Copy commands</span>
      </CopyPlayer>
    </div>
  );
}

export default function Shell({ children }: BlockProps<ShellProps>): ReactElement {
  const blocks = nodesOf(children);
  const code = blocks
    .filter((b) => blockName(b) === "pre")
    .map(codeOf)
    .join("\n\n");
  if (!code) throw new MdxError("<Shell> holds at least one ``` code block");
  return <ShellBox blocks={blocks} code={code} />;
}
