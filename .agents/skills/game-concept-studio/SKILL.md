---
name: game-concept-studio
description: Develop an early game idea through conversation, a concise concept document, and exploratory cover art. Use for pre-production concept work before a user authorizes game generation; do not create game.toml, runtime assets, implementation plans, or playable code.
---

# Game Concept Studio

Work only inside the `concept-studio` project. The outcome is a game concept that a person can
read and look at before paying for full game generation. It is not a Stage Gen recipe input or a
promise that the depicted game has been implemented.

## Start from the short idea

Read the repository `AGENTS.md`, `concept-studio/AGENTS.md`, and
[references/artifact-contract.md](references/artifact-contract.md). Initialize one ignored
workspace with `stage-gen-concept init`; never place draft work in `library/`, `fixtures/`,
`docs/media/`, `src/`, or `web/`.

Expand the user's brief through conversation without turning it into a questionnaire. Make useful
assumptions explicit in `concept.md`, focus on the player fantasy and the game's visual identity,
and leave consequential choices as open questions. Do not author `game.toml`, maps, manifests,
schemas, implementation plans, source code, production asset trees, or engine/runtime decisions.

## Art direction

Before writing an image prompt, read
[references/style-library.md](references/style-library.md). Use it as a vocabulary and evidence
map, not an allowlist. The concept workflow may combine or depart from its entries using concrete,
observable visual language. Do not apply the runtime's three-mode style anchor, recipe layouts,
sprite constraints, camera contracts, transparency requirements, or asset-sheet conventions.

Keep rendering style, subject matter, camera/composition, production role, and adult-commercial
presentation as separate decisions. Game titles in repository research are human-facing anchors;
translate them into neutral visible traits before any provider call. Prompts for work that may be
promoted must request original, brand-neutral imagery with no protected characters, logos,
signatures, watermarks, or readable pseudo-branding.

## Image tool and model choice

Use only the dedicated `stage-gen-concept image` command for project images. It loads the
allowlisted `OPENROUTER_API_KEY` from the repository-root `.env`, keeps one retry owner, validates
provider media, normalizes PNG/JPEG/WebP into a real PNG, and writes portable provenance. Never
print, copy, rewrite, or assume the contents of `.env`.

Read [references/model-routing.md](references/model-routing.md) before choosing a model. Record the
selected model and a one-line reason in `concept.md`. Use each requested candidate as a separate
semantic generation. A disappointing but technically valid image is not a provider failure and
must not be retried by the transport loop. Do not silently fall back to another model.

Live calls are billable. Generate only when the user explicitly asks for or authorizes live image
work. Authorization for one concept or candidate count does not authorize additional variants.

## Review and cover selection

Inspect every candidate image itself. Compare it with the written concept for subject, player
fantasy, world cues, composition, style, unwanted text or marks, and visible protected material.
Keep rejected candidates in the ignored workspace. Use `stage-gen-concept select` to make the
chosen bytes `images/cover.png`, then run `stage-gen-concept check`.

An independently reviewed candidate may be promoted only after the user explicitly asks for
promotion and the repository's generated-media rights, provenance, storage, and inventory gates
pass. Never copy an exploratory image into `concept-studio/gallery/` merely because generation or
local validation succeeded.

## Handoff

Return the workspace path and the two human-facing deliverables:

- `concept.md`
- `images/cover.png`

Prompt files and `.meta.json` files are supporting text records. Do not claim a ZIP ingest path or
full-game generation handoff exists yet; the stable concept pair is deliberately suitable for a
future reference-package contract.
