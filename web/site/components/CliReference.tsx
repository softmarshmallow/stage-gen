// The CLI reference page (/docs/cli/), written from the command tree `stage-gen catalog
// export` writes beside the catalog (lib/cli.ts): every command in the parser's order, with
// its usage and its arguments. Nothing here is typed by hand, so the page cannot drift from
// the parser.

import { Fragment, type ReactElement } from "react";
import { CELL, HEAD } from "@/blocks/shared";
import type { CliArgument, CliCommand } from "@/lib/cli";

const H2 = "mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800";
const H3 = "mt-10 font-medium";
const P = "mt-4 max-w-3xl text-zinc-700 dark:text-zinc-300";
const PRE =
  "mt-4 overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-4 font-mono text-[13px] leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200";
const CODE = "font-mono text-[0.9em]";
const LINK = "underline decoration-zinc-300 underline-offset-2";

/** The fragment id of a command: its full invocation, words joined by hyphens. */
export function commandAnchor(command: CliCommand): string {
  return command.prog.trim().split(/\s+/).join("-");
}

function signature(argument: CliArgument): string {
  if (argument.positional) return argument.names[0];
  return argument.names.map((name) => (argument.metavar ? `${name} ${argument.metavar}` : name)).join(", ");
}

function notes(argument: CliArgument): string[] {
  const out: string[] = [];
  if (argument.required && !argument.positional) out.push("Required.");
  // Help that already says an argument repeats ("repeatable", "repeat it") is not echoed.
  if (argument.repeatable && !/\brepeat/i.test(argument.help ?? "")) out.push("Repeatable.");
  if (argument.choices !== null) out.push(`One of: ${argument.choices.join(", ")}.`);
  if (argument.default !== null) out.push(`Default: ${argument.default}.`);
  return out;
}

function Arguments({ command }: { command: CliCommand }): ReactElement | null {
  if (command.arguments.length === 0) return null;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className={HEAD}>Argument</th>
            <th className={HEAD}>Meaning</th>
          </tr>
        </thead>
        <tbody>
          {command.arguments.map((argument) => (
            <tr key={argument.names.join(" ")}>
              <td className={`${CELL} w-2/5 whitespace-nowrap font-mono text-[13px]`}>{signature(argument)}</td>
              <td className={`${CELL} text-zinc-600 dark:text-zinc-400`}>
                {[argument.help ?? "", ...notes(argument)].filter(Boolean).join(" ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Command({ command, depth }: { command: CliCommand; depth: number }): ReactElement {
  const Heading = depth === 1 ? "h2" : "h3";
  const said = command.description ?? command.summary;
  return (
    <>
      <Heading id={commandAnchor(command)} className={depth === 1 ? H2 : H3}>
        <code className={CODE}>{command.prog}</code>
      </Heading>
      {said ? <p className={P}>{said}</p> : null}
      <pre className={PRE}>{command.usage}</pre>
      <Arguments command={command} />
      {command.commands.map((child) => (
        <Command key={child.name} command={child} depth={depth + 1} />
      ))}
    </>
  );
}

export default function CliReference({ root }: { root: CliCommand }): ReactElement {
  return (
    <>
      <h1 className="text-3xl font-semibold tracking-tight">CLI reference</h1>
      {root.description ? <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">{root.description}</p> : null}
      <pre className={PRE}>{root.usage}</pre>
      <p className={P}>
        Written from the parser itself when the site is built. <code className={CODE}>stage-gen &lt;command&gt; --help</code>{" "}
        prints the same for one command.
      </p>
      <ul className="mt-6 max-w-3xl space-y-1.5 text-zinc-700 dark:text-zinc-300">
        {root.commands.map((command) => (
          <li key={command.name}>
            <a className={LINK} href={`#${commandAnchor(command)}`}>
              <code className={CODE}>{command.name}</code>
            </a>
            {command.summary ? <span className="text-zinc-500">: {command.summary}</span> : null}
          </li>
        ))}
      </ul>
      {root.commands.map((command) => (
        <Fragment key={command.name}>
          <Command command={command} depth={1} />
        </Fragment>
      ))}
    </>
  );
}
