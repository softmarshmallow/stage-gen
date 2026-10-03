// The docs' own checks, runnable without a staged catalog: the CLI reference's parser, and a
// doc's relative links pointed at the site's pages.

import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CliReference, { commandAnchor } from "@/components/CliReference";
import { cliCommands, parseCliReference } from "@/lib/cli";
import { compileSource, docComponents } from "@/lib/mdx";

const argument = (names: string[], extra: Record<string, unknown> = {}) => ({
  names,
  positional: false,
  metavar: null,
  help: null,
  required: false,
  repeatable: false,
  choices: null,
  default: null,
  ...extra,
});

const command = (prog: string, extra: Record<string, unknown> = {}) => ({
  name: prog.split(" ").at(-1),
  prog,
  summary: null,
  description: null,
  usage: prog,
  arguments: [],
  commands: [],
  ...extra,
});

const TREE = {
  kind: "gnode-cli-v1",
  ...command("gnode", {
    description: "Plan and run gnode workflows.",
    usage: "gnode [-h] <command> ...",
    commands: [
      command("gnode view", {
        summary: "the dashboard over run folders",
        usage: "gnode view [-h] [--port PORT]",
        arguments: [argument(["--port"], { metavar: "PORT", default: "3000" })],
      }),
      command("gnode takes", {
        commands: [command("gnode takes list")],
      }),
    ],
  }),
};

describe("CLI reference", () => {
  test("parses the exported tree and lists every command depth first", () => {
    const root = parseCliReference(TREE);
    expect(cliCommands(root).map((c) => c.prog)).toEqual([
      "gnode view",
      "gnode takes",
      "gnode takes list",
    ]);
    expect(commandAnchor(root.commands[1].commands[0])).toBe("gnode-takes-list");
  });

  test("refuses another kind or a malformed command", () => {
    expect(() => parseCliReference({ ...TREE, kind: "stage-gen-catalog-v1" })).toThrow("not gnode-cli-v1");
    expect(() => parseCliReference({ ...TREE, usage: 3 })).toThrow("cli.json.usage is not a string");
    const nameless = { ...TREE, commands: [command("gnode view", { arguments: [argument([])] })] };
    expect(() => parseCliReference(nameless)).toThrow("names is empty");
  });

  test("renders usage and arguments from the tree alone", () => {
    const html = renderToStaticMarkup(createElement(CliReference, { root: parseCliReference(TREE) }));
    expect(html).toContain('id="gnode-view"');
    expect(html).toContain("--port PORT");
    expect(html).toContain("Default: 3000.");
  });
});

describe("doc links", () => {
  test("a relative link leads to the site's page, or keeps only its words", async () => {
    const source = "See the [site](site.md#pages), the [runs code](../src/stage_gen/runs.py) and [uv](https://docs.astral.sh/uv/).";
    const resolve = (target: string) => (target.startsWith("site.md") ? `/docs/site/${target.slice("site.md".length)}` : null);
    const Content = await compileSource(source, "md", { from: "docs/viewer.md", resolve });
    const html = renderToStaticMarkup(createElement(Content, { components: docComponents() }));
    expect(html).toContain('href="/docs/site/#pages"');
    expect(html).toContain("the runs code and");
    expect(html).not.toContain("runs.py");
    expect(html).toContain('href="https://docs.astral.sh/uv/"');
  });

  test("a relative image the site does not publish keeps its alt text", async () => {
    const source = "Before.\n\n![The loop node in the map branch](../../../../docs/diagrams/loop.svg)\n\nAfter.";
    const Content = await compileSource(source, "md", { from: "src/stage_gen/workflows/x/contract.md", resolve: () => null });
    const html = renderToStaticMarkup(createElement(Content, { components: docComponents() }));
    expect(html).toContain("The loop node in the map branch");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("loop.svg");
  });
});
