#!/usr/bin/env bun
// stage-gen pipeline CLI.
//
// Phase 1: a single command runs the full pipeline end-to-end for one prompt.
// Today every stage is a stub (logs + writes a `<stage>.stub` marker + meta);
// Phase 2+ replaces stub bodies with real generators without changing this
// entrypoint.
//
//   bun run pipeline "<prompt>"
//
// Behaviour:
//   - Validates env (fail-fast, exit 2) — preserves TC-003.
//   - Derives a deterministic tag from the prompt (TC-011).
//   - Writes only into `out/<tag>/` (TC-012).
//   - Exits 0 on success; any stage failure → non-zero exit + one-line stderr
//     (TC-010).

import { loadEnv } from "./env.ts";
import { runPipeline } from "./orchestrator.ts";

function usage(): never {
  process.stderr.write(
    `usage: bun run pipeline <prompt>\n` +
      `       (or: bun --cwd pipeline run start <prompt>)\n`,
  );
  process.exit(64);
}

async function main() {
  const env = loadEnv();

  const args = process.argv.slice(2);
  // Support `bun run pipeline -- "<prompt>"` style by stripping a leading `--`.
  while (args[0] === "--") args.shift();

  const prompt = args.join(" ").trim();
  if (!prompt) usage();

  let summary;
  try {
    summary = await runPipeline({ prompt, env });
  } catch (err) {
    // The orchestrator catches per-stage failures; reaching here means an
    // unexpected error (e.g. fs permission). Surface it on one line and exit.
    const msg = err instanceof Error ? err.message : String(err);
    process.stderr.write(`stage-gen: pipeline crashed: ${msg}\n`);
    process.exit(1);
  }

  if (!summary.ok) {
    const failed = summary.stages.find((s) => !s.ok);
    const cause = failed ? `${failed.stage}: ${failed.error}` : "unknown";
    process.stderr.write(`stage-gen: stage failed — ${cause}\n`);
    process.exit(1);
  }

  process.stdout.write(
    `stage-gen: done tag=${summary.tag} stages=${summary.stages.length} ` +
      `duration=${summary.durationMs}ms\n`,
  );
}

main();
