// One page's data, and the lookups every block makes against it. This is the port of the
// retired showcase's `Page`: blocks read only this and their
// own props, and a prop that names something the bound example lacks throws at build time.
//
// The showcase built a page from its MDX front matter plus one record. The site builds the
// same thing from the catalog: a workflow page binds its cover example and the workflow's
// manifest, an example page binds that example, and a game page binds the stored game
// example and its entry.json. A workflow without an example still has a page; any lookup
// into its record throws, so only prose renders there.

import type {
  Catalog,
  CatalogWorkflow,
  ExampleEntry,
} from "@stage-gen/ui/contracts/catalog";
import type {
  Currency,
  ExampleNode,
  ExampleTool,
  GameExampleEntry,
  WorkflowExample,
} from "@stage-gen/ui/contracts/example";
import type { JsonObject, JsonValue } from "@stage-gen/ui/contracts/wire";

/** Thrown for anything a page source asks of its data that the data does not hold. */
export class PageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PageError";
  }
}

/** A picture as the example document records it: its own ground colour, and whether it has alpha. */
export interface Picture {
  readonly src: string;
  readonly width: number;
  readonly height: number;
  readonly bg: string;
  readonly alpha?: boolean;
}

export type PageKind = "workflow" | "example" | "game";

/** A link under the promise ("See also: ..."). */
export interface RelatedLink {
  readonly title: string;
  readonly href: string;
}

/** One stage of the node graph: the showcase's `[[stages]]`, with node ids in order. */
export interface PageStep {
  readonly label: string;
  readonly note: string;
  readonly nodes: readonly string[];
}

export interface PageData {
  readonly kind: PageKind;
  /** The route without base path, with its trailing slash: "/workflows/movie-sprite/". */
  readonly route: string;
  /** The staged page source under .catalog/pages/: "workflows/movie-sprite/page.mdx". */
  readonly source: string;
  readonly title: string;
  readonly promise: string;
  readonly footer: string;
  readonly related: readonly RelatedLink[];
  /** Node titles by node id, type id or type-id tail (the showcase's `node_labels`). */
  readonly labels: Readonly<Record<string, string>>;
  /** Titles the workflow's steps give each type id, the fallback after `labels`. */
  readonly typeTitles: Readonly<Record<string, string>>;
  /** Local tools the Models table lists after the models (the showcase's `[[tools]]`). */
  readonly tools: readonly ExampleTool[];
  readonly steps: readonly PageStep[];
  /** The store owner the media is served under: a workflow id or a game id. */
  readonly owner: string | null;
  readonly exampleId: string | null;
  readonly example: WorkflowExample | null;
  readonly currency: Currency | null;
  readonly workflow: CatalogWorkflow | null;
  readonly entry: ExampleEntry | null;
  readonly gameEntry: GameExampleEntry | null;
  /**
   * The node that delivers the result (the showcase's `run.output_node`). The catalog does
   * not record it; it is derived as the one node nothing depends on, or null.
   */
  readonly outputNode: string | null;
  /**
   * The workflow declares a cover example this build does not hold (a clean clone builds
   * with --allow-missing-examples). Its page.mdx binds that example, so the page shows the
   * examples it does hold instead of its body.
   */
  readonly coverMissing: boolean;
}

export const DEFAULT_FOOTER =
  "Every picture on this page comes from one real run of this workflow. Nothing was drawn for it.";

function asObject(value: JsonValue | undefined, label: string): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new PageError(`${label} is not an object`);
  }
  return value as JsonObject;
}

/** Reads a picture object of the example document (`thumb`, `poster`, `pictures[i]`, an input's `picture`). */
export function picture(value: JsonValue | undefined, label = "picture"): Picture {
  const fields = asObject(value, label);
  const { src, width, height, bg, alpha } = fields;
  if (typeof src !== "string" || typeof width !== "number" || typeof height !== "number") {
    throw new PageError(`${label} needs src, width and height`);
  }
  return {
    src,
    width,
    height,
    bg: typeof bg === "string" ? bg : "transparent",
    ...(typeof alpha === "boolean" ? { alpha } : {}),
  };
}

/** Python's str.capitalize(): the first letter upper case, the rest lower case. */
export function capitalize(text: string): string {
  return text.slice(0, 1).toUpperCase() + text.slice(1).toLowerCase();
}

export class Page {
  constructor(
    readonly data: PageData,
    readonly catalog: Catalog,
  ) {}

  /** Whether an example is bound, so example-bound blocks can render. */
  get hasExample(): boolean {
    return this.data.example !== null;
  }

  /** The bound example document; throws on a page without one. */
  get record(): WorkflowExample {
    if (this.data.example === null) {
      throw new PageError(`${this.data.route} has no example, so it cannot show example blocks`);
    }
    return this.data.example;
  }

  node(nodeId: string): ExampleNode {
    const node = this.record.nodes[nodeId];
    if (node === undefined) throw new PageError(`no node '${nodeId}' in this run`);
    return node;
  }

  /** A node's title, as Page.title_of words it: page label, type label, step title, else its type's tail. */
  titleOf(nodeId: string): string {
    const node = this.node(nodeId);
    const tail = node.typeId.split(/[/.]/).at(-1) ?? node.typeId;
    const labels = this.data.labels;
    let label =
      labels[nodeId] ||
      labels[node.typeId] ||
      labels[tail] ||
      this.data.typeTitles[node.typeId] ||
      capitalize(tail.replaceAll("_", " "));
    const round = /_(\d\d)$/.exec(nodeId);
    if (round && Number(round[1]) > 1) label += `, round ${Number(round[1])}`;
    return label;
  }

  metric(name: string): number {
    const metrics = this.record.metrics;
    const value = metrics[name];
    if (value === undefined) {
      throw new PageError(
        `<Stat metric='${name}'>: this run records ${Object.keys(metrics).sort().join(", ")}`,
      );
    }
    return value;
  }

  input(name: string): JsonObject {
    const value = this.record.inputs[name];
    if (value === undefined) {
      throw new PageError(
        `input '${name}': the record's inputs are ${Object.keys(this.record.inputs).join(", ")}`,
      );
    }
    return value;
  }

  output(name: string): JsonObject {
    const value = this.record.outputs[name];
    if (value === undefined) {
      throw new PageError(
        `output '${name}': the record's outputs are ${Object.keys(this.record.outputs).join(", ")}`,
      );
    }
    return value;
  }

  /** The run folder's entry for a run-relative path, for <Files>. */
  treeEntry(path: string) {
    const entry = this.record.tree[path];
    if (entry === undefined) throw new PageError(`<File path='${path}'> is not in this run`);
    return entry;
  }

  modelName(model: string | null): string | null {
    return model ? (this.catalog.modelNames[model] ?? model) : null;
  }

  providerName(provider: string | null): string | null {
    return provider ? (this.catalog.providerNames[provider] ?? provider) : null;
  }
}
