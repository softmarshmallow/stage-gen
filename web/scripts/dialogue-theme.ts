import path from "node:path";
import {
  activateDialogueTheme,
  dialogueThemeStatus,
  installDialogueTheme,
  rollbackDialogueTheme,
  type DialogueThemeAdapterOptions,
} from "../lib/dialogue-scene/theme-adapter";

type Command = "install" | "activate" | "status" | "rollback";

function usage(): never {
  throw new Error(
    "usage: bun run dialogue-theme -- <install|activate|status|rollback> " +
      "[--bundle PATH] [--bundle-id SHA256] " +
      "[--state-root PATH] [--public-root PATH]",
  );
}

export function parseDialogueThemeArgs(args: readonly string[]): {
  readonly command: Command;
  readonly bundle: string | null;
  readonly bundleId: string | null;
  readonly options: DialogueThemeAdapterOptions;
} {
  const [commandValue, ...rest] = args;
  if (!["install", "activate", "status", "rollback"].includes(commandValue ?? "")) {
    usage();
  }
  const command = commandValue as Command;
  let bundle: string | null = null;
  let bundleId: string | null = null;
  let stateRoot = path.resolve(import.meta.dir, "../../out/dialogue-theme-state");
  let publicRoot = path.resolve(import.meta.dir, "../public/dialogue-scene/themes");
  const seenFlags = new Set<string>();
  for (let index = 0; index < rest.length; index += 1) {
    const flag = rest[index];
    const value = rest[index + 1];
    if (value === undefined) usage();
    if (seenFlags.has(flag)) usage();
    seenFlags.add(flag);
    if (flag === "--bundle") bundle = path.resolve(value);
    else if (flag === "--bundle-id") bundleId = value;
    else if (flag === "--state-root") stateRoot = path.resolve(value);
    else if (flag === "--public-root") publicRoot = path.resolve(value);
    else usage();
    index += 1;
  }
  if ((command === "install") !== (bundle !== null)) usage();
  if ((command === "activate") !== (bundleId !== null)) usage();
  return Object.freeze({
    command,
    bundle,
    bundleId,
    options: Object.freeze({ stateRoot, publicRoot }),
  });
}

export async function runDialogueTheme(args: readonly string[]): Promise<unknown> {
  const parsed = parseDialogueThemeArgs(args);
  if (parsed.command === "install") {
    return installDialogueTheme(parsed.bundle!, parsed.options);
  }
  if (parsed.command === "activate") {
    return activateDialogueTheme(parsed.bundleId!, parsed.options);
  }
  if (parsed.command === "rollback") return rollbackDialogueTheme(parsed.options);
  return dialogueThemeStatus(parsed.options);
}

if (import.meta.main) {
  try {
    const result = await runDialogueTheme(process.argv.slice(2));
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
