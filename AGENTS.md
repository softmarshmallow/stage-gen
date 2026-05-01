# AGENTS.md

Concept and tech setup live in [README.md](README.md). This file covers practices and gotchas specific to working in this repo.

## Orchestration

The main agent plans and orchestrates. It does not execute the work itself.

Before doing anything non-trivial, the main agent should sketch the subagent fan-out: what each subagent gets, what it returns, and how results compose. The build target is well-defined — most steps are delegations, not exploration.

## Vision payloads — hard rule

**The main agent does not read images.** Not generated outputs, not reference templates, not fixtures, not screenshots. Every image touch happens inside a subagent.

This applies even when the prompt and template are pre-tested and "should just work." Any image entering the main context burns budget that compounds across the loop. One image is fine; the tenth is fatal.

Concrete tripwires:
- No `Read` on files under `fixtures/`, `example-output/`, or any `*.png` / `*.jpg` / `*.webp`.
- Vision verification is always a subagent call, even for a single output.
- If a subagent returns an image path expecting the main agent to "just check it" — push it back as a verification subagent.

## Verification

Every vision payload gets verified at least once, by a **different** subagent than the one that produced it. The verifier sees the spec and the output, not the generation prompt — otherwise it tends to confirm what was asked for instead of what was rendered.

Verification subagents return a structured verdict (`pass` / `fail` + short reason), not a description of the image.

On `fail`: bounded retries (default 2), then surface to the user with the verifier's reasons. Do not loop indefinitely on the same failing stage.

## Shared TODO

Maintain a single TODO file (`TODO.md` at repo root) that both the main agent and subagents read and write. This is the coordination surface across the loop:

- Main agent writes the plan as TODO entries before fan-out.
- Subagents tick off their assigned items and append findings or follow-ups.
- Next iteration's main agent reads TODO first to recover state without re-deriving the plan.

Keep entries short and outcome-shaped (`[ ] verify stage-3 lighting matches ref`), not narrative. Prune completed sections aggressively — TODO is working memory, not a log.

## Subagent output budget

Cap every subagent's return. Default: under 200 words, or a fixed schema (verdict + path + one-line reason). A subagent that returns a paragraph describing what it saw in an image has just leaked the image into the main context.

If a subagent needs to communicate more than the cap, it writes to a file and returns the path.

## Cost is not a constraint

This project does not optimize for token or API cost. Env is provisioned for free use of the AI SDK. Agents should call the SDK as much as needed to validate that a pipeline stage works — extra exploratory calls, comparison runs, and sanity checks are encouraged. Do not skip a verification, retry, or experiment to "save calls." The only budget that matters is the main agent's context window (see vision rule above).

## Retry every AI call

Every AI SDK call must be wrapped in a retry. The SDK fails randomly — transient network errors, model hiccups, schema-violating outputs. A single un-retried call is a latent bug.

Default policy: **5 blind retries** with backoff before surfacing failure. Apply this at every AI-dependent point in the pipeline — generation, verification, structured-output parsing, anything that hits the model. No bare calls.

Retry on the obvious (network, 5xx, timeout) and on the silent failures too: malformed JSON, schema mismatch, empty output. If the call's contract isn't met, retry.

## Env

`.env` at the repo root is gitignored but **already populated** with working keys (image-gen, text-gen, gateway URL). Treat it as a ready resource, not a thing to set up.

When a workspace needs its own env (e.g. the Next.js app reading `process.env.*` at build/runtime), **copy** the root `.env` into that workspace's expected location (`web/.env`, `web/.env.local`, etc.) — same copy-don't-symlink rule as fixtures. Each workspace gets its own copy; do not try to share by reference.

`.env.example` is the source of truth for *which keys exist*. Keep it in sync when the agent introduces a new env-dependent step.

## Fixtures

Pre-defined assets (reference templates, sample inputs, etc.) live under `fixtures/`. Use them directly from that path, or **copy** them into wherever the actual service consumes them — e.g. a Next.js app would copy needed assets into `public/`.

Do not symlink. Symlinks break across build steps, deploy targets, and platform tools in ways that are tedious to debug. Copy is cheap; pay the duplication.

## Reproducibility for vision

When a subagent generates an image, it persists alongside the output: prompt, seed, model, reference path, and any params. The main agent uses these to dispatch a retry without ever loading the image itself. If this metadata is missing, a failed verification becomes unrecoverable from the main context.
