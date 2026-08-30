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
}

function collapsedId(domain: string): string {
  return `domain:${domain}`;
}

function contract(
  nodes: readonly LayoutNodeInput[],
  collapsedDomains: ReadonlySet<string>,
): readonly ContractedNode[] {
  const idFor = new Map<string, string>();
  for (const node of nodes) {
    idFor.set(
      node.nodeId,
      collapsedDomains.has(node.domain) ? collapsedId(node.domain) : node.nodeId,
    );
  }
  const contracted = new Map<
    string,
    { domain: string; memberIds: string[]; dependsOn: Set<string> }
  >();
  for (const node of nodes) {
    const id = idFor.get(node.nodeId) ?? node.nodeId;
    const entry = contracted.get(id) ?? {
      domain: node.domain,
      memberIds: [],
      dependsOn: new Set<string>(),
    };
    entry.memberIds.push(node.nodeId);
    for (const dependency of node.dependsOn) {
      const target = idFor.get(dependency) ?? dependency;
      if (target !== id) entry.dependsOn.add(target);
    }
    contracted.set(id, entry);
  }
  return [...contracted.entries()].map(([id, entry]) => ({
    id,
    domain: entry.domain,
    memberIds: entry.memberIds,
    dependsOn: [...entry.dependsOn].sort(),
  }));
}

function longestPathDepths(nodes: readonly ContractedNode[]): Map<string, number> {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const depths = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (id: string): number => {
    const known = depths.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) throw new Error("execution view graph contains a cycle");
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
  const depths = longestPathDepths(contracted);
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
