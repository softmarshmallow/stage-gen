// A workflow's offline sample plan, shaped as a run view so the run viewer can draw it.
//
// The catalog carries the graph each workflow plans from its committed sample inputs,
// with no provider and nothing run. Every node is pending, each node's lane is the step
// that places its type, and the fields a plan cannot know (timings, artifacts, cache
// keys) are empty; the plan panel never shows them.

import type { Catalog, CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";
import {
  type ExecutionView,
  type ExecutionViewNode,
  VIEW_ARCHETYPES,
  type ViewArchetype,
} from "@stage-gen/ui/contracts/run-view";

/** The workflow and plan an offline view was drawn from. */
export interface PlanContext {
  readonly workflowTitle: string;
  readonly kind: string;
  readonly topologySha256: string;
  readonly operationCounts: Readonly<Record<string, number>>;
  /** Each step's one-line note, by step label: a plan node's lane is its step. */
  readonly stepNotes: Readonly<Record<string, string>>;
  readonly modelNames: Readonly<Record<string, string>>;
  readonly providerNames: Readonly<Record<string, string>>;
}

/** The lane of a node whose type no step places. */
export const UNPLACED_STEP = "other";

function archetypeOf(value: string | null): ViewArchetype | null {
  return value !== null && (VIEW_ARCHETYPES as readonly string[]).includes(value)
    ? (value as ViewArchetype)
    : null;
}

export function samplePlanView(
  workflow: CatalogWorkflow,
  catalog: Catalog,
): { readonly view: ExecutionView; readonly plan: PlanContext } | null {
  const sample = workflow.samplePlan;
  if (sample === null) return null;
  const stepOf = new Map<string, string>();
  for (const step of workflow.steps) {
    for (const member of step.members) stepOf.set(member.typeId, step.label);
  }
  const nodes: ExecutionViewNode[] = sample.nodes.map((planned) => ({
    nodeId: planned.id,
    typeId: planned.typeId,
    title: planned.title,
    archetype: archetypeOf(planned.archetype),
    domain: stepOf.get(planned.typeId) ?? UNPLACED_STEP,
    description: "",
    params: {},
    dependsOn: planned.dependsOn,
    barrierOnly: [],
    operation: planned.operation,
    resourceId: "",
    provider: planned.provider,
    model: planned.model,
    retryOwner: "",
    maxAttempts: 1,
    inputSha256: [],
    cacheKey: "",
    ports: [],
    card: null,
    templateId: null,
    estimatedDurationSeconds: 0,
    estimatedCostLowUsd: 0,
    estimatedCostHighUsd: 0,
    state: "pending",
    startedOffsetMs: null,
    endedOffsetMs: null,
    queueMs: null,
    durationMs: null,
    cache: null,
    attempts: null,
    providerOperations: null,
    knownCostUsd: null,
    error: null,
    blockedBy: [],
    artifacts: [],
  }));
  const view: ExecutionView = {
    subject: { kind: sample.kind, recipe: null, pipelineId: null, title: workflow.manifest.title, fields: {} },
    graphSha256: sample.topologySha256,
    topologySha256: sample.topologySha256,
    invocationId: null,
    runState: "planned",
    traceModifiedAt: null,
    durationMs: null,
    knownCostUsd: null,
    stateCounts: { pending: nodes.length, running: 0, succeeded: 0, failed: 0, skipped: 0 },
    nodes,
    gaps: [],
  };
  return {
    view,
    plan: {
      workflowTitle: workflow.manifest.title,
      kind: sample.kind,
      topologySha256: sample.topologySha256,
      operationCounts: sample.operationCounts,
      stepNotes: Object.fromEntries(workflow.steps.map((step) => [step.label, step.note])),
      modelNames: catalog.modelNames,
      providerNames: catalog.providerNames,
    },
  };
}
