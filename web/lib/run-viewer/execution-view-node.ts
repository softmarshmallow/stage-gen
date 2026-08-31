// Derived readings of one typed node, kept pure so the renderer stays dumb.
//
// Everything here answers a question the view document implies but does not
// state: what to call a node, which upstream artwork it was shown, and which
// sidecar belongs to one of its artifacts. None of it is stored — the document
// is the source of truth and these are recomputed on every render.

import type {
  ExecutionViewArtifact,
  ExecutionViewAuthoredInput,
  ExecutionViewCard,
  ExecutionViewNode,
  ExecutionViewPort,
  ExecutionViewPortRef,
  ViewArchetype,
} from "./execution-view";

/**
 * The params that tell two instances of the same type apart, most specific
 * first. A motion atlas is disambiguated by its state, a map layer by its
 * layer, and a chip that says only "Motion atlas" says nothing.
 */
export const DISAMBIGUATING_PARAMS: readonly string[] = [
  "state",
  "layer_id",
  "entity_id",
  "actor_id",
  "track_id",
  "map_id",
] as const;

/** Archetypes whose definition is a prompt: the node is told what to make. */
const PROMPTED: readonly ViewArchetype[] = ["image", "matte", "music", "structured", "judge"];

export function isPrompted(archetype: ViewArchetype | null): boolean {
  return archetype !== null && PROMPTED.includes(archetype);
}

/**
 * What to call this node in a heading. The title is the registry's human name;
 * a node whose type the exporter could not join falls back to the tail of its
 * taxonomy path, and only then to the id.
 */
export function nodeHeading(node: ExecutionViewNode): string {
  if (node.title) return node.title;
  const segments = node.typeId.split("/").filter(Boolean);
  if (segments.length >= 2) return segments.slice(-2).join("/");
  return segments[0] ?? node.nodeId;
}

/**
 * What to call this node on a chip: the title, disambiguated by its most
 * specific param. The full node id stays the hover title, so the id is never
 * lost — only moved out of the way.
 */
export function nodeChipLabel(node: ExecutionViewNode): string {
  if (!node.title) return node.nodeId;
  const key = DISAMBIGUATING_PARAMS.find((name) => node.params[name]);
  return key ? `${node.title} · ${node.params[key]}` : node.title;
}

/**
 * The sidecar for one artifact: the port's declared pairing when the node
 * declares one, otherwise the naming convention. The declaration wins because
 * a guess that happens to be right is still a guess.
 */
export function sidecarRefFor(node: ExecutionViewNode, artifactRef: string): string {
  const declared = node.ports.find((port) => port.artifactRef === artifactRef);
  return declared?.sidecarRef ?? `${artifactRef}.meta.json`;
}

/** One derived input, joined against the upstream node that produces it. */
export interface ResolvedReference {
  readonly reference: ExecutionViewPortRef;
  /** The upstream node, when the document declares one. */
  readonly node: ExecutionViewNode | null;
  /** The port the reference names, when that node declares it. */
  readonly port: ExecutionViewPort | null;
  /** The upstream artifact, when the run has actually written it. */
  readonly artifact: ExecutionViewArtifact | null;
}

/**
 * Join a node's card references to the artifacts they point at. An unwritten
 * reference resolves to a port without an artifact — a pending run shows what
 * it will be shown, not an error.
 */
export function resolveReferenceInputs(
  card: ExecutionViewCard | null,
  nodesById: ReadonlyMap<string, ExecutionViewNode>,
): readonly ResolvedReference[] {
  return (card?.referenceInputs ?? []).map((reference) => {
    const upstream = nodesById.get(reference.nodeId) ?? null;
    const port = upstream?.ports.find((entry) => entry.portId === reference.portId) ?? null;
    const artifact =
      port === null
        ? null
        : (upstream?.artifacts.find((entry) => entry.artifactRef === port.artifactRef) ?? null);
    return { reference, node: upstream, port, artifact };
  });
}

/** One authored input, joined against the copy the run published, if any. */
export interface ResolvedAuthoredInput {
  readonly input: ExecutionViewAuthoredInput;
  /**
   * The run's own copy of those bytes, when some node republished the package
   * member into the run. Absent is normal: an authored input lives in the
   * package, and only a recipe that ships it also writes it here.
   */
  readonly artifact: ExecutionViewArtifact | null;
}

/**
 * Join a node's authored inputs to the run's copy of them. Matching is by
 * artifact ref and digest together: same path with different bytes is a
 * different file, and saying otherwise would put the wrong picture on screen.
 */
export function resolveAuthoredInputs(
  card: ExecutionViewCard | null,
  nodes: Iterable<ExecutionViewNode>,
): readonly ResolvedAuthoredInput[] {
  // Materialized once: callers pass a map's values, and a one-shot iterator
  // would be exhausted by the first input and starve every one after it.
  const published = [...nodes];
  return (card?.authoredInputs ?? []).map((input) => {
    for (const node of published) {
      const artifact = node.artifacts.find(
        (entry) => entry.artifactRef === input.ref && entry.sha256 === input.sha256,
      );
      if (artifact) return { input, artifact };
    }
    return { input, artifact: null };
  });
}

/**
 * The port carrying a judge's answer, when the node has written one. Two port
 * ids name that answer today: a review writes a "verdict", a measurement
 * writes a "reading".
 */
export const VERDICT_PORT_IDS: readonly string[] = ["verdict", "reading"] as const;

export function verdictPort(node: ExecutionViewNode): ExecutionViewPort | null {
  if (node.archetype !== "judge" || node.state !== "succeeded") return null;
  const port = node.ports.find((entry) => VERDICT_PORT_IDS.includes(entry.portId));
  if (!port) return null;
  // Only offer the panel for an answer the run actually wrote to disk.
  const present = node.artifacts.some(
    (artifact) => artifact.artifactRef === port.artifactRef && artifact.present,
  );
  return present ? port : null;
}
