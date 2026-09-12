# Repository reshape: asset product and independently owned games

Implemented under the repository-wide authorization of 2026-09-12. The current
layout is [the directory preview](../repository-layout.md). The product is the
asset pipeline and SDK; complete games are consumers. Existing TOML readers,
media bytes and paid-node cache identities remain supported under legacy ownership.

## Implemented changes

| Area | Result |
|---|---|
| Public authoring | `stage_gen.pipeline` exposes Python definitions, planning, target selection, execution and inspection over the existing GNode engine. |
| Asset capabilities | UI, effects, screens, music, voice profiles, structural terrain and actor scale were separated from game aggregates. |
| Recipes | Looping parallax and portrait motion have bounded recipe ownership; universe and storefront retain independent asset contracts. |
| Examples | Arbitrary PNG/WAV graphs, portrait processing, supplied-layer parallax and standalone storefront inputs demonstrate independent use. |
| Preview | The viewer accepts arbitrary public pipeline identities, preserves unfamiliar metadata and provides a working parallax inspector. |
| Godot | A consumer-owned import script and GDScript template demonstrate the new asset-to-application boundary. Existing games/packages remain separate projects. |
| Legacy demos | Five whole-game recipes, their game contracts, authored inputs, Python tooling and shared runtime moved under Godot. |
| Library | Removed; the empty private placeholder supplied no remaining ownership reason. |
| Optional applications | Concept Studio has separate packaging and an explicit external workspace root. |
| Distribution | Core wheel/sdist omit legacy packages, game vocabulary, demo music and the full demo routing census. Standalone sdist metadata does not require the monorepo workspace. |
| Guidance | Root architecture, onboarding, authoring skills, scoped legacy references and verification gates now follow these owners. |

The old TOML documents were not redesigned as a prerequisite. New asset pipelines
can use recipe-local TOML or ordinary Python; complete gameplay belongs to consumer
scripts and scenes. A bounded scenario, sprite, parallax or animation format does
not have to become part of a universal game schema.

## Preservation and compatibility

The scheduler, route preflight, retry ownership, atomic persistence, provenance,
cache validation and explicit provider opt-in remain the execution substrate.
Whole-game code imports the product; the product does not import legacy code.

The migration initially changed a source-lock digest by updating a path inside a
TOML comment. Restoring that comment preserved all original scope cache goldens;
no paid node acquired a new key just because its implementation moved directories.
Existing media and sidecar bytes were relocated intact, with their original rights
and review records. No provider generation, publication, release or commit was made.

## Validation evidence

Completed independent checks include:

- A fresh core wheel installed outside the checkout passed 1,699 selected product tests with both optional package imports blocked. Product code loaded from the wheel; third-party dependency modules were reused from the development environment without executing editable hooks.
- The complementary legacy selection passed 1,141 tests, including existing readers, game plans, cache goldens and moved command dispatch.
- The viewer passed 168 tests and TypeScript checking. Its webpack production build passed; the default Turbopack build encountered this environment's IPC bind restriction.
- A real local parallax run was inspected in the browser: images loaded, scrolling used each layer's declared factor and visibility controls changed the composition.
- The retained native Godot suite passed 4,329 checks across 47 files. Its fixture does not assert the 16 checks pinned to a real generated run. The new image-consumer template also passed its native loading test.
- Core packaging was built from the standalone source archive and installed through pip. The measured core wheel is approximately 0.86 MB compressed; demo-only resources are absent.
- All public/legacy input smoke commands and deterministic asset examples passed without provider calls. Publication inventory retained two existing reviewed entries.

The aggregate `uv run --all-groups python scripts/check.py --scope all` passed all
37 steps, including 2,885 Python tests, formatting, strict typing, builds, viewer,
Godot, documentation and all input smoke commands. Seven live tests were deselected.

Independent review additionally closed cancellation cleanup, cache-failure
accounting, barrier-input reads and external sibling-import behavior. The expanded
reliability/cache/import suite passed 529 tests; its concurrent import-guard failure
was corrected and passed separately with three installed-consumer tests. All four
review reproductions then passed against a freshly built and installed wheel with
optional consumers blocked. Invalid roots are refused before execution; failed
cache persistence retains spent operations/cost without persisting cache filenames.
The final focused checks cover the changes made after the aggregate run started:
38 pipeline/loader/import tests and 15 package/documentation/gate tests passed.
Final Ruff formatting/lint and strict mypy over 728 files passed. Both optional
legacy and Concept Studio distributions also built successfully as wheels.


## Practical limits

The parallax recipe currently composes supplied layers; reference-to-layer
extraction remains an upstream capability to implement when required. The new
examples prove local processing and consumption, not semantic approval of generated
art. Existing demos retain their old game-specific TOML and host code rather than
being rewritten as new templates. Neither limitation expands the public contract.
