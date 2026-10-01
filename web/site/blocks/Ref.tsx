// <Ref>: An inline reference to one of the workflow's inputs, shown as a chip like an
// attachment in an agent's prompt box.
// Port of the retired showcase's `ref` component.
//
// Inside an <Agent> the chip is numbered: the showcase counted page.refs while the prompt
// rendered, and the <Agent> now clones each of its Refs with that number as `_number`.

import type { ReactElement } from "react";
import { picture } from "@/lib/page";
import type { BlockProps } from "./shared";
import { css, ground, referenceOf, textOf } from "./shared";

export interface RefProps {
  readonly input: string;
  readonly _number?: number;
}

function Document(): ReactElement {
  return (
    <svg className="size-4 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2">
      <path d="M3.5 1.5h6l3 3v10h-9z M9.5 1.5v3h3 M5.5 8h5 M5.5 10.5h5" strokeLinejoin="round" />
    </svg>
  );
}

export default function Ref({ page, children, input, _number }: BlockProps<RefProps>): ReactElement {
  const source = referenceOf(page, input);
  const inPrompt = _number !== undefined;
  const file = typeof source.file === "string" ? source.file : undefined;
  const label = textOf(children) || (file ?? input);
  let icon: ReactElement;
  if (source.kind === "image") {
    const shown = picture(source.picture, `input ${input} picture`);
    icon = (
      <img
        className="size-6 rounded-sm object-cover object-top"
        style={css(ground(shown))}
        src={shown.src}
        alt=""
      />
    );
  } else {
    icon = <Document />;
  }
  const tone = inPrompt
    ? "bg-zinc-800 text-zinc-100"
    : "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100";
  // Python sliced the text by code points; Array.from does too, where slice() counts UTF-16 units.
  const title =
    source.kind === "text" ? `${Array.from(String(source.text)).slice(0, 240).join("")}…` : (file ?? "");
  return (
    <span
      className={`mx-0.5 inline-flex items-center gap-1.5 rounded-md py-0.5 pl-1 pr-2 align-middle text-[14px] leading-6 ${tone}`}
      title={title}
    >
      {icon}
      {inPrompt ? (
        <span className="flex size-4 items-center justify-center rounded-full bg-zinc-100 text-[10px] font-semibold text-zinc-900">
          {_number}
        </span>
      ) : null}
      {label}
    </span>
  );
}
