// Pure layered-DAG layout for the run viewer.
//
// Columns are longest-path depth from the roots; rows are domain lanes in
// first-appearance order. Layout is computed on every load from the document
// alone — a read-only viewer that persists hand-layout has quietly become an
// editor, so nothing here is stored.
//
// Collapsing is a pre-layout graph transform: every node of a collapsed
// domain contracts into one super-node and the renderer stays dumb.

export interface LayoutNodeInput {
  readonly nodeId: string;
  readonly domain: string;
  readonly dependsOn: readonly string[];
  /** The subset of dependsOn that orders execution without carrying lineage. */
  readonly barrierOnly?: readonly string[];
}

export interface PlacedNode {
  readonly id: string;
  readonly domain: string;
  /** Node ids this chip stands for: one for a plain node, many when collapsed. */
  readonly memberIds: readonly string[];
  readonly column: number;
  readonly x: number;
  readonly y: number;
}

export interface PlacedEdge {
  readonly from: string;
  readonly to: string;
  /** True when this edge only orders execution: a cache barrier, not lineage. */
  readonly barrier: boolean;
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
}

export interface DomainLane {
  readonly domain: string;
  readonly y: number;
  readonly height: number;
  readonly nodeCount: number;
}

export interface GraphLayout {
  readonly width: number;
  readonly height: number;
  readonly chipWidth: number;
  readonly chipHeight: number;
  readonly nodes: readonly PlacedNode[];
  readonly edges: readonly PlacedEdge[];
  readonly lanes: readonly DomainLane[];
}

export const CHIP_WIDTH = 172;
export const CHIP_HEIGHT = 32;
const COLUMN_GAP = 56;
const ROW_GAP = 8;
const LANE_HEADER = 22;
const LANE_GAP = 14;
const PADDING = 16;

interface ContractedNode {
  readonly id: string;
  readonly domain: string;
  readonly memberIds: readonly string[];
  readonly dependsOn: readonly string[];
  /** Contracted edges that stayed barriers: every edge folded in was one. */
  readonly barrierDependsOn: ReadonlySet<string>;
}

function collapsedId(domain: string): string {
  return `domain:${domain}`;
}

function contract(
  nodes: readonly LayoutNodeInput[],
  collapsedDomains: ReadonlySet<string>,
): readonly ContractedNode[] {
  // A one-node domain gains nothing from contraction and loses its identity:
  // its "super-chip" would carry a synthetic id no inspector can resolve.
  const members = new Map<string, number>();
  for (const node of nodes) {
    members.set(node.domain, (members.get(node.domain) ?? 0) + 1);
  }
  const contractible = new Set(
    [...collapsedDomains].filter((domain) => (members.get(domain) ?? 0) > 1),
  );
  const idFor = new Map<string, string>();
  for (const node of nodes) {
    idFor.set(
      node.nodeId,
      contractible.has(node.domain) ? collapsedId(node.domain) : node.nodeId,
    );
  }
  const contracted = new Map<
    string,
    { domain: string; memberIds: string[]; dependsOn: Map<string, boolean> }
  >();
  for (const node of nodes) {
    const id = idFor.get(node.nodeId) ?? node.nodeId;
    const barriers = new Set(node.barrierOnly ?? []);
    const entry = contracted.get(id) ?? {
      domain: node.domain,
      memberIds: [],
      dependsOn: new Map<string, boolean>(),
    };
    entry.memberIds.push(node.nodeId);
    for (const dependency of node.dependsOn) {
      const target = idFor.get(dependency) ?? dependency;
      if (target === id) continue;
      // Collapsing merges edges: the contracted edge is a barrier only when
      // every edge folded into it was one. A single lineage edge makes it
      // lineage, because that is what the pair actually carries.
      const barrier = barriers.has(dependency) && (entry.dependsOn.get(target) ?? true);
      entry.dependsOn.set(target, barrier);
    }
    contracted.set(id, entry);
  }
  return [...contracted.entries()].map(([id, entry]) => ({
    id,
    domain: entry.domain,
    memberIds: entry.memberIds,
    dependsOn: [...entry.dependsOn.keys()].sort(),
    barrierDependsOn: new Set(
      [...entry.dependsOn.entries()].filter(([, barrier]) => barrier).map(([target]) => target),
    ),
  }));
}

function longestPathDepths(
  nodes: readonly ContractedNode[],
  { tolerateCycles }: { tolerateCycles: boolean },
): Map<string, number> {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const depths = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (id: string): number => {
    const known = depths.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) {
      // Contracting a domain can legally fold an acyclic graph into a cyclic
      // one (room -> hotspots -> room). The document itself is validated
      // acyclic, so inside a contraction a back-edge is a layout artifact:
      // break it here instead of crashing the viewer.
      if (tolerateCycles) return 0;
      throw new Error("execution view graph contains a cycle");
    }
    visiting.add(id);
    const node = byId.get(id);
    const depth =
      node === undefined || node.dependsOn.length === 0
        ? 0
        : 1 + Math.max(...node.dependsOn.map(depthOf));
    visiting.delete(id);
    depths.set(id, depth);
    return depth;
  };
  for (const node of nodes) depthOf(node.id);
  return depths;
}

export function layoutExecutionGraph(
  nodes: readonly LayoutNodeInput[],
  collapsedDomains: ReadonlySet<string> = new Set(),
): GraphLayout {
  const contracted = contract(nodes, collapsedDomains);
  const depths = longestPathDepths(contracted, {
    tolerateCycles: collapsedDomains.size > 0,
  });
  const columnCount = contracted.length === 0 ? 0 : 1 + Math.max(...depths.values());

  const laneOrder: string[] = [];
  const laneMinDepth = new Map<string, number>();
  for (const node of contracted) {
    const depth = depths.get(node.id) ?? 0;
    const known = laneMinDepth.get(node.domain);
    if (known === undefined) laneMinDepth.set(node.domain, depth);
    else if (depth < known) laneMinDepth.set(node.domain, depth);
  }
  for (const domain of [...laneMinDepth.keys()].sort(
    (a, b) => (laneMinDepth.get(a) ?? 0) - (laneMinDepth.get(b) ?? 0) || a.localeCompare(b),
  )) {
    laneOrder.push(domain);
  }

  const placed: PlacedNode[] = [];
  const lanes: DomainLane[] = [];
  let laneY = PADDING;
  for (const domain of laneOrder) {
    const laneNodes = contracted
      .filter((node) => node.domain === domain)
      .sort((a, b) => (depths.get(a.id) ?? 0) - (depths.get(b.id) ?? 0) || a.id.localeCompare(b.id));
    const rowsPerColumn = new Map<number, number>();
    let laneRows = 1;
    for (const node of laneNodes) {
      const column = depths.get(node.id) ?? 0;
      const row = rowsPerColumn.get(column) ?? 0;
      rowsPerColumn.set(column, row + 1);
      if (row + 1 > laneRows) laneRows = row + 1;
      placed.push({
        id: node.id,
        domain,
        memberIds: node.memberIds,
        column,
        x: PADDING + column * (CHIP_WIDTH + COLUMN_GAP),
        y: laneY + LANE_HEADER + row * (CHIP_HEIGHT + ROW_GAP),
      });
    }
    const laneHeight = LANE_HEADER + laneRows * (CHIP_HEIGHT + ROW_GAP) - ROW_GAP;
    lanes.push({ domain, y: laneY, height: laneHeight, nodeCount: laneNodes.length });
    laneY += laneHeight + LANE_GAP;
  }

  const positionById = new Map(placed.map((node) => [node.id, node]));
  const edges: PlacedEdge[] = [];
  for (const node of contracted) {
    const target = positionById.get(node.id);
    if (!target) continue;
    for (const dependency of node.dependsOn) {
      const source = positionById.get(dependency);
      if (!source) continue;
      edges.push({
        from: dependency,
        to: node.id,
        barrier: node.barrierDependsOn.has(dependency),
        x1: source.x + CHIP_WIDTH,
        y1: source.y + CHIP_HEIGHT / 2,
        x2: target.x,
        y2: target.y + CHIP_HEIGHT / 2,
      });
    }
  }

  return {
    width: PADDING * 2 + Math.max(0, columnCount * (CHIP_WIDTH + COLUMN_GAP) - COLUMN_GAP),
    height: laneY - LANE_GAP + PADDING,
    chipWidth: CHIP_WIDTH,
    chipHeight: CHIP_HEIGHT,
    nodes: placed,
    edges,
    lanes,
  };
}
