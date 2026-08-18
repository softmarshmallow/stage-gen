#!/usr/bin/env bun

import {
  parseGameplayRecorderArgs,
  recordGameplay,
  recorderDryRun,
  sanitizeRecorderDiagnostic,
} from "./recorder";

export const GAMEPLAY_RECORDER_USAGE =
  "usage: bun scripts/gameplay/record.ts [--dry-run] [--output output/playwright/name.mp4] " +
  "[--duration 30] [--fps 30] [--width 1280] [--height 720] [--poster-frame 35] " +
  "[--timeout-ms 600000] [--no-verify-twice] [--preset model-demo | " +
  "--fixture out/<tag> --tag <tag> --timeline <timeline.json>]";

export async function runGameplayRecorderCli(
  args: readonly string[],
): Promise<unknown> {
  if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
    return Object.freeze({ usage: GAMEPLAY_RECORDER_USAGE });
  }
  const options = parseGameplayRecorderArgs(args);
  return options.mode === "dry-run"
    ? recorderDryRun(options)
    : await recordGameplay(options);
}

if (import.meta.main) {
  try {
    const evidence = await runGameplayRecorderCli(process.argv.slice(2));
    process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
  } catch (error) {
    const detail = sanitizeRecorderDiagnostic(
      error instanceof Error ? error.message : String(error),
    );
    process.stderr.write(`gameplay recorder failed: ${detail}\n`);
    process.exitCode = 1;
  }
}
