// The generated reference page of one workflow (/docs/workflows/<id>/), written from the
// catalog alone: what it promises, its steps and their node types, what it writes, how to
// try it, and its examples.

import type { ReactElement } from "react";
import type { CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";
import { CELL, HEAD } from "@/blocks/shared";
import { href } from "@/lib/media";
import { contractRoute, workflowRoute } from "@/lib/pages";

const H2 = "mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800";
const P = "mt-6 max-w-3xl text-zinc-700 dark:text-zinc-300";
const PRE =
  "mt-4 overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-4 font-mono text-[13px] leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200";

export default function WorkflowReference({ workflow }: { workflow: CatalogWorkflow }): ReactElement {
  const manifest = workflow.manifest;
  return (
    <>
      <h1 className="text-3xl font-semibold tracking-tight">{manifest.title}</h1>
      <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">{manifest.promise}</p>
      <p className="mt-4 text-sm text-zinc-500">
        <code className="font-mono text-[0.9em]">{workflow.id}</code> ·{" "}
        <a className="underline decoration-zinc-300 underline-offset-2" href={href(workflowRoute(workflow.id))}>
          Page
        </a>{" "}
        ·{" "}
        <a className="underline decoration-zinc-300 underline-offset-2" href={href(contractRoute(workflow.id))}>
          Contract
        </a>
      </p>
      <p className={P}>{manifest.summary}</p>

      <h2 className={H2}>Steps</h2>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr>
            <th className={HEAD}>Step</th>
            <th className={HEAD}>Node types</th>
          </tr>
        </thead>
        <tbody>
          {workflow.steps.map((step) => (
            <tr key={step.label}>
              <td className={`${CELL} w-2/5`}>
                <span className="font-medium">{step.label}</span>
                <br />
                <span className="text-zinc-500">{step.note}</span>
              </td>
              <td className={CELL}>
                {step.members.map((member) => (
                  <div key={member.typeId}>
                    {member.title} <code className="font-mono text-[0.9em] text-zinc-500">{member.typeId}</code>
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {manifest.outputs.length > 0 ? (
        <>
          <h2 className={H2}>Outputs</h2>
          <table className="mt-4 w-full text-sm">
            <tbody>
              {manifest.outputs.map((output) => (
                <tr key={output.artifactRef}>
                  <td className={`${CELL} font-mono text-[13px]`}>{output.artifactRef}</td>
                  <td className={`${CELL} text-zinc-500`}>{output.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {manifest.tryIt !== null ? (
        <>
          <h2 className={H2}>Try it</h2>
          <p className={P}>{manifest.tryIt.input}</p>
          <pre className={PRE}>{manifest.tryIt.commands.join("\n\n")}</pre>
        </>
      ) : null}

      <h2 className={H2}>Examples</h2>
      {workflow.examples.length === 0 ? (
        <p className={P}>No approved example yet.</p>
      ) : (
        <table className="mt-4 w-full text-sm">
          <tbody>
            {workflow.examples.map((example) => (
              <tr key={example.id}>
                <td className={`${CELL} font-medium`}>{example.title}</td>
                <td className={`${CELL} text-zinc-500`}>{example.id}</td>
                <td className={`${CELL} text-zinc-500`}>
                  {example.present
                    ? example.currency === "earlier_version"
                      ? "made with an earlier version"
                      : "current"
                    : "not in this build"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
