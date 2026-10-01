// One workflow, read from the catalog `stage-gen view` exported: what it promises, the
// commands that run it, the graph it plans offline from its committed sample inputs,
// its steps, and its runs under the viewer's roots.
//
// The plan is the catalog's: drawn with the run viewer in its plan mode, every node
// pending. Nothing here plans, spawns or runs anything; the commands are for the
// reader's terminal.

import Link from "next/link";
import { notFound } from "next/navigation";
import { findWorkflow } from "@stage-gen/ui/contracts/catalog";
import CopyCommand from "@/app/CopyCommand";
import RunList from "@/app/RunList";
import RunViewer from "@/app/runs/[root]/[tag]/RunViewer";
import { cx, errorBanner, h1, metaLine, page, sectionHeading } from "@/app/ui";
import { groupRuns } from "@/lib/run-groups";
import { samplePlanView } from "@/lib/run-viewer/plan-view";
import { readCatalog } from "@/lib/shell/catalog";
import { listRuns } from "@/lib/shell/run-index";

export const dynamic = "force-dynamic";

export default async function WorkflowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { catalog, refusal } = await readCatalog();
  if (catalog === null) {
    return (
      <main className={page}>
        <p className={metaLine}>
          <Link className="text-dim no-underline hover:text-accent" href="/">
            ← runs
          </Link>
        </p>
        <h1 className={h1}>{id}</h1>
        <p className={refusal ? errorBanner : metaLine}>
          {refusal ?? "No catalog. Start the viewer with stage-gen view to read workflows."}
        </p>
      </main>
    );
  }
  const workflow = findWorkflow(catalog, id);
  if (workflow === null) notFound();
  const manifest = workflow.manifest;
  const planned = samplePlanView(workflow, catalog);
  const runs = groupRuns(await listRuns(), catalog).workflows.find(
    (group) => group.workflow.id === workflow.id,
  )?.runs;
  const now = Date.now();
  const commands = [
    ...(manifest.tryIt?.commands ?? []),
    `stage-gen show ${workflow.id}`,
    `stage-gen plan ${workflow.id} --help`,
    `stage-gen run ${workflow.id} --help`,
  ];
  const related = manifest.related
    .map((other) => findWorkflow(catalog, other))
    .filter((other) => other !== null);

  return (
    <main className={page}>
      <p className={metaLine}>
        <Link className="text-dim no-underline hover:text-accent" href={`/#${workflow.id}`}>
          ← runs
        </Link>
      </p>
      <h1 className={cx(h1, "mb-1")}>{manifest.title}</h1>
      <p className={metaLine}>
        {workflow.id} · {manifest.promise}
      </p>
      <p className="mt-2 mb-0 max-w-[760px] text-dim">{manifest.summary}</p>

      <h2 className={sectionHeading}>run it</h2>
      {manifest.tryIt ? <p className={metaLine}>{manifest.tryIt.input}</p> : null}
      <div className="flex flex-col gap-1.5">
        {commands.map((command) => (
          <CopyCommand key={command} command={command} />
        ))}
      </div>
      {workflow.planRefusal ? (
        <p className={cx(metaLine, "mt-2")}>
          <code>stage-gen plan {workflow.id}</code> refuses: {workflow.planRefusal}
        </p>
      ) : null}

      <h2 className={sectionHeading}>offline plan</h2>
      {planned ? (
        <>
          <p className={metaLine}>
            The graph this workflow plans from its committed sample inputs, with no provider
            and nothing run. Lanes are its steps; click a node to see what it is for.
          </p>
          <div className="relative h-[560px] overflow-hidden border border-border max-[700px]:h-[440px]">
            <RunViewer view={planned.view} plan={planned.plan} liveness="planned" embedded />
          </div>
        </>
      ) : (
        <p className={metaLine}>
          No offline plan: {workflow.noSamplePlan ?? "its committed sample inputs are absent"}.
        </p>
      )}

      <h2 className={sectionHeading}>steps</h2>
      <ol className="m-0 list-none p-0">
        {workflow.steps.map((step, index) => (
          <li key={step.label} className="border-b border-border py-2 first:border-t">
            <div className="text-[13px] text-fg">
              <span className="text-dim">{index + 1}.</span> {step.label}
            </div>
            <p className="m-0 mt-0.5 text-xs text-dim">{step.note}</p>
            <p className="m-0 mt-1 text-[11px] text-dim">
              {step.members.map((member) => member.title).join(" · ")}
            </p>
          </li>
        ))}
      </ol>

      <h2 className={sectionHeading}>runs</h2>
      {runs && runs.length > 0 ? (
        <RunList runs={runs} now={now} />
      ) : (
        <p className={metaLine}>No runs of this workflow under the viewer&apos;s roots yet.</p>
      )}

      {related.length > 0 || manifest.tools.length > 0 ? (
        <>
          <h2 className={sectionHeading}>around it</h2>
          {related.length > 0 ? (
            <p className={metaLine}>
              related:{" "}
              {related.map((other, index) => (
                <span key={other.id}>
                  {index > 0 ? ", " : ""}
                  <Link className="text-dim hover:text-accent" href={`/workflows/${other.id}`}>
                    {other.manifest.title}
                  </Link>
                </span>
              ))}
            </p>
          ) : null}
          {manifest.tools.length > 0 ? (
            <p className={metaLine}>
              tools: {manifest.tools.map((tool) => `${tool.name} (${tool.role})`).join(" · ")}
            </p>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
