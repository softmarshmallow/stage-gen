// Helpers every block shares: the port of the formatting, framing and wording helpers of the
// retired showcase's components and of its inline Markdown. The markup and class strings are the showcase's, literally (Tailwind scans this file; keep them literal).
//
// Two things differ from the Python by necessity:
// - JSX escapes text and attributes itself, so `esc` is only for strings built by hand;
// - a style is an object in React, so a block writes `style={css(ground(picture))}`: the
//   CSS text stays the showcase's, and `css` turns it into the object React writes back out.
//
// Python's round() and float formatting round half to even on the exact binary value, and
// print an integral float as "12.0"; JavaScript does neither, so `pyRound`, `pyFixed` and
// `pyFloat` stand in wherever the Python called round(), formatted with :.Nf, or printed a float.

import {
  Children,
  isValidElement,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react";
import { capitalize, PageError, type Page, type Picture } from "@/lib/page";

/** What every block receives: its MDX props, the bound page, and its MDX children. */
export type BlockProps<P extends object = Record<string, never>> = P & {
  readonly page: Page;
  readonly children?: ReactNode;
};

/** The showcase's MdxError: a page source asked for something its data does not hold. */
export const MdxError = PageError;

// ------------------------------------------------------------------------------ Python numbers

/** The exact decimal expansion of a double, as digits and a point ("3.660000000000000142..."). */
function exactDecimal(value: number): string {
  // toFixed(100) is exact for every value with at most 100 fractional digits, which covers
  // every number a page formats (the smallest is far above 2^-48).
  return Math.abs(value).toFixed(100);
}

/** f"{value:.{digits}f}": round half to even on the exact value, as Python formats floats. */
export function pyFixed(value: number, digits: number): string {
  const exact = exactDecimal(value);
  const point = exact.indexOf(".");
  const whole = exact.slice(0, point);
  const fraction = exact.slice(point + 1);
  const kept = whole + fraction.slice(0, digits);
  const rest = fraction.slice(digits);
  let up = false;
  if (rest[0] > "5") up = true;
  else if (rest[0] === "5") {
    up = /[1-9]/.test(rest.slice(1)) || Number(kept.at(-1) ?? "0") % 2 === 1;
  }
  let digitsOut = kept;
  if (up) {
    const chars = kept.split("");
    let i = chars.length - 1;
    while (i >= 0 && chars[i] === "9") {
      chars[i] = "0";
      i -= 1;
    }
    if (i < 0) chars.unshift("1");
    else chars[i] = String(Number(chars[i]) + 1);
    digitsOut = chars.join("");
  }
  const intPart = digitsOut.slice(0, digitsOut.length - digits).replace(/^0+(?=\d)/, "") || "0";
  const fracPart = digits > 0 ? `.${digitsOut.slice(digitsOut.length - digits)}` : "";
  const negative = value < 0 && /[1-9]/.test(digitsOut);
  return `${negative ? "-" : ""}${intPart}${fracPart}`;
}

/** round(value) or round(value, digits), half to even on the exact value. */
export function pyRound(value: number, digits = 0): number {
  return Number(pyFixed(value, digits));
}

/** str(float): Python's repr of a float, which keeps ".0" on an integral value. */
export function pyFloat(value: number): string {
  if (Number.isInteger(value) && Math.abs(value) < 1e16) return `${value}.0`;
  return String(value).replace(/e([+-])(\d)$/, "e$10$2");
}

// ------------------------------------------------------------------------------ formatting

/** html.escape(str(value), quote=True), for strings a block builds by hand. */
export function esc(value: unknown): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#x27;");
}

export function minutes(seconds: number): string {
  return seconds >= 90 ? `${pyRound(seconds / 60)} min` : `${pyRound(seconds)} s`;
}

export function clock(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined) return null;
  const s = ms / 1000;
  if (s < 1) return "under a second";
  return s < 60 ? `${pyRound(s)} s` : `${Math.floor(s / 60)} min ${Math.trunc(s % 60)} s`;
}

export function money(usd: unknown): string | null {
  return usd === null || usd === undefined || usd === "" ? null : `$${pyFixed(Number(usd), 2)}`;
}

export function size(n: number): string {
  return n >= 1e6 ? `${pyFixed(n / 1e6, 1)} MB` : `${pyFixed(n / 1e3, 0)} KB`;
}

// ------------------------------------------------------------------------------ styles

/** A CSS declaration list ("a:b;c:d") as the style object React renders back to the same text. */
export function css(text: string): CSSProperties {
  const style: Record<string, string> = {};
  for (const declaration of text.split(";")) {
    const colon = declaration.indexOf(":");
    if (colon < 0) continue;
    const property = declaration.slice(0, colon).trim();
    const value = declaration.slice(colon + 1).trim();
    if (!property) continue;
    const key = property.startsWith("--")
      ? property
      : property.replace(/-([a-z])/g, (_, letter: string) => letter.toUpperCase());
    style[key] = value;
  }
  return style as CSSProperties;
}

export const CHECKER =
  "background-color:#fff;background-image:conic-gradient(#e4e4e7 25%,transparent 0 50%,#e4e4e7 0 75%,transparent 0);" +
  "background-size:16px 16px";

/** A picture's plain ground colour, or the checkerboard when it is transparent (CSS text). */
export function ground(picture: Picture): string {
  return picture.alpha ? CHECKER : `background:${picture.bg}`;
}

export function wide(picture: Picture): boolean {
  return picture.width >= picture.height * 1.6;
}

/**
 * A picture on its own ground colour, or a checkerboard when it is transparent.
 *
 * A wide picture, such as a panorama or a tile sheet, keeps its own shape instead of the
 * frame's aspect class, so it is not shrunk into a strip.
 */
export function Framed({ picture, cls }: { picture: Picture; cls: string }): ReactElement {
  let style = ground(picture);
  let classes = cls;
  if (wide(picture)) {
    classes = cls
      .split(/\s+/)
      .filter((c) => c && !c.startsWith("aspect-"))
      .join(" ");
    style += `;aspect-ratio:${picture.width}/${picture.height}`;
  }
  return (
    <div
      className={`${classes} flex items-center justify-center overflow-hidden rounded-sm`}
      style={css(style)}
    >
      <img className="max-h-full max-w-full object-contain" src={picture.src} alt="" loading="lazy" />
    </div>
  );
}

// ------------------------------------------------------------------------------ class strings

export const LINK =
  "jump text-sm text-zinc-500 underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100";
export const CELL = "border-b border-zinc-200 py-3 pr-6 align-top dark:border-zinc-800";
export const HEAD =
  "border-b border-zinc-300 pb-2 pr-6 text-left text-sm font-normal text-zinc-500 dark:border-zinc-700";
export const CLIP =
  "rounded-sm border border-zinc-300 px-2 py-0.5 text-xs text-zinc-600 hover:border-zinc-500 aria-pressed:border-zinc-900 " +
  "aria-pressed:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:aria-pressed:border-zinc-100 " +
  "dark:aria-pressed:text-zinc-100";
export const SEGMENT =
  "rounded-sm border border-zinc-300 px-2.5 py-1 text-xs text-zinc-600 hover:border-zinc-500 aria-pressed:border-zinc-900 " +
  "aria-pressed:bg-zinc-900 aria-pressed:text-white dark:border-zinc-700 dark:text-zinc-400 dark:aria-pressed:border-zinc-100 " +
  "dark:aria-pressed:bg-zinc-100 dark:aria-pressed:text-zinc-900";
export const ACTION =
  "rounded-sm border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 " +
  "dark:text-zinc-300";
export const KBD =
  "rounded-sm border border-zinc-300 px-1 font-sans text-[11px] text-zinc-600 dark:border-zinc-700 dark:text-zinc-400";
export const TOGGLE = "flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400";

// ------------------------------------------------------------------------------ small parts

/** A button that opens a node's record in the graph view. */
export function NodeLink({ page, node }: { page: Page; node: string }): ReactElement {
  return (
    <button className={LINK} data-node={node}>
      {page.titleOf(node)}
    </button>
  );
}

/** One button per clip the model carries; the pressed one is playing. */
export function ClipButtons({ clips, first }: { clips: readonly string[]; first: string }): ReactElement {
  return (
    <>
      {clips.map((name) => (
        <button
          key={name}
          data-clip={name}
          aria-pressed={name === first ? "true" : "false"}
          className={CLIP}
        >
          {capitalize(name.replaceAll("_", " "))}
        </button>
      ))}
    </>
  );
}

export const STATE_WORDS: Readonly<Record<string, string>> = {
  "eyes|rest": "Open",
  "eyes|eyes_half": "Half",
  "eyes|eyes_closed": "Closed",
  "mouth|rest": "Rest",
};

export function stateWords(group: string, state: string): string {
  const known = STATE_WORDS[`${group}|${state}`];
  if (known) return known;
  let rest = state.startsWith(`${group}_`) ? state.slice(group.length + 1) : state;
  rest = rest.startsWith("mouth_") ? rest.slice("mouth_".length) : rest;
  return rest.toUpperCase();
}

// ------------------------------------------------------------------------------ inline Markdown

/** mdx.inline's HTML: escape, then `code`, **bold**, *emphasis* and [links](url). */
function inlineHtml(text: string): string {
  let out = esc(text);
  out = out.replace(/`([^`]+)`/g, '<code class="font-mono text-[0.9em]">$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    '<a class="underline underline-offset-2" href="$2">$1</a>',
  );
  return out;
}

function unescapeHtml(text: string): string {
  return text
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#x27;", "'")
    .replaceAll("&amp;", "&");
}

/**
 * The inline Markdown a prop string may hold (a Guard's `how`, a stage's note), rendered as
 * mdx.inline renders it: the same regular expressions, read back into elements.
 */
export function inline(text: string): ReactNode {
  const html = inlineHtml(text);
  const nodes: ReactNode[] = [];
  const stack: { tag: string; attrs: Record<string, string>; children: ReactNode[] }[] = [];
  const push = (node: ReactNode) => (stack.at(-1)?.children ?? nodes).push(node);
  const pattern = /<(\/?)(code|strong|em|a)((?:\s+[a-z]+="[^"]*")*)>/g;
  let last = 0;
  let key = 0;
  for (const match of html.matchAll(pattern)) {
    if (match.index > last) push(unescapeHtml(html.slice(last, match.index)));
    last = match.index + match[0].length;
    const [, closing, tag, rawAttrs] = match;
    if (!closing) {
      const attrs: Record<string, string> = {};
      for (const [, name, value] of rawAttrs.matchAll(/([a-z]+)="([^"]*)"/g)) {
        attrs[name] = unescapeHtml(value);
      }
      stack.push({ tag, attrs, children: [] });
      continue;
    }
    const open = stack.pop();
    if (open === undefined) continue;
    const props: Record<string, string> = { key: String(key++) };
    if (open.attrs.class) props.className = open.attrs.class;
    if (open.attrs.href) props.href = open.attrs.href;
    const Tag = open.tag as "code" | "strong" | "em" | "a";
    push(<Tag {...props}>{open.children}</Tag>);
  }
  if (last < html.length) push(unescapeHtml(html.slice(last)));
  return <>{nodes}</>;
}

/** mdx.plain: the same inline Markdown as plain text, for copying. */
export function plain(text: string): string {
  let out = text.replace(/`([^`]+)`/g, "$1");
  out = out.replace(
    /\*\*([^*]+)\*\*|\*([^*]+)\*/g,
    (_, bold: string | undefined, em: string | undefined) => bold ?? em ?? "",
  );
  return out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, "$1 ($2)");
}

// ------------------------------------------------------------------------------ MDX children

/** Markdown blocks MDX may hand a component as children. */
const BLOCK_TAGS = new Set([
  "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "pre", "blockquote", "table", "hr",
]);

/**
 * The name a child element was registered under: the component name ("Stat") or the
 * Markdown element ("p", "h2") lib/mdx.ts bound it as; null for anything else.
 */
export function blockName(node: ReactNode): string | null {
  if (!isValidElement(node)) return null;
  if (typeof node.type === "string") return node.type;
  const name = (node.type as { blockName?: unknown }).blockName;
  return typeof name === "string" ? name : null;
}

/** The children as a list, without the whitespace-only strings MDX leaves between blocks. */
export function nodesOf(children: ReactNode): ReactNode[] {
  return Children.toArray(children).filter(
    (child) => !(typeof child === "string" && child.trim() === ""),
  );
}

type AnyElement = ReactElement<{ children?: ReactNode } & Record<string, unknown>>;

/** children_of: the component children, all of which must be `name`; prose is ignored. */
export function childrenOf(children: ReactNode, name: string): AnyElement[] {
  const items = nodesOf(children).filter(
    (child): child is AnyElement => isValidElement(child) && /^[A-Z]/.test(blockName(child) ?? ""),
  );
  if (items.some((child) => blockName(child) !== name)) {
    throw new MdxError(`only <${name}> may appear here`);
  }
  return items;
}

/**
 * text_of: a sentence's content, whether the element held a sentence or a single paragraph
 * block; null (the showcase's "") when it held other blocks or nothing.
 */
export function textOf(children: ReactNode): ReactNode {
  const nodes = nodesOf(children);
  if (nodes.length === 0) return null;
  if (nodes.length === 1 && blockName(nodes[0]) === "p") {
    return (nodes[0] as AnyElement).props.children ?? null;
  }
  if (nodes.some((node) => BLOCK_TAGS.has(blockName(node) ?? ""))) return null;
  return <>{children}</>;
}

/** Plain text of rendered inline content: code, emphasis and links read as plain() reads them. */
export function plainOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(plainOf).join("");
  if (!isValidElement(node)) return "";
  const element = node as AnyElement;
  const inner = plainOf(element.props.children);
  if (blockName(element) === "a" && typeof element.props.href === "string") {
    return `${inner} (${element.props.href})`;
  }
  return inner;
}

// ------------------------------------------------------------------------------ prompts

/** The input a <Ref> names, as reference() checks it. */
export function referenceOf(page: Page, input: string) {
  const source = page.record.inputs[input];
  if (source === undefined) {
    throw new MdxError(
      `<Ref input='${input}'>: the record's inputs are ${Object.keys(page.record.inputs).join(", ")}`,
    );
  }
  return source;
}

/**
 * plain_prompt: the prompt as text to paste. Each reference names the file to attach; a text
 * input is appended in full. `paragraphs` are the <Agent>'s paragraph elements.
 */
export function plainPrompt(page: Page, paragraphs: readonly ReactNode[]): string {
  const lines: string[] = [];
  const appended: string[] = [];
  for (const paragraph of paragraphs) {
    const parts = isValidElement(paragraph)
      ? Children.toArray((paragraph as AnyElement).props.children)
      : [paragraph];
    const words: string[] = [];
    for (const part of parts) {
      if (blockName(part) !== "Ref") {
        words.push(plainOf(part));
        continue;
      }
      const ref = part as AnyElement;
      const source = referenceOf(page, String(ref.props.input));
      const inner = nodesOf(ref.props.children);
      const label = inner.some((node) => BLOCK_TAGS.has(blockName(node) ?? ""))
        ? ""
        : plainOf(inner);
      const file = typeof source.file === "string" ? source.file : null;
      if (source.kind === "text") {
        words.push(label ? `${label} (below)` : "the text below");
        appended.push(String(source.text));
      } else {
        words.push(
          label ? `${label} (attach ${file ?? "your file"})` : `the attached ${file ?? "file"}`,
        );
      }
    }
    lines.push(words.join(""));
  }
  let text = lines.join("\n\n");
  for (const extra of appended) text += `\n\n---\n${extra}`;
  return text;
}

/** A component that may only be read by its parent; rendering it alone is a page error. */
export function onlyInside(parent: string): () => never {
  return () => {
    throw new MdxError(`this element belongs inside <${parent}>`);
  };
}
