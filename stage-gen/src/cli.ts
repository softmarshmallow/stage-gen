#!/usr/bin/env bun

import { readFile } from "node:fs/promises";
import {
  ConfigError,
  loadConfig,
  parseTransparencyMode,
  type TransparencyMode,
} from "./config.ts";
import { listBenchmarkSuites, runBenchmark } from "./benchmarks.ts";
import { listRecipes } from "./recipes.ts";
import { generate } from "./service.ts";
import { serveStageGen } from "./server.ts";
import { generateMusic, removeBackground } from "./capabilities.ts";
import { generateImageArtifact } from "./capabilities.ts";
import { importProviderEnv } from "./import-env.ts";
import type { ImageAspectRatio } from "@stage-gen/image-generation";

const HELP = `stage-gen - headless 2D asset pipeline

usage:
  stage-gen generate [--recipe <id>] [--input <json-file>] [--transparency ai|chroma] <prompt>
  stage-gen serve [--host <hostname>] [--port <number>] [--public]
  stage-gen recipes
  stage-gen benchmark [list | <suite>]
  stage-gen research [list | <suite>]
  stage-gen generate-image --output <png> [--aspect-ratio <w:h>] [--reference <image>] <prompt>
  stage-gen remove-background --input <image> --output <png>
  stage-gen generate-music --output <mp3|wav> [--format mp3|wav] <prompt>
  stage-gen import-env --source <dotenv> --destination <dotenv>
  stage-gen doctor [--transparency ai|chroma] [--json]

Every generated artifact reports both its explicit output path and provenance path.

Legacy compatibility: a bare prompt is treated as "generate --recipe scrolling-preview".
`;

export async function main(argv = process.argv.slice(2)): Promise<number> {
  const args = argv.slice();
  while (args[0] === "--") args.shift();
  if (args.length === 0 || args[0] === "help" || args[0] === "--help" || args[0] === "-h") {
    process.stdout.write(HELP);
    return 0;
  }

  const known = new Set([
    "generate",
    "serve",
    "recipes",
    "benchmark",
    "research",
    "generate-image",
    "remove-background",
    "generate-music",
    "import-env",
    "doctor",
  ]);
  const command = known.has(args[0]) ? args.shift()! : "generate";

  try {
    if (command === "recipes") {
      process.stdout.write(`${JSON.stringify({ recipes: listRecipes() }, null, 2)}\n`);
      return 0;
    }
    if (command === "doctor") return doctor(args);
    if (command === "benchmark" || command === "research") return benchmark(args);
    if (command === "generate-image") return runGenerateImage(args);
    if (command === "remove-background") return runRemoveBackground(args);
    if (command === "generate-music") return runGenerateMusic(args);
    if (command === "import-env") return runImportEnv(args);
    if (command === "serve") return serve(args);
    return runGenerate(args);
  } catch (error) {
    const prefix = error instanceof ConfigError ? "configuration" : "error";
    process.stderr.write(`stage-gen: ${prefix}: ${message(error)}\n`);
    return error instanceof ConfigError ? 2 : 1;
  }
}

async function runGenerateImage(args: string[]): Promise<number> {
  let output: string | undefined;
  let aspectRatio: ImageAspectRatio = "1:1";
  const references: string[] = [];
  const promptParts: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--output") output = requiredValue(args, ++i, "--output");
    else if (args[i] === "--aspect-ratio") {
      const value = requiredValue(args, ++i, "--aspect-ratio");
      if (value !== "auto" && !/^[1-9]\d*:[1-9]\d*$/.test(value)) {
        throw new Error("--aspect-ratio must be auto or positive <width>:<height>");
      }
      aspectRatio = value as ImageAspectRatio;
    } else if (args[i] === "--reference") {
      references.push(requiredValue(args, ++i, "--reference"));
    } else promptParts.push(args[i]);
  }
  const prompt = promptParts.join(" ").trim();
  if (!output || !prompt) throw new Error("generate-image requires --output and a prompt");
  const result = await generateImageArtifact(
    { prompt, outputPath: output, aspectRatio, referencePaths: references },
    loadConfig(),
  );
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return 0;
}

async function runImportEnv(args: string[]): Promise<number> {
  let source: string | undefined;
  let destination: string | undefined;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--source") source = requiredValue(args, ++i, "--source");
    else if (args[i] === "--destination") {
      destination = requiredValue(args, ++i, "--destination");
    } else throw new Error(`unknown import-env argument: ${args[i]}`);
  }
  if (!source || !destination) throw new Error("import-env requires --source and --destination");
  const result = await importProviderEnv(source, destination);
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return 0;
}

async function runRemoveBackground(args: string[]): Promise<number> {
  let input: string | undefined;
  let output: string | undefined;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--input") input = requiredValue(args, ++i, "--input");
    else if (args[i] === "--output") output = requiredValue(args, ++i, "--output");
    else throw new Error(`unknown remove-background argument: ${args[i]}`);
  }
  if (!input || !output) throw new Error("remove-background requires --input and --output");
  const result = await removeBackground(input, output, loadConfig());
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return 0;
}

async function runGenerateMusic(args: string[]): Promise<number> {
  let output: string | undefined;
  let format: "mp3" | "wav" = "mp3";
  const promptParts: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--output") output = requiredValue(args, ++i, "--output");
    else if (args[i] === "--format") {
      const value = requiredValue(args, ++i, "--format");
      if (value !== "mp3" && value !== "wav") throw new Error("--format must be mp3 or wav");
      format = value;
    } else promptParts.push(args[i]);
  }
  const prompt = promptParts.join(" ").trim();
  if (!output || !prompt) throw new Error("generate-music requires --output and a prompt");
  const result = await generateMusic(prompt, output, format, loadConfig());
  process.stdout.write(`${JSON.stringify(result)}\n`);
  return 0;
}

async function runGenerate(args: string[]): Promise<number> {
  const parsed = parseGenerateArguments(args);
  const input = parsed.inputFile
    ? JSON.parse(await readFile(parsed.inputFile, "utf8"))
    : { prompt: parsed.prompt };
  const config = loadConfig();
  const summary = await generate(
    {
      recipe: parsed.recipe,
      input,
      transparencyMode: parsed.transparencyMode,
    },
    config,
  );
  if (!summary.ok) {
    const failed = summary.stages.find((stage) => !stage.ok);
    process.stderr.write(
      `stage-gen: stage failed - ${failed?.stage ?? "unknown"}: ${failed?.error ?? "unknown"}\n`,
    );
    return 1;
  }
  process.stdout.write(
    `stage-gen: done recipe=${summary.recipe} tag=${summary.tag} stages=${summary.stages.length} duration=${summary.durationMs}ms\n`,
  );
  return 0;
}

export interface GenerateArguments {
  recipe: string;
  inputFile?: string;
  prompt: string;
  transparencyMode?: TransparencyMode;
}

/** Pure public CLI parser, shared by tests and the executable boundary. */
export function parseGenerateArguments(args: string[]): GenerateArguments {
  let recipe = "scrolling-preview";
  let inputFile: string | undefined;
  let transparencyMode: TransparencyMode | undefined;
  const rest: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--recipe") recipe = requiredValue(args, ++i, "--recipe");
    else if (args[i] === "--input") inputFile = requiredValue(args, ++i, "--input");
    else if (args[i] === "--transparency") {
      transparencyMode = parseTransparencyMode(
        requiredValue(args, ++i, "--transparency"),
        "--transparency",
      );
    } else if (args[i].startsWith("--")) {
      throw new Error(`unknown generate argument: ${args[i]}`);
    } else rest.push(args[i]);
  }
  return { recipe, inputFile, prompt: rest.join(" ").trim(), transparencyMode };
}

async function benchmark(args: string[]): Promise<number> {
  const suite = args[0] ?? "smoke";
  if (suite === "list") {
    process.stdout.write(`${JSON.stringify({ suites: listBenchmarkSuites() }, null, 2)}\n`);
    return 0;
  }
  const result = await runBenchmark(suite, {
    config: loadConfig(),
    write: (line) => process.stdout.write(`${line}\n`),
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  return result.ok ? 0 : 1;
}

async function serve(args: string[]): Promise<number> {
  let port = 4317;
  let hostname: string | undefined;
  let allowPublic = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--port") port = Number(requiredValue(args, ++i, "--port"));
    else if (args[i] === "--host") hostname = requiredValue(args, ++i, "--host");
    else if (args[i] === "--public") allowPublic = true;
    else throw new Error(`unknown serve argument: ${args[i]}`);
  }
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("--port must be an integer between 1 and 65535");
  }
  if (allowPublic && !hostname) hostname = "0.0.0.0";
  const server = serveStageGen(loadConfig(), { port, hostname, allowPublic });
  const actualHostname = server.hostname ?? hostname ?? "127.0.0.1";
  const reportedHost = actualHostname.includes(":")
    ? `[${actualHostname}]`
    : actualHostname;
  process.stdout.write(`stage-gen: listening on http://${reportedHost}:${server.port}\n`);
  await new Promise<void>((resolve) => {
    const stop = () => {
      server.stop();
      resolve();
    };
    process.once("SIGINT", stop);
    process.once("SIGTERM", stop);
  });
  return 0;
}

function doctor(args: string[]): number {
  const { json: jsonOutput, transparencyMode: requestedMode } =
    parseDoctorArguments(args);
  const config = loadConfig();
  const report = createDoctorReport(config, requestedMode);
  if (jsonOutput) process.stdout.write(`${JSON.stringify(report)}\n`);
  else {
    process.stdout.write(
      `stage-gen: ${report.ok ? "ready" : "incomplete"}; transparency=${report.transparencyMode}; openrouter=${report.capabilities.openrouter ? "configured" : "missing"}; fal=${report.requirements.backgroundRemoval ? (report.capabilities.fal ? "configured" : "missing") : "not-required"}\n`,
    );
  }
  return report.ok ? 0 : 2;
}

export interface DoctorArguments {
  json: boolean;
  transparencyMode?: TransparencyMode;
}

export function parseDoctorArguments(args: string[]): DoctorArguments {
  let json = false;
  let transparencyMode: TransparencyMode | undefined;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--json") json = true;
    else if (args[i] === "--transparency") {
      transparencyMode = parseTransparencyMode(
        requiredValue(args, ++i, "--transparency"),
        "--transparency",
      );
    } else throw new Error(`unknown doctor argument: ${args[i]}`);
  }
  return { json, transparencyMode };
}

export function createDoctorReport(
  config: ReturnType<typeof loadConfig>,
  requestedMode?: TransparencyMode,
) {
  const transparencyMode = requestedMode ?? config.transparencyMode;
  const requiresBackgroundRemoval = transparencyMode === "ai";
  return {
    ok: Boolean(
      config.openRouterApiKey && (!requiresBackgroundRemoval || config.falKey),
    ),
    transparencyMode,
    requirements: {
      openrouter: true,
      backgroundRemoval: requiresBackgroundRemoval,
    },
    capabilities: {
      openrouter: Boolean(config.openRouterApiKey),
      fal: Boolean(config.falKey),
    },
    models: {
      image: config.imageModel,
      text: config.textModel,
      music: config.musicModel,
      backgroundRemoval: config.backgroundRemovalModel,
    },
    outDir: config.outDir,
  };
}

function requiredValue(args: string[], index: number, flag: string): string {
  const value = args[index];
  if (!value) throw new Error(`${flag} requires a value`);
  return value;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

if (import.meta.main) {
  process.exitCode = await main();
}
