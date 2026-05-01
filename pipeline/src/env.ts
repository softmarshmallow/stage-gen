// Env validation for the pipeline CLI.
// Fail-fast: if any required key is missing/empty, print to stderr and exit non-zero.
//
// Single source of truth for which env vars exist is `.env.example` at repo
// root — keep that file in sync when adding entries here.

export interface PipelineEnv {
  AI_GATEWAY_API_KEY: string;
  AI_GATEWAY_BASE_URL: string;
  IMAGE_MODEL: string;
  TEXT_MODEL: string;
  OUT_DIR: string;
}

interface EnvSpec {
  name: keyof PipelineEnv;
  required: boolean;
  default?: string;
  purpose: string;
}

const SPECS: EnvSpec[] = [
  {
    name: "AI_GATEWAY_API_KEY",
    required: true,
    purpose: "Vercel AI Gateway API key (auth for image-gen + text-gen).",
  },
  {
    name: "AI_GATEWAY_BASE_URL",
    required: false,
    default: "https://ai-gateway.vercel.sh/v1",
    purpose: "Vercel AI Gateway base URL.",
  },
  {
    name: "IMAGE_MODEL",
    required: false,
    default: "openai/gpt-image-2",
    purpose: "Image generation model id.",
  },
  {
    name: "TEXT_MODEL",
    required: false,
    default: "openai/gpt-5.5",
    purpose: "Vision LLM model id for the world-design agent.",
  },
  {
    name: "OUT_DIR",
    required: false,
    default: "out",
    purpose: "Output root directory (per-tag subdirs land here).",
  },
];

export function loadEnv(): PipelineEnv {
  const missing: string[] = [];
  const resolved: Partial<PipelineEnv> = {};

  for (const spec of SPECS) {
    const raw = process.env[spec.name];
    const value = raw && raw.trim().length > 0 ? raw : spec.default;
    if (!value) {
      if (spec.required) missing.push(spec.name);
      continue;
    }
    resolved[spec.name] = value;
  }

  if (missing.length > 0) {
    process.stderr.write(
      `stage-gen: missing required env var${missing.length > 1 ? "s" : ""}: ${missing.join(
        ", ",
      )}\n` +
        `  populate .env at the repo root (see .env.example for the full list).\n`,
    );
    process.exit(2);
  }

  return resolved as PipelineEnv;
}
