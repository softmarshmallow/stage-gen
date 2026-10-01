// <Try>: Tabs with the same request two ways: a prompt for your own agent, and the commands it would run.
// Port of the retired showcase's `try_it` component.
//
// The panes are the page's own <Agent> and <Shell>, as in the showcase. A <Try> without a
// <Shell> gets a "Command line" pane of the commands the page's source declares: the
// workflow.toml [try] commands, or a game example entry's command. web/ui/players/tabs.ts
// drives the [data-tabs] hook, through <TabsPlayer>, and copy.ts each [data-copy] button.

import { createElement, isValidElement, type ReactElement } from "react";
import type { Page } from "@/lib/page";
import TabsPlayer from "@/components/players/TabsPlayer";
import { MARKDOWN } from "./markdown";
import type { BlockProps } from "./shared";
import { blockName, MdxError, nodesOf } from "./shared";
import { ShellBox } from "./Shell";

export type TryProps = Record<string, never>;

const LABELS: Readonly<Record<string, string>> = { Agent: "For agents", Shell: "Command line" };

/** The commands the page's source declares, for a <Try> that holds no <Shell>. */
function declaredCommands(page: Page): readonly string[] {
  const game = page.data.gameEntry;
  if (game !== null) return game.command ? [game.command] : [];
  return page.data.workflow?.manifest.tryIt?.commands ?? [];
}

function DeclaredShell({ commands }: { commands: readonly string[] }): ReactElement {
  const blocks = commands.map((command, i) => createElement(MARKDOWN.pre, { key: i }, command));
  return <ShellBox blocks={blocks} code={commands.join("\n\n")} />;
}

export default function Try({ page, children }: BlockProps<TryProps>): ReactElement {
  const items = nodesOf(children).filter(
    (c): c is ReactElement => isValidElement(c) && /^[A-Z]/.test(blockName(c) ?? ""),
  );
  if (items.some((p) => !(String(blockName(p)) in LABELS))) {
    throw new MdxError("<Try> holds <Agent> and <Shell>");
  }
  const panes: { label: string; body: ReactElement }[] = items.map((p) => ({
    label: LABELS[String(blockName(p))],
    body: p,
  }));
  if (!items.some((p) => blockName(p) === "Shell")) {
    const commands = declaredCommands(page);
    if (commands.length > 0) {
      panes.push({ label: LABELS.Shell, body: <DeclaredShell commands={commands} /> });
    }
  }
  if (panes.length === 0) throw new MdxError("<Try> holds <Agent> and <Shell>");
  return (
    <TabsPlayer className="mt-6">
      <div className="flex gap-6 border-b border-zinc-200 dark:border-zinc-800">
        {panes.map((p, i) => (
          <button
            key={i}
            data-tab={i}
            aria-pressed={i === 0 ? "true" : "false"}
            className="border-b-2 border-transparent px-1 pb-2 text-sm text-zinc-500 aria-pressed:border-zinc-900 aria-pressed:text-zinc-900 dark:aria-pressed:border-zinc-100 dark:aria-pressed:text-zinc-100"
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="mt-6">
        {panes.map((p, i) => (
          <div key={i} data-pane={i} className={i === 0 ? "" : "hidden"}>
            {p.body}
          </div>
        ))}
      </div>
    </TabsPlayer>
  );
}
