# The Grain

Status: **story placeholder, not a prepared game package**.

This directory gives the selected story a durable repository home while its
writing continues. It intentionally has no `game.toml`, is not referenced by
`library/games/main.toml`, and has not passed game-package validation. Nothing
here should be described as playable or game-ready.

## Organization

- `story/foundation.md` contains the compact, ratified narrative foundation.
- `scenarios/index.toml` catalogs ratified executable narrative.
- Each scenario pairs a human-readable `.scenario` script with a `.toml`
  declaration of its cast, stages, flags, tracks, ending, and exact script
  digest. The pair uses the repository's implemented `scenario-v1` format.
- Additional story documents belong under `story/` only after their status and
  relationship to the foundation are explicit.
- Future game contracts, maps, interactions, assets, and generated material do
  not belong here until a separate game-preparation pass is authorized.

The scenario catalog does not make this a complete prepared game package. The
directory still has no root `game.toml`, no complete package closure, and no
canonical selector binding.

## Ratifying story work

1. Start from the exact story material supplied for ratification; do not assume
   that brainstorming or provisional prose is approved.
2. Add only director-selected story facts to `story/foundation.md`, or create a
   clearly named human-readable story document when the material outgrows it.
3. Preserve unresolved matters as explicit open questions. Do not fill narrative
   blanks merely because a game field will eventually require a value.
4. Keep the prose natural and implementation-neutral. The dialogue-first
   screenplay remains the narrative source; engine data is a later translation.
5. When a chapter is ratified as executable narrative, translate it into the
   closed `.scenario` vocabulary without inventing branches, flags, or endings,
   then update its digest and run the scenario admission proof.

## Preparing a game later

Treat game preparation as a separate conversion, not an edit to make the prose
look like a contract. Follow `library/games/AGENTS.md` and the live package
documentation, create an exact prepared closure with a root `game.toml`, and
validate it from the repository root. Remove or relocate this procedural README
if the exact-closure rules do not permit it.

The conversion agent should proceed in this order:

1. Choose and record the exact ratified story snapshot being adapted.
2. Inventory required game decisions and separate genuine narrative blanks from
   implementation-owned choices.
3. Return narrative blanks to the writing process; do not invent them inside a
   contract.
4. Translate the approved story into the current package structure in one
   internally consistent closure.
5. Validate the package and report authored validity separately from generated
   assets, playability, and publication readiness.
6. Request explicit promotion before changing the canonical selector.

Do not edit `library/games/main.toml` unless the user explicitly promotes this
game as the repository's selected canonical package. Conversion may identify
missing decisions and report them back to the story process; it must not silently
rewrite characters, mystery truth, or dialogue to satisfy implementation.
