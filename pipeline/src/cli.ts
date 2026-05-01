#!/usr/bin/env bun
// stage-gen pipeline CLI — Phase 0 stub.
//
// Today this entrypoint only validates env and echoes the prompt. Real
// generation orchestration lands in later phases. The fail-fast env check
// satisfies TC-003.

import { loadEnv } from "./env.ts";

function usage(): never {
  process.stderr.write(
    `usage: bun run pipeline <prompt>\n` +
      `       (or: bun --cwd pipeline run start <prompt>)\n`,
  );
  process.exit(64);
}

function main() {
  // Bun auto-loads `.env` from cwd. We additionally probe the repo-root .env
  // so the CLI works whether invoked from repo root or pipeline/.
  // (Bun's auto-load handles both via cwd; explicit re-load is a no-op here.)

  const env = loadEnv();

  const args = process.argv.slice(2);
  // Support `bun run pipeline -- "<prompt>"` style by stripping a leading `--`.
  while (args[0] === "--") args.shift();

  const prompt = args.join(" ").trim();
  if (!prompt) usage();

  process.stdout.write(
    `ok: would run for ${JSON.stringify(prompt)} ` +
      `(model=${env.IMAGE_MODEL}, out=${env.OUT_DIR})\n`,
  );
}

main();
