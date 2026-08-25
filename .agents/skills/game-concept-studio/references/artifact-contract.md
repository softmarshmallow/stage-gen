# Concept workspace contract

## Draft location

Every draft is confined to:

```text
concept-studio/workspaces/<concept_id>/
```

The complete directory is gitignored. `<concept_id>` is lowercase hyphen-case. One concept uses
one workspace; multiple image candidates live in that same workspace.

## Human-facing deliverables

```text
concept.md
images/
  cover.png
```

`concept.md` is flexible prose, not a schema. It should make the following understandable when
they matter to the idea:

- title and one-sentence pitch;
- player fantasy and core play rhythm at concept level;
- world, tone, characters, or factions;
- visual direction in observable terms;
- cover-art direction and candidate/model rationale; and
- assumptions and open questions.

Do not add `game.toml`, a manifest, maps, gameplay contracts, implementation tasks, source code, or
an engine asset hierarchy. The concept may discuss mechanics, but it must not encode runtime
behavior.

## Supporting records

The agent may add Markdown or text prompt notes and these tool-owned files:

```text
images/candidate-01.png
images/candidate-01.png.meta.json
images/cover.png.meta.json
```

The sidecars are operational provenance, not additional authored product contracts. The selected
cover must be byte-identical to one reviewed candidate unless a new review is performed after a
transformation.

## Promotion boundary

`concept-studio/gallery/<concept_id>/` is a repository publication surface, not a second working
directory. Promotion requires an explicit current user request, an independent artifact-bound
visual review, exact prompt/model lineage, an artifact-specific rights notice, inventory binding,
and all repository media checks. Draft authorization does not imply promotion.
