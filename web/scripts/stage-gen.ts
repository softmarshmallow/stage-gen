import path from "node:path";

export function stageGenArgv(args: readonly string[]): string[] {
  return ["uv", "run", "stage-gen", ...args];
}

export function stageGenRepositoryRoot(): string {
  return path.resolve(import.meta.dir, "../..");
}

if (import.meta.main) {
  const child = Bun.spawn(stageGenArgv(process.argv.slice(2)), {
    cwd: stageGenRepositoryRoot(),
    env: process.env,
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  process.exitCode = await child.exited;
}
