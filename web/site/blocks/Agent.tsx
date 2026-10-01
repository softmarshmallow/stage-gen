// <Agent>: The prompt box of <Try>, with a copy button.
// Port of the retired showcase's `agent` component.
//
// The showcase numbered the prompt's references through page.refs while it rendered. React
// renders children after the parent returns, so each <Ref> of the prompt's paragraphs is
// cloned here with its number as `_number`, counted across the paragraphs in order.

import { Children, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import CopyPlayer from "@/components/players/CopyPlayer";
import type { BlockProps } from "./shared";
import { blockName, MdxError, nodesOf, plainPrompt } from "./shared";
import { CopyIcon } from "./Shell";

export type AgentProps = Record<string, never>;

export default function Agent({ page, children }: BlockProps<AgentProps>): ReactElement {
  const paragraphs = nodesOf(children).filter(
    (b): b is ReactElement<{ children?: ReactNode }> => isValidElement(b) && blockName(b) === "p",
  );
  if (paragraphs.length === 0) throw new MdxError("<Agent> holds the prompt as one or more paragraphs");
  let refs = 0;
  const body = paragraphs.map((p, i) => (
    <p key={i} className="[&+&]:mt-3">
      {Children.map(p.props.children, (part) => {
        if (!isValidElement(part) || blockName(part) !== "Ref") return part;
        refs += 1;
        return cloneElement(part as ReactElement<{ _number?: number }>, { _number: refs });
      })}
    </p>
  ));
  const copy = plainPrompt(page, paragraphs);
  return (
    <>
      <div className="max-w-3xl rounded-3xl bg-zinc-900 p-5 text-[15px] leading-8 text-zinc-100 dark:ring-1 dark:ring-zinc-800">
        {body}
        <div className="mt-4 flex items-center justify-between">
          <span className="flex size-8 items-center justify-center rounded-full border border-zinc-700 text-zinc-400">+</span>
          <div className="flex items-center gap-3">
            <CopyPlayer
              code={copy}
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            >
              <CopyIcon />
              <span>Copy prompt</span>
            </CopyPlayer>
            <span className="flex size-9 items-center justify-center rounded-full bg-zinc-100 text-zinc-900">
              <svg className="size-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M8 13V3.5M4 7l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          </div>
        </div>
      </div>
      <p className="mt-3 text-sm text-zinc-500">
        Paste it into an agent that can use this repository, and attach your own files where the prompt refers to them.
      </p>
    </>
  );
}
