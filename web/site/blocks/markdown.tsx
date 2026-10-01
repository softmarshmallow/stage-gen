// The Markdown a page body holds, rendered with the showcase's markup: the port of the
// retired showcase's render_blocks and its inline Markdown. MDX parses the Markdown; these
// components give each element the showcase's classes. A fenced code block is the
// showcase's bare <pre>, without the <code> MDX nests in it.
//
// DOC_MARKDOWN extends the same look to the docs and contracts, which use more of Markdown
// than a page body does (h1, h4, ordered lists, tables, quotes).

import { isValidElement, type ComponentType, type ReactElement, type ReactNode } from "react";
import { CELL, HEAD } from "./shared";

type Props = { readonly children?: ReactNode };
type LinkProps = Props & { readonly href?: string };

function H2({ children }: Props): ReactElement {
  return (
    <h2 className="mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800">{children}</h2>
  );
}

function H3({ children }: Props): ReactElement {
  return <h3 className="mt-8 font-medium">{children}</h3>;
}

function P({ children }: Props): ReactElement {
  return <p className="mt-6 max-w-3xl text-zinc-700 dark:text-zinc-300">{children}</p>;
}

/** The code text of a fenced block: MDX hands <pre> one <code> child holding it. */
function codeText(children: ReactNode): ReactNode {
  if (isValidElement<Props>(children)) {
    const inner = children.props.children;
    // MDX keeps the newline that ends the block; the showcase stripped it.
    return typeof inner === "string" ? inner.replace(/\n+$/, "") : inner;
  }
  return children;
}

function Pre({ children }: Props): ReactElement {
  return (
    <pre className="mt-4 overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-4 font-mono text-[13px] leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
      {codeText(children)}
    </pre>
  );
}

function Ul({ children }: Props): ReactElement {
  return (
    <ul className="mt-4 max-w-3xl list-disc space-y-1.5 pl-5 text-zinc-700 dark:text-zinc-300">{children}</ul>
  );
}

function Li({ children }: Props): ReactElement {
  return <li>{children}</li>;
}

function Code({ children }: Props): ReactElement {
  return <code className="font-mono text-[0.9em]">{children}</code>;
}

function Strong({ children }: Props): ReactElement {
  return <strong>{children}</strong>;
}

function Em({ children }: Props): ReactElement {
  return <em>{children}</em>;
}

function A({ children, href }: LinkProps): ReactElement {
  return (
    <a className="underline underline-offset-2" href={href}>
      {children}
    </a>
  );
}

/** The Markdown elements of a page body, by the tag name MDX asks for. */
export const MARKDOWN: Readonly<Record<string, ComponentType<Props & Record<string, unknown>>>> = {
  h2: H2,
  h3: H3,
  p: P,
  pre: Pre,
  ul: Ul,
  li: Li,
  code: Code,
  strong: Strong,
  em: Em,
  a: A,
};

function H1({ children }: Props): ReactElement {
  return <h1 className="text-3xl font-semibold tracking-tight">{children}</h1>;
}

function H4({ children }: Props): ReactElement {
  return <h4 className="mt-6 text-sm font-medium">{children}</h4>;
}

function Ol({ children }: Props): ReactElement {
  return (
    <ol className="mt-4 max-w-3xl list-decimal space-y-1.5 pl-5 text-zinc-700 dark:text-zinc-300">{children}</ol>
  );
}

function Blockquote({ children }: Props): ReactElement {
  return (
    <blockquote className="mt-6 max-w-3xl border-l-2 border-zinc-200 pl-4 text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
      {children}
    </blockquote>
  );
}

function Table({ children }: Props): ReactElement {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-sm">{children}</table>
    </div>
  );
}

function Th({ children }: Props): ReactElement {
  return <th className={HEAD}>{children}</th>;
}

function Td({ children }: Props): ReactElement {
  return <td className={CELL}>{children}</td>;
}

/** Docs and contracts: the page body's look, plus the Markdown a page body never uses. */
export const DOC_MARKDOWN: Readonly<Record<string, ComponentType<Props & Record<string, unknown>>>> = {
  ...MARKDOWN,
  h1: H1,
  h4: H4,
  ol: Ol,
  blockquote: Blockquote,
  table: Table,
  th: Th,
  td: Td,
};
