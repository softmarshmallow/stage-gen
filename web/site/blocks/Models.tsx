// <Models>: The models the run called, then the local tools.
// Port of the retired showcase's `models` component.
//
// A model and its provider are shown by the catalog's display names (model_names,
// provider_names); a name the catalog does not map is already a display name.

import type { ReactElement } from "react";
import type { ExampleModel } from "@stage-gen/ui/contracts/example";
import type { Page } from "@/lib/page";
import type { BlockProps } from "./shared";
import { CELL } from "./shared";

export type ModelsProps = Record<string, never>;

/** Python's str.isupper(): at least one cased character, and none in lower case. */
function isUpper(text: string): boolean {
  return text !== text.toLowerCase() && text === text.toUpperCase();
}

function role(page: Page, m: ExampleModel): string {
  // Lower-case role words mid-sentence, but leave acronyms such as "3D" alone.
  const parts =
    m.roles.length > 0
      ? [
          m.roles
            .map((k) => (isUpper(k.slice(0, 2)) || /^\d/.test(k) ? k : k.toLowerCase()))
            .join(" and "),
        ]
      : [];
  parts.push(...m.calledBy.map((n) => `used by ${page.titleOf(n)}`));
  const text = parts.filter((p) => p).join(", ");
  return text.slice(0, 1).toUpperCase() + text.slice(1);
}

/**
 * The page's local tools, less those the run recorded itself as a local model row. The
 * showcase's front matter named a tool only where the record did not; workflow.toml names
 * every tool for the reference too (character-3d's Blender), so the record's own row,
 * with its version ("Blender 5.2.0 LTS"), wins and the tool is not listed twice.
 */
function toolsOf(page: Page) {
  const local = page.record.models.filter((m) => m.provider === "local").map((m) => m.name);
  return page.data.tools.filter(
    (t) => !local.some((name) => name === t.name || name.startsWith(`${t.name} `)),
  );
}

export default function Models({ page }: BlockProps<ModelsProps>): ReactElement {
  return (
    <table className="mt-4 w-full text-sm">
      <tbody>
        {page.record.models.map((m, i) => (
          <tr key={`m${i}`}>
            <td className={`${CELL} font-medium`}>{page.modelName(m.name)}</td>
            <td className={`${CELL} text-zinc-500`}>{page.providerName(m.provider) ?? ""}</td>
            <td className={`${CELL} text-zinc-500`}>{role(page, m)}</td>
          </tr>
        ))}
        {toolsOf(page).map((t, i) => (
          <tr key={`t${i}`}>
            <td className={`${CELL} font-medium`}>{t.name}</td>
            <td className={`${CELL} text-zinc-500`}>local</td>
            <td className={`${CELL} text-zinc-500`}>{t.role}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
