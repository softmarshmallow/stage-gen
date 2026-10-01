// Page sources compiled with @mdx-js/mdx and remark-gfm, rendered with the block set bound
// to one page. React context does not reach server components, so each page gets its own
// component map: makeComponents(page) closes every block over that page, and checks a
// block's props before it renders it, the way the showcase's render_element did:
// - an unknown component name throws (MDX itself refuses a name the map lacks);
// - an unknown prop, a prop of the wrong type, or a missing required prop throws;
// - a prop that names a node, metric, output or input the bound example lacks throws.
// A prop whose name starts with "_" is internal: a parent block passes it to a child it
// clones (React renders children after the parent returns, so the showcase's page.frame_box
// and page.refs become props), and it is passed through unchecked.

import { evaluate, type RunOptions } from "@mdx-js/mdx";
import { createElement, type ComponentType, type ReactNode } from "react";
import * as runtime from "react/jsx-runtime";
import remarkGfm from "remark-gfm";
import { BLOCKS, NAMED_PROPS, type BlockSpec, type PropKind } from "@/blocks";
import { DOC_MARKDOWN, MARKDOWN } from "@/blocks/markdown";
import { readPageSource } from "./catalog";
import { PageError, type Page } from "./page";

// MDX hands each component its props and children, and a component map may hold any
// component; `any` is the honest type of that map's values.
type AnyComponent = ComponentType<any>;
export type MdxComponents = Record<string, AnyComponent>;
export type MdxContent = ComponentType<{ components?: MdxComponents }>;

/** A component of the map, tagged with the name it is bound under (blocks/shared blockName). */
export type BoundComponent = AnyComponent & { blockName: string };

function tag<T extends AnyComponent>(component: T, name: string): T & { blockName: string } {
  return Object.assign(component, { blockName: name, displayName: name });
}

// ------------------------------------------------------------------------------ prop checks

function kindOf(value: unknown): PropKind | "other" {
  if (typeof value === "string") return "string";
  if (Array.isArray(value)) return "list";
  if (typeof value === "number" && Number.isInteger(value)) return "int";
  return "other";
}

const KIND_WORDS: Record<PropKind, string> = { string: "str", list: "list", int: "int" };

function checkProps(name: string, spec: BlockSpec, props: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(props)) {
    if (key === "children" || key.startsWith("_")) continue;
    const kind = spec.props[key];
    if (kind === undefined) throw new PageError(`<${name}> has no prop '${key}'`);
    if (kindOf(value) !== kind) throw new PageError(`<${name} ${key}> must be ${KIND_WORDS[kind]}`);
  }
  for (const key of spec.required) {
    if (!(key in props)) throw new PageError(`<${name}> needs '${key}'`);
  }
}

function checkNames(page: Page, name: string, props: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(props)) {
    const names = NAMED_PROPS[key];
    if (names === undefined || typeof value !== "string") continue;
    try {
      if (names === "node") page.node(value);
      else if (names === "metric") page.metric(value);
      else if (names === "output") page.output(value);
      else page.input(value);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new PageError(`<${name} ${key}='${value}'> on ${page.data.route}: ${reason}`);
    }
  }
}

// ------------------------------------------------------------------------------ binding

/** Every showcase component and Markdown element, bound to one page. */
export function makeComponents(page: Page): MdxComponents {
  const components: MdxComponents = {};
  for (const [name, element] of Object.entries(MARKDOWN)) {
    components[name] = tag((props: Record<string, unknown>) => createElement(element, props), name);
  }
  for (const [name, spec] of Object.entries(BLOCKS)) {
    components[name] = tag((props: Record<string, unknown>) => {
      checkProps(name, spec, props);
      checkNames(page, name, props);
      return createElement(spec.render, { ...props, page });
    }, name);
  }
  return components;
}

/** The docs' and contracts' Markdown elements; no blocks, since no example is bound. */
export function docComponents(): MdxComponents {
  const components: MdxComponents = {};
  for (const [name, element] of Object.entries(DOC_MARKDOWN)) {
    components[name] = tag((props: Record<string, unknown>) => createElement(element, props), name);
  }
  return components;
}

// ------------------------------------------------------------------------------ compiling

interface TextNode {
  type: string;
  value?: string;
  url?: string;
  children?: TextNode[];
}

/**
 * The showcase joined a paragraph's lines with one space. MDX keeps the line breaks in its
 * text; this turns each soft break of prose and inline code back into that space.
 */
function remarkJoinLines() {
  const visit = (node: TextNode): void => {
    if ((node.type === "text" || node.type === "inlineCode") && typeof node.value === "string") {
      node.value = node.value.replace(/[ \t]*\n[ \t]*/g, " ");
    }
    node.children?.forEach(visit);
  };
  return (tree: TextNode) => visit(tree);
}

/** Where a doc's relative link leads on the site, or null when the site does not publish it. */
export type LinkResolver = (target: string) => string | null;

/** A link with a scheme ("https:", "mailto:") or a root path is left as it is. */
const ABSOLUTE = /^(?:[a-z][a-z0-9+.-]*:|\/)/i;

/**
 * A doc is written for the checkout, so its relative links name files beside it. Each one is
 * pointed at the page the site builds for its target; a link to a file the site does not
 * publish keeps its words and loses the link, instead of leading nowhere.
 */
function remarkDocLinks(resolve: LinkResolver) {
  const visit = (node: TextNode): void => {
    node.children = node.children?.flatMap((child) => {
      if (child.type === "link" && typeof child.url === "string" && !ABSOLUTE.test(child.url)) {
        const target = resolve(child.url);
        if (target === null) return child.children ?? [];
        child.url = target;
      }
      return [child];
    });
    node.children?.forEach(visit);
  };
  return (tree: TextNode) => visit(tree);
}

const compiled = new Map<string, Promise<MdxContent>>();

/**
 * A page source compiled to a component; `md` for plain Markdown (docs, contracts). A doc
 * passes its checkout path and a resolver for its relative links (`links`).
 */
export function compileSource(
  source: string,
  format: "mdx" | "md" = "mdx",
  links: { readonly from: string; readonly resolve: LinkResolver } | null = null,
): Promise<MdxContent> {
  const key = `${format}\0${links?.from ?? ""}\0${source}`;
  let content = compiled.get(key);
  if (content === undefined) {
    content = evaluate(source, {
      ...(runtime as unknown as RunOptions),
      format,
      remarkPlugins: links === null ? [remarkGfm, remarkJoinLines] : [remarkGfm, remarkJoinLines, [remarkDocLinks, links.resolve]],
      development: false,
    }).then((module) => module.default as unknown as MdxContent);
    compiled.set(key, content);
  }
  return content;
}

/** A staged page source by its path under .catalog/pages/; throws when it was not staged. */
export function pageSource(relative: string): string {
  const source = readPageSource(relative);
  if (source === null) {
    throw new PageError(`${relative} is not staged; run \`uv run python scripts/site.py build\``);
  }
  return source;
}

/** A page's MDX body, rendered with the blocks bound to that page. */
export async function renderBody(page: Page): Promise<ReactNode> {
  const Content = await compileSource(pageSource(page.data.source));
  return createElement(Content, { components: makeComponents(page) });
}

/**
 * A staged Markdown file (a doc or a contract), rendered with the docs' elements. A doc names
 * its checkout path and link resolver, so its relative links lead to the site's pages.
 */
export async function renderMarkdown(
  relative: string,
  links: { readonly from: string; readonly resolve: LinkResolver } | null = null,
): Promise<ReactNode> {
  const Content = await compileSource(pageSource(relative), "md", links);
  return createElement(Content, { components: docComponents() });
}
