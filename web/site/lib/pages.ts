// Every page the site builds, derived from the catalog alone: the landing cards (amendment
// A1: one ordered list of eight), workflow pages bound to their cover example, example
// pages for examples with their own prose, game example pages, and the docs. Routes call
// these from generateStaticParams, so a page exists exactly when the catalog says so.

import path from "node:path";
import type { Catalog, CatalogExample, CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";
import type { WorkflowExample } from "@stage-gen/ui/contracts/example";
import { loadCatalog, readPageSource } from "./catalog";
import { cliReferenceStaged } from "./cli";
import { href } from "./media";
import {
  DEFAULT_FOOTER,
  Page,
  picture,
  type PageData,
  type PageStep,
  type Picture,
  type RelatedLink,
} from "./page";

// ------------------------------------------------------------------------------ formatting

// The landing's meta line uses the same wording as the blocks; these two are the
// showcase's `minutes` and `money`, kept here so lib/ does not import a block.
function minutes(seconds: number): string {
  return seconds >= 90 ? `${Math.round(seconds / 60)} min` : `${Math.round(seconds)} s`;
}

function money(usd: number | null | undefined): string | null {
  return usd === null || usd === undefined ? null : `$${usd.toFixed(2)}`;
}

// ------------------------------------------------------------------------------ shared bits

/** The one node nothing else depends on: the showcase's `run.output_node`, when it is unique. */
function outputNodeOf(example: WorkflowExample | null): string | null {
  if (example === null) return null;
  const fed = new Set(Object.values(example.nodes).flatMap((node) => node.dependsOn));
  const sinks = Object.keys(example.nodes).filter((id) => !fed.has(id));
  return sinks.length === 1 ? sinks[0] : null;
}

function typeTitlesOf(workflow: CatalogWorkflow): Record<string, string> {
  const titles: Record<string, string> = {};
  for (const step of workflow.steps) {
    for (const member of step.members) titles[member.typeId] = member.title;
  }
  return titles;
}

const tailOf = (typeId: string): string => typeId.split(/[/.]/).at(-1) ?? typeId;

/**
 * A workflow's steps as graph stages, each with its nodes in the example's node order.
 * - An example made with an earlier version names its types in an older namespace
 *   ("spike/character.normalize"), so a node no member names exactly joins the member whose
 *   type id ends the same way ("3d/character/normalize").
 * - A node whose type is in no step (a node the importer derived, such as portrait-motion's
 *   face_crop) joins the step of the node it depends on, or else of a node that depends on it.
 * - A stage never holds a node that waits on a later stage: a node depending on a node of a
 *   later step joins that step (character-3d's second rig, after the bounded recovery).
 */
function workflowSteps(workflow: CatalogWorkflow, example: WorkflowExample | null): PageStep[] {
  const nodes = example === null ? [] : Object.values(example.nodes);
  const stepOfType = new Map<string, number>();
  workflow.steps.forEach((step, index) =>
    step.members.forEach((member) => stepOfType.set(member.typeId, index)),
  );
  const byTail = (typeId: string): number | undefined => {
    for (const [member, index] of stepOfType) if (tailOf(member) === tailOf(typeId)) return index;
    return undefined;
  };
  const stepOf = new Map<string, number>();
  for (const node of nodes) {
    const index = stepOfType.get(node.typeId) ?? byTail(node.typeId);
    if (index !== undefined) stepOf.set(node.id, index);
  }
  for (const node of nodes) {
    if (stepOf.has(node.id)) continue;
    const upstream = node.dependsOn.map((id) => stepOf.get(id)).find((index) => index !== undefined);
    const downstream = nodes
      .filter((other) => other.dependsOn.includes(node.id))
      .map((other) => stepOf.get(other.id))
      .find((index) => index !== undefined);
    const index = upstream ?? downstream;
    if (index !== undefined) stepOf.set(node.id, index);
  }
  for (let moved = true; moved; ) {
    moved = false;
    for (const node of nodes) {
      const own = stepOf.get(node.id);
      if (own === undefined) continue;
      const latest = Math.max(own, ...node.dependsOn.map((id) => stepOf.get(id) ?? own));
      if (latest > own) {
        stepOf.set(node.id, latest);
        moved = true;
      }
    }
  }
  return workflow.steps.map((step, index) => ({
    label: step.label,
    note: step.note,
    nodes: nodes.filter((node) => stepOf.get(node.id) === index).map((node) => node.id),
  }));
}

/** The example's own steps when its entry declares them (made with an earlier version), else the workflow's. */
function stepsOf(workflow: CatalogWorkflow, entry: CatalogExample | null): PageStep[] {
  if (entry !== null && entry.steps.length > 0) {
    return entry.steps.map((step) => ({ label: step.label, note: step.note, nodes: step.members }));
  }
  return workflowSteps(workflow, entry?.example ?? null);
}

function coverOf(workflow: CatalogWorkflow): CatalogExample | null {
  return workflow.examples.find((example) => example.cover && example.example !== null) ?? null;
}

/** Examples that have their own page: present, not the cover, with an examples/<id>.mdx. */
function examplesWithPages(workflow: CatalogWorkflow): CatalogExample[] {
  return workflow.examples.filter(
    (example) =>
      !example.cover &&
      example.example !== null &&
      readPageSource(`workflows/${workflow.id}/examples/${example.id}.mdx`) !== null,
  );
}

function exampleTitle(example: CatalogExample, workflow: CatalogWorkflow): [string, string] {
  // An entry with its own promise carries its own title; otherwise it shows as its workflow.
  return example.promise !== null
    ? [example.title, example.promise]
    : [workflow.manifest.title, workflow.manifest.promise];
}

// ------------------------------------------------------------------------------ routes

export function workflowRoute(id: string): string {
  return `/workflows/${id}/`;
}

export function exampleRoute(workflow: string, example: string): string {
  return `/workflows/${workflow}/${example}/`;
}

export function gameRoute(game: string, example: string): string {
  return `/games/${game}/${example}/`;
}

export function contractRoute(id: string): string {
  return `/workflows/${id}/contract/`;
}

export function docRoute(slug: readonly string[]): string {
  return `/docs/${slug.join("/")}/`;
}

function findWorkflowOrThrow(catalog: Catalog, id: string): CatalogWorkflow {
  const workflow = catalog.workflows.find((entry) => entry.id === id);
  if (workflow === undefined) throw new Error(`no workflow ${id} in the catalog`);
  return workflow;
}

// ------------------------------------------------------------------------------ pages

export function workflowPage(id: string, catalog: Catalog = loadCatalog()): Page {
  const workflow = findWorkflowOrThrow(catalog, id);
  const cover = coverOf(workflow);
  const example = cover?.example ?? null;
  const coverMissing = cover === null && workflow.examples.some((entry) => entry.cover);
  const related: RelatedLink[] = [
    ...workflow.manifest.related.map((other) => ({
      title: findWorkflowOrThrow(catalog, other).manifest.title,
      href: href(workflowRoute(other)),
    })),
    ...examplesWithPages(workflow).map((other) => ({
      title: exampleTitle(other, workflow)[0],
      href: href(exampleRoute(workflow.id, other.id)),
    })),
  ];
  const data: PageData = {
    kind: "workflow",
    route: workflowRoute(id),
    source: `workflows/${id}/page.mdx`,
    title: workflow.manifest.title,
    promise: workflow.manifest.promise,
    footer: cover?.footer ?? DEFAULT_FOOTER,
    related,
    labels: { ...workflow.manifest.labels, ...cover?.labels },
    typeTitles: typeTitlesOf(workflow),
    tools: workflow.manifest.tools,
    steps: stepsOf(workflow, cover),
    owner: example === null ? null : workflow.id,
    exampleId: cover?.id ?? null,
    example,
    currency: cover?.currency ?? null,
    workflow,
    entry: cover,
    gameEntry: null,
    outputNode: outputNodeOf(example),
    coverMissing,
  };
  return new Page(data, catalog);
}

export function examplePage(id: string, exampleId: string, catalog: Catalog = loadCatalog()): Page {
  const workflow = findWorkflowOrThrow(catalog, id);
  const entry = workflow.examples.find((example) => example.id === exampleId);
  if (entry === undefined || entry.example === null) {
    throw new Error(`no present example ${id}/${exampleId} in the catalog`);
  }
  const [title, promise] = exampleTitle(entry, workflow);
  const related: RelatedLink[] = [
    { title: workflow.manifest.title, href: href(workflowRoute(workflow.id)) },
    ...examplesWithPages(workflow)
      .filter((other) => other.id !== exampleId)
      .map((other) => ({
        title: exampleTitle(other, workflow)[0],
        href: href(exampleRoute(workflow.id, other.id)),
      })),
  ];
  const data: PageData = {
    kind: "example",
    route: exampleRoute(id, exampleId),
    source: `workflows/${id}/examples/${exampleId}.mdx`,
    title,
    promise,
    footer: entry.footer ?? DEFAULT_FOOTER,
    related,
    labels: { ...workflow.manifest.labels, ...entry.labels },
    typeTitles: typeTitlesOf(workflow),
    tools: workflow.manifest.tools,
    steps: stepsOf(workflow, entry),
    owner: workflow.id,
    exampleId,
    example: entry.example,
    currency: entry.currency,
    workflow,
    entry,
    gameEntry: null,
    outputNode: outputNodeOf(entry.example),
    coverMissing: false,
  };
  return new Page(data, catalog);
}

export function gamePage(game: string, exampleId: string, catalog: Catalog = loadCatalog()): Page {
  const stored = catalog.gameExamples.find(
    (example) => example.owner === game && example.id === exampleId,
  );
  if (stored === undefined || stored.entry === null) {
    throw new Error(`no game example ${game}/${exampleId} with an entry in the catalog`);
  }
  const entry = stored.entry;
  const related: RelatedLink[] = entry.related.map((other) => {
    const sibling = catalog.gameExamples.find(
      (example) => example.owner === game && example.id === other,
    );
    if (sibling?.entry) return { title: sibling.entry.title, href: href(gameRoute(game, other)) };
    return { title: findWorkflowOrThrow(catalog, other).manifest.title, href: href(workflowRoute(other)) };
  });
  const data: PageData = {
    kind: "game",
    route: gameRoute(game, exampleId),
    source: `games/${game}/${exampleId}/page.mdx`,
    title: entry.title,
    promise: entry.promise,
    footer: entry.footer ?? DEFAULT_FOOTER,
    related,
    labels: entry.labels,
    typeTitles: {},
    tools: entry.tools,
    steps: entry.steps.map((step) => ({ label: step.label, note: step.note, nodes: step.members })),
    owner: game,
    exampleId,
    example: stored.example,
    currency: stored.currency,
    workflow: null,
    entry: null,
    gameEntry: entry,
    outputNode: outputNodeOf(stored.example),
    coverMissing: false,
  };
  return new Page(data, catalog);
}

// ------------------------------------------------------------------------------ enumeration

/**
 * A static export refuses a dynamic route with no params, and a clean clone has no store,
 * so no game example and no example page. Such a route then builds one placeholder path,
 * whose page calls notFound(); isPlaceholder() tells the page.
 */
export const PLACEHOLDER = "_";

function orPlaceholder<P extends Record<string, string>>(params: P[], keys: readonly (keyof P)[]): P[] {
  return params.length > 0
    ? params
    : [Object.fromEntries(keys.map((key) => [key, PLACEHOLDER])) as P];
}

export function isPlaceholder(...values: readonly string[]): boolean {
  return values.every((value) => value === PLACEHOLDER);
}

export function workflowParams(catalog: Catalog = loadCatalog()): { id: string }[] {
  return catalog.workflows.map((workflow) => ({ id: workflow.id }));
}

export function exampleParams(catalog: Catalog = loadCatalog()): { id: string; example: string }[] {
  return orPlaceholder(
    catalog.workflows.flatMap((workflow) =>
      examplesWithPages(workflow).map((example) => ({ id: workflow.id, example: example.id })),
    ),
    ["id", "example"],
  );
}

export function gameParams(catalog: Catalog = loadCatalog()): { game: string; example: string }[] {
  return orPlaceholder(
    catalog.gameExamples
      .filter((example) => example.entry !== null && example.page !== null)
      .map((example) => ({ game: example.owner, example: example.id })),
    ["game", "example"],
  );
}

/** Every example-bound page, keyed "<owner>/<example id>", as the parity harness addresses them. */
export function pageForExample(owner: string, exampleId: string, catalog: Catalog = loadCatalog()): Page {
  if (catalog.gameExamples.some((example) => example.owner === owner && example.id === exampleId)) {
    return gamePage(owner, exampleId, catalog);
  }
  const workflow = findWorkflowOrThrow(catalog, owner);
  return coverOf(workflow)?.id === exampleId
    ? workflowPage(owner, catalog)
    : examplePage(owner, exampleId, catalog);
}

// ------------------------------------------------------------------------------ landing

export interface Card {
  readonly order: number;
  readonly title: string;
  readonly promise: string;
  /** The page the card links to, with base path; null when the example is not present. */
  readonly href: string | null;
  /** The first output's poster, the showcase's card picture; null when the example is absent. */
  readonly hero: Picture | null;
  /** A wide sheet fills the square with its middle instead of shrinking to a strip. */
  readonly heroWide: boolean;
  /** "3 min · about $3.66", or "not built yet" for an absent example. */
  readonly meta: string;
  /** "Made inside the Bellweather example game" on a game-made card; null otherwise. */
  readonly madeInside: string | null;
}

function cardMeta(example: WorkflowExample): string {
  const metrics = example.metrics;
  const cost = metrics.cost_usd ?? metrics.estimated_cost_usd;
  const price = money(cost);
  const parts = [
    metrics.wall_seconds === undefined ? null : minutes(metrics.wall_seconds),
    price && ("cost_usd" in metrics ? "" : "about ") + price,
  ];
  return parts.filter((part): part is string => Boolean(part)).join(" · ");
}

/** The landing's cards: one ordered list, in the catalog's `order` (amendment A1). */
export function landingCards(catalog: Catalog = loadCatalog()): Card[] {
  return catalog.cards.map((card) => {
    let example: WorkflowExample | null;
    let route: string;
    if (card.workflow !== null) {
      const workflow = findWorkflowOrThrow(catalog, card.workflow);
      const entry = workflow.examples.find((candidate) => candidate.id === card.example);
      example = entry?.example ?? null;
      route = entry?.cover ? workflowRoute(workflow.id) : exampleRoute(workflow.id, card.example);
    } else {
      const stored = catalog.gameExamples.find(
        (candidate) => candidate.owner === card.madeBy.id && candidate.id === card.example,
      );
      example = stored?.example ?? null;
      route = gameRoute(card.madeBy.id, card.example);
    }
    const first = example === null ? undefined : Object.values(example.outputs)[0];
    const hero =
      first === undefined || first.poster === undefined
        ? null
        : picture(first.poster, `${card.example} poster`);
    return {
      order: card.order,
      title: card.title,
      promise: card.promise,
      href: card.present && example !== null ? href(route) : null,
      hero,
      heroWide: hero !== null && hero.width >= hero.height * 1.6,
      meta: example === null ? "not built yet" : cardMeta(example),
      madeInside:
        card.madeInside === null ? null : `Made inside the ${card.madeInside} example game`,
    };
  });
}

// ------------------------------------------------------------------------------ docs

export interface DocPage {
  readonly slug: readonly string[];
  readonly title: string;
  /**
   * What the page renders: a staged Markdown doc, the generated reference of one workflow,
   * or the generated CLI reference.
   */
  readonly kind: "markdown" | "workflow" | "cli";
  /** The staged Markdown source under .catalog/pages/, for a Markdown doc. */
  readonly source: string | null;
  /** Where that Markdown lives in the checkout; its relative links resolve against it. */
  readonly path: string | null;
  /** The workflow a generated reference page describes. */
  readonly workflow: string | null;
}

/** One staged doc, as scripts/site.py lists it in .catalog/pages/docs/index.json. */
interface StagedDoc {
  readonly slug: string;
  readonly title: string;
  readonly path: string;
}

function stagedDocs(): StagedDoc[] {
  const index = readPageSource("docs/index.json");
  if (index === null) return [];
  const entries = JSON.parse(index) as unknown;
  if (!Array.isArray(entries)) throw new Error("docs/index.json is not a list");
  return entries.map((entry: unknown, i) => {
    const fields = entry as Record<string, unknown>;
    if (typeof fields.slug !== "string" || typeof fields.title !== "string" || typeof fields.path !== "string") {
      throw new Error(`docs/index.json[${i}] needs a slug, a title and a path`);
    }
    return { slug: fields.slug, title: fields.title, path: fields.path };
  });
}

/** The staged guides in SITE_DOCS order, the CLI reference, then every workflow's reference. */
export function docPages(catalog: Catalog = loadCatalog()): DocPage[] {
  return [
    ...stagedDocs().map((doc) => ({
      slug: [doc.slug],
      title: doc.title,
      kind: "markdown" as const,
      source: `docs/${doc.slug}.md`,
      path: doc.path,
      workflow: null,
    })),
    ...(cliReferenceStaged()
      ? [{ slug: ["cli"], title: "CLI reference", kind: "cli" as const, source: null, path: null, workflow: null }]
      : []),
    ...catalog.workflows.map((workflow) => ({
      slug: ["workflows", workflow.id],
      title: workflow.manifest.title,
      kind: "workflow" as const,
      source: null,
      path: null,
      workflow: workflow.id,
    })),
  ];
}

export function findDoc(slug: readonly string[], catalog: Catalog = loadCatalog()): DocPage {
  const doc = docPages(catalog).find((candidate) => candidate.slug.join("/") === slug.join("/"));
  if (doc === undefined) throw new Error(`no doc ${slug.join("/")}`);
  return doc;
}

/**
 * Where a relative link of a staged doc leads on the site: the route of the doc or workflow
 * contract it names, with its fragment, or null when the site does not publish its target.
 * `from` is the doc's checkout path ("docs/viewer.md").
 */
export function docLink(from: string, target: string, catalog: Catalog = loadCatalog()): string | null {
  const [file, fragment] = target.split("#", 2) as [string, string | undefined];
  const hash = fragment ? `#${fragment}` : "";
  if (file === "") return hash;
  const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(from), file));
  const doc = stagedDocs().find((entry) => entry.path === resolved);
  if (doc !== undefined) return href(docRoute([doc.slug])) + hash;
  const workflow = catalog.workflows.find(
    (entry) => entry.sourceFolder !== null && `${entry.sourceFolder}/contract.md` === resolved,
  );
  if (workflow !== undefined) return href(contractRoute(workflow.id)) + hash;
  return null;
}
