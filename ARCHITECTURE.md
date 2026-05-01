# Architecture

A small set of pre-pinned technology choices so the loop doesn't burn
iterations re-litigating them. Everything else is the agent's call.

## Stack at a glance

| Layer | Choice | Why pinned |
|---|---|---|
| Runtime + tooling | **Bun** | One binary for runtime + bundler + script runner + package manager. Native TypeScript, fast cold starts, zero build step for `bun run`. The pipeline scripts run as `bun <file>.ts` directly. |
| Web framework | **Next.js (App Router)** | Mature, batteries-included; serves the static demo + has API routes for streaming pipeline logs to the browser. Use the App Router (`app/`), not the legacy `pages/` router. |
| 2D game engine | **Phaser 4** | Long-lived, well-documented WebGL/Canvas 2D engine. Phaser 4 is the current major; it is functionally compatible with Phaser 3 — see [`docs/tech/phaser-4.md`](docs/tech/phaser-4.md). |
| Image generation | **OpenAI gpt-image-2** via Vercel AI Gateway | The asset contracts in [`docs/spec/asset-contracts.md`](docs/spec/asset-contracts.md) are written against this model. See [`docs/tech/gpt-image-2.md`](docs/tech/gpt-image-2.md) for what works and what to avoid. |
| Vision LLM (world-design agent) | **OpenAI `gpt-5.5`** | Reads the concept image, returns Zod-validated structured output. Flagship model; no fallback chain. |
| AI SDK | **`ai` v6 (`@vercel/ai`)** + `@ai-sdk/openai` | One SDK for both image-gen and structured-output text-gen. Talks to the gateway via env-var auth (`AI_GATEWAY_API_KEY`). |
| Schema validation | **Zod v4** | Used for the world-spec contract. Every Zod schema fed to `generateObject` follows the OpenAI-strict-mode rules in [`docs/tech/gpt-image-2.md`](docs/tech/gpt-image-2.md) (no `.optional()` — use `.nullable()`). |
| Image post-processing | **`sharp`** | Pipeline-side cropping, resizing, and slicing. Browser-side post (chroma-key, alpha-bbox crop, edge-fade) uses `<canvas>` directly — no extra dep. |

## Three workspaces

The repository has three concerns that should sit in three independent
workspaces (separate `package.json`s; one Bun monorepo via `bun
workspaces` is the cleanest layout, but plain top-level dirs also work).

```
<repo-root>/
├── pipeline/        ← Bun TypeScript pipeline scripts
│   ├── ai/          ← per-asset generators + world-design agent + retry wrapper
│   ├── post/        ← sharp-based slicing / cropping
│   └── orchestrator (a single `bun` script that fans out the gen calls)
│
├── web/             ← Next.js app
│   ├── app/         ← App Router routes (e.g. `/play/[tag]`)
│   ├── game/        ← Phaser scene(s) + asset loaders + runtime compositors
│   └── lib/         ← shared types, slug helpers, world-spec readers
│
└── fixtures/              ← committed static assets (same across all worlds)
    ├── image_gen_templates/ ← layout-prior PNGs
    ├── bgm/                 ← curated audio library (index.json + mp3s)
    ├── prompts.txt          ← example world prompts
    └── styles.txt           ← visual style hints
```

Generated outputs live outside the repo in `out/<tag>/` and are
gitignored.

## Why this split

- **Pipeline runs offline** (CLI, can be invoked from anywhere — terminal,
  Next.js API route, CI). It writes PNGs + JSON to a per-tag directory.
- **Web runtime is purely client-side** at gameplay time — it loads the
  per-tag directory the pipeline produced and renders the scene in
  Phaser. The Next.js layer is only there to serve the assets and host
  the API route that streams pipeline logs to the browser.
- **Layout-prior PNGs are committed** because they are part of the
  contract between the painter and the runtime slicer (see
  [`docs/spec/asset-contracts.md`](docs/spec/asset-contracts.md) §
  "Common contract: layout priors").

## What the agent must NOT do (architecture-level)

- Don't replace Phaser with another 2D engine. The compositing recipes
  ([`docs/spec/asset-contracts.md`](docs/spec/asset-contracts.md), parallax /
  chroma-key) are written against a `<canvas>`+sprite-image pipeline
  that Phaser handles natively.
- Don't move the pipeline into the Next.js process. The image-gen calls
  are 30–120 s each; running them inside an HTTP request handler means
  you're holding 25 in-flight requests open. The pipeline is a CLI; the
  web layer streams its stdout.
- Don't introduce a frontend framework on top of Phaser (React, Vue,
  Svelte) for the gameplay scene. The Phaser scene IS the UI.
  React/Next is fine for the upload form, the log viewer, and routing.
- Don't switch image models without re-validating every per-asset
  contract — see [`docs/tech/gpt-image-2.md`](docs/tech/gpt-image-2.md)
  for the model-specific quirks the asset contracts depend on.
