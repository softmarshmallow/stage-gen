#!/usr/bin/env bun

import {
  captureDeterministicGameplay,
  verifyDeterministicGameplay,
} from "../../tests/gameplay/harness";

function usage(): never {
  throw new Error(
    "usage: bun scripts/gameplay/showcase.ts --verify | --capture docs/media/gameplay-showcase.mp4",
  );
}

const args = process.argv.slice(2);

try {
  const evidence =
    args.length === 1 && args[0] === "--verify"
      ? await verifyDeterministicGameplay()
      : args.length === 2 && args[0] === "--capture"
        ? await captureDeterministicGameplay(args[1])
        : usage();
  process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`gameplay automation failed: ${message}\n`);
  process.exitCode = 1;
}
