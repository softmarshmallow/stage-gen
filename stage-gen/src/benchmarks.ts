import type { StageGenConfig } from "./config.ts";
import { listRecipes } from "./recipes.ts";
import { tagFor } from "./tag.ts";

export interface BenchmarkContext {
  config: StageGenConfig;
  write(line: string): void;
}

export interface BenchmarkResult {
  suite: string;
  ok: boolean;
  checks: Array<{ name: string; ok: boolean; detail?: string }>;
}

export interface BenchmarkSuite {
  id: string;
  description: string;
  live: boolean;
  run(context: BenchmarkContext): Promise<BenchmarkResult>;
}

const smokeSuite: BenchmarkSuite = {
  id: "smoke",
  description: "Offline headless registry and deterministic-tag smoke",
  live: false,
  async run() {
    const a = tagFor("neutral 2D asset study");
    const b = tagFor("neutral 2D asset study");
    const recipes = listRecipes();
    const checks = [
      { name: "deterministic-tag", ok: a === b, detail: a },
      {
        name: "recipe-registry",
        ok: recipes.some((recipe) => recipe.id === "scrolling-preview"),
        detail: recipes.map((recipe) => recipe.id).join(","),
      },
    ];
    return { suite: "smoke", ok: checks.every((check) => check.ok), checks };
  },
};

const SUITES = new Map<string, BenchmarkSuite>([[smokeSuite.id, smokeSuite]]);

export function listBenchmarkSuites(): Array<
  Pick<BenchmarkSuite, "id" | "description" | "live">
> {
  return [...SUITES.values()].map(({ id, description, live }) => ({
    id,
    description,
    live,
  }));
}

export async function runBenchmark(
  id: string,
  context: BenchmarkContext,
): Promise<BenchmarkResult> {
  const suite = SUITES.get(id);
  if (!suite) throw new Error(`unknown benchmark suite: ${id}`);
  return suite.run(context);
}
