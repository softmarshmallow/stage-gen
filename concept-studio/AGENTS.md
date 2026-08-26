# Concept Studio guardrails

This subtree is an agent-facing pre-production project. Its only authored deliverables are text and
images that help a person decide what game they want before full generation.

- Use the `game-concept-studio` skill for concept requests.
- Keep drafts under `workspaces/<concept_id>/`; this directory is gitignored.
- Do not create or modify `game.toml`, maps, runtime manifests, recipes, source code, fixtures,
  library packages, web files, or engine assets as part of concept work.
- Use the dedicated `stage-gen-concept` CLI for live images. Live calls require explicit user intent.
- Keep provider prompts original and brand-neutral. Research game names never cross the provider
  boundary.
- `style-dictionary/` is the canonical tracked vocabulary, reviewed-prompt, and research reference.
  Its Markdown consumes individual previews directly; do not add a grid, contact sheet, or document
  render. Keep prompts brand-neutral and keep its manifest, shared exact-image review, and rights
  notice synchronized with the tracked preview set.
- `gallery/` is a publication surface. Promotion requires explicit authorization plus provenance,
  independent review, rights, inventory, and storage gates.
- Keep repository identifiers, logs, prompts intended for persistence, and authored files in
  English.
