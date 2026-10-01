"use client";

// What the floating panel shows for an offline plan: the plan's own facts when nothing
// is selected, otherwise what one planned node is for. A plan has run nothing, so there
// are no timings, artifacts or verdicts to show — only the step a node belongs to, what
// it does, and which provider and model the plan bound it to.

import { cx, metaLine } from "@/app/ui";
import type { ExecutionView, ExecutionViewNode } from "@stage-gen/ui/contracts/run-view";
import { nodeHeading } from "@/lib/run-viewer/execution-view-node";
import type { PlanContext } from "@/lib/run-viewer/plan-view";

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)] gap-2 border-b border-border px-2 py-1 text-xs last:border-b-0">
      <dt className="text-dim">{term}</dt>
      <dd className="m-0 wrap-anywhere">{children}</dd>
    </div>
  );
}

export function PlanFacts({ view, plan }: { view: ExecutionView; plan: PlanContext | null }) {
  const counts = Object.entries(plan?.operationCounts ?? {});
  return (
    <div className="p-3 text-xs">
      <p className={cx(metaLine, "mb-2")}>
        Planned offline from the workflow&apos;s committed sample inputs. Nothing was run and
        nothing was paid for.
      </p>
      <dl className="m-0 border border-border">
        {plan ? <Fact term="workflow">{plan.workflowTitle}</Fact> : null}
        <Fact term="graph">{plan?.kind ?? view.subject.kind}</Fact>
        <Fact term="nodes">{view.nodes.length}</Fact>
        {counts.length > 0 ? (
          <Fact term="operations">
            {counts.map(([operation, count]) => `${operation} ${count}`).join(" · ")}
          </Fact>
        ) : null}
        {plan ? <Fact term="topology">{plan.topologySha256.slice(0, 12)}…</Fact> : null}
      </dl>
      <p className="mt-4 text-dim">Click a node to see what it is for.</p>
    </div>
  );
}

export function PlanNodeFacts({
  node,
  plan,
  onSelect,
}: {
  node: ExecutionViewNode;
  plan: PlanContext | null;
  onSelect: (nodeId: string) => void;
}) {
  const note = plan?.stepNotes[node.domain];
  const provider = node.provider ? (plan?.providerNames[node.provider] ?? node.provider) : null;
  const model = node.model ? (plan?.modelNames[node.model] ?? node.model) : null;
  return (
    <div className="p-3 text-xs">
      <p className={cx(metaLine, "mb-1")}>
        planned · {node.archetype ?? "unregistered"} · {node.domain}
      </p>
      <h3 className="mt-0 mb-0.5 text-sm font-semibold">{nodeHeading(node)}</h3>
      <p className="m-0 truncate text-[11px] text-dim" title={node.typeId}>
        {node.typeId}
      </p>
      {note ? <p className="mt-1.5 mb-2 text-dim">{note}</p> : null}
      <dl className="m-0 mt-2 border border-border">
        <Fact term="node">{node.nodeId}</Fact>
        <Fact term="operation">
          {node.operation}
          {provider ? ` · ${provider}${model ? ` / ${model}` : ""}` : ""}
        </Fact>
        {node.dependsOn.length > 0 ? (
          <Fact term="depends on">
            {node.dependsOn.map((id) => (
              <button
                key={id}
                type="button"
                className="mr-1 cursor-pointer text-dim underline hover:text-fg"
                onClick={() => onSelect(id)}
              >
                {id}
              </button>
            ))}
          </Fact>
        ) : null}
      </dl>
    </div>
  );
}
