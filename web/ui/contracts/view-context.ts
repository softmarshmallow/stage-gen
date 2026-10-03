// gnode views: an HTML template and a read-only context, shown in a sandboxed frame.
//
// `view-contexts.json` (`gnode-view-contexts-v1`) sits beside a derived run view. Each
// context (`gnode-view-context-v1`) is what the view's `context()` returns: the `step` it
// shows (path, title, status, take, cost and every resolved `with` value), its `inputs`
// and `outputs` files, its `facts` and its `run`. A file is `{kind, digest, size, key,
// ref, facts}`, `ref` being where the run folder keeps it for the view; a small JSON file
// carries its parsed `value` too. The viewer adds each file's `url` and hands the context
// to the frame through `/_gnode/view.js`; the frame can do nothing but draw it.

import { artifactReference } from "./artifact-preview";

export const VIEW_CONTEXTS_KIND = "gnode-view-contexts-v1";
export const VIEW_CONTEXT_KIND = "gnode-view-context-v1";

export interface ViewContext {
  readonly kind: typeof VIEW_CONTEXT_KIND;
  readonly scope: "node";
  readonly nodeId: string;
  readonly title: string;
  /** Run-relative path of the view's HTML template. */
  readonly template: string;
  /** The context as the frame receives it, files' `url` still to be added. */
  readonly document: Readonly<Record<string, unknown>>;
}

export interface ViewContexts {
  /** Origins a view may load from besides the run's own files. */
  readonly viewOrigins: readonly string[];
  readonly views: readonly ViewContext[];
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new Error(`${label} must be an object`);
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be text`);
  return value;
}

/** Every file in a context value has a portable run-local `ref`. */
function checkFiles(value: unknown, label: string): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => checkFiles(item, `${label}[${index}]`));
    return;
  }
  if (value === null || typeof value !== "object") return;
  const record = value as Record<string, unknown>;
  if (typeof record.ref === "string" && typeof record.digest === "string") {
    artifactReference(record.ref, `${label}.ref`);
    return;
  }
  for (const [key, item] of Object.entries(record)) checkFiles(item, `${label}.${key}`);
}

export function parseViewContexts(value: unknown): ViewContexts {
  const record = object(value, "view contexts");
  if (record.kind !== VIEW_CONTEXTS_KIND)
    throw new Error(`unsupported view contexts: expected ${VIEW_CONTEXTS_KIND}`);
  const origins = record.view_origins ?? [];
  if (!Array.isArray(origins)) throw new Error("view_origins must be a list");
  const viewOrigins = origins.map((origin, index) => {
    const url = new URL(text(origin, `view_origins[${index}]`));
    if (url.protocol !== "https:" || url.origin !== origin)
      throw new Error(`view_origins[${index}] must be an https origin`);
    return url.origin;
  });
  if (!Array.isArray(record.views)) throw new Error("views must be a list");
  const views = record.views.map((item, index): ViewContext => {
    const label = `views[${index}]`;
    const view = object(item, label);
    if (view.kind !== VIEW_CONTEXT_KIND) throw new Error(`${label} must be ${VIEW_CONTEXT_KIND}`);
    const template = artifactReference(view.template, `${label}.template`);
    if (!/^views\/[0-9a-f]{64}\.html$/.test(template))
      throw new Error(`${label}.template must be a view template the run keeps`);
    checkFiles(view.inputs, `${label}.inputs`);
    checkFiles(view.outputs, `${label}.outputs`);
    checkFiles(object(view.step, `${label}.step`).with, `${label}.step.with`);
    return Object.freeze({
      kind: VIEW_CONTEXT_KIND,
      scope: "node",
      nodeId: text(view.node_id, `${label}.node_id`),
      title: text(object(view.step, `${label}.step`).title, `${label}.step.title`),
      template,
      document: Object.freeze({ ...view }),
    });
  });
  return Object.freeze({ viewOrigins: Object.freeze(viewOrigins), views: Object.freeze(views) });
}

/** The context the frame receives: every file given the URL it is served at. */
export function withUrls(context: ViewContext, urlFor: (ref: string) => string): unknown {
  const visit = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(visit);
    if (value === null || typeof value !== "object") return value;
    const record = value as Record<string, unknown>;
    if (typeof record.ref === "string" && typeof record.digest === "string")
      return { ...record, url: urlFor(record.ref) };
    return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, visit(item)]));
  };
  return visit(context.document);
}

/** Where a host serves the module a view imports its context from. */
export const VIEW_HELPER_PATH = "/_gnode/view.js";

/**
 * `import { context } from "/_gnode/view.js"`: the step a view shows, as data. The view
 * asks its host once, and every call returns the same frozen context.
 */
export const VIEW_HELPER_SOURCE = `// gnode view helper: the step this view shows, read-only.
let asked;
export function context() {
  asked ??= new Promise((resolve) => {
    addEventListener("message", function receive(event) {
      if (event.source !== parent || event.data?.kind !== "${VIEW_CONTEXT_KIND}") return;
      removeEventListener("message", receive);
      resolve(Object.freeze(event.data));
    });
    parent.postMessage({ kind: "gnode-view-ready" }, "*");
  });
  return asked;
}
`;

/** The policy a view template is served under: it runs, and reaches only what it is shown. */
export function viewPolicy(self: string, origins: readonly string[]): string {
  const extra = origins.join(" ");
  return [
    "sandbox allow-scripts",
    "default-src 'none'",
    `script-src 'unsafe-inline' ${self}${VIEW_HELPER_PATH} ${extra}`.trim(),
    `style-src 'unsafe-inline' ${extra}`.trim(),
    `img-src ${self} data: blob: ${extra}`.trim(),
    `media-src ${self} blob: ${extra}`.trim(),
    `font-src ${extra || "'none'"}`,
    `connect-src ${self} ${extra}`.trim(),
  ].join("; ");
}
