// The CLI reference's data: web/site/.catalog/cli.json, the `stage-gen-cli-v1` command tree
// that `stage-gen catalog export` writes from the argparse parser
// (stage_gen.interfaces.cli.command_reference). Read once per process, at build time, and
// checked here, so a drifted export fails the build instead of rendering half a page.

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { catalogDir } from "./catalog";

export const CLI_REFERENCE_KIND = "stage-gen-cli-v1";

export interface CliArgument {
  readonly names: readonly string[];
  readonly positional: boolean;
  readonly metavar: string | null;
  readonly help: string | null;
  readonly required: boolean;
  readonly repeatable: boolean;
  readonly choices: readonly string[] | null;
  readonly default: string | null;
}

export interface CliCommand {
  readonly name: string;
  readonly prog: string;
  readonly summary: string | null;
  readonly description: string | null;
  readonly usage: string;
  readonly arguments: readonly CliArgument[];
  readonly commands: readonly CliCommand[];
}

type Raw = Record<string, unknown>;

function object(value: unknown, label: string): Raw {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} is not an object`);
  return value as Raw;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string") throw new Error(`${label} is not a string`);
  return value;
}

function textOrNull(value: unknown, label: string): string | null {
  return value === null ? null : text(value, label);
}

function flag(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} is not a boolean`);
  return value;
}

function list(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} is not a list`);
  return value;
}

function parseArgument(value: unknown, label: string): CliArgument {
  const fields = object(value, label);
  const names = list(fields.names, `${label}.names`).map((name, i) => text(name, `${label}.names[${i}]`));
  if (names.length === 0) throw new Error(`${label}.names is empty`);
  return {
    names,
    positional: flag(fields.positional, `${label}.positional`),
    metavar: textOrNull(fields.metavar, `${label}.metavar`),
    help: textOrNull(fields.help, `${label}.help`),
    required: flag(fields.required, `${label}.required`),
    repeatable: flag(fields.repeatable, `${label}.repeatable`),
    choices:
      fields.choices === null
        ? null
        : list(fields.choices, `${label}.choices`).map((choice, i) => text(choice, `${label}.choices[${i}]`)),
    default: textOrNull(fields.default, `${label}.default`),
  };
}

function parseCommand(value: unknown, label: string): CliCommand {
  const fields = object(value, label);
  const name = text(fields.name, `${label}.name`);
  return {
    name,
    prog: text(fields.prog, `${label}.prog`),
    summary: textOrNull(fields.summary, `${label}.summary`),
    description: textOrNull(fields.description, `${label}.description`),
    usage: text(fields.usage, `${label}.usage`),
    arguments: list(fields.arguments, `${label}.arguments`).map((entry, i) => parseArgument(entry, `${label}.arguments[${i}]`)),
    commands: list(fields.commands, `${label}.commands`).map((entry) =>
      parseCommand(entry, `${label} ${String(object(entry, label).name)}`),
    ),
  };
}

/** The parsed command tree, rooted at `stage-gen`. */
export function parseCliReference(value: unknown): CliCommand {
  const fields = object(value, "cli.json");
  if (fields.kind !== CLI_REFERENCE_KIND) {
    throw new Error(`cli.json is ${String(fields.kind)}, not ${CLI_REFERENCE_KIND}`);
  }
  return parseCommand(fields, "cli.json");
}

export function cliReferenceStaged(): boolean {
  return existsSync(path.join(catalogDir(), "cli.json"));
}

let cached: CliCommand | null = null;

/** The staged command tree; throws with the staging command when absent. */
export function loadCliReference(): CliCommand {
  if (cached) return cached;
  const file = path.join(catalogDir(), "cli.json");
  if (!existsSync(file)) {
    throw new Error(`${file} is missing; run \`uv run python scripts/site.py stage\` first`);
  }
  cached = parseCliReference(JSON.parse(readFileSync(file, "utf8")));
  return cached;
}

/** Every command below the root, depth first, in the order the parser declares them. */
export function cliCommands(root: CliCommand): CliCommand[] {
  return root.commands.flatMap((command) => [command, ...cliCommands(command)]);
}
