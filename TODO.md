# TODO

Only unresolved current-tree work belongs here. Provider runs, generated-media promotion, and
publication still require explicit authorization even when their implementation gates are ready.

## Exact current contracts

- [ ] Collapse the Python `dialogue-scene` request, plan, review, and bundle models onto one exact
      lower_snake_case contract. `character_profile` remains optional by presence; delete the V2/V3
      dispatch and unions, reject every other schema/kind, and update core examples, tests, docs,
      and the Python-to-web boundary together.
- [ ] Remove remaining alternate public shapes instead of maintaining readers for them. The
      audited debt includes camelCase artifact/capability and doctor output, the scrolling manifest,
      `legacyDialogueBeats`, and tracked historical JSON below `web/public/dialogue-scene/demo/anime/`
      and `docs/media/`, plus `docs/generated-media-inventory.json`. Replace or retire each contract
      atomically with its consumers, digest bindings, and rejection tests; do not add aliases.

## Runtime acceptance

- [ ] Add the producer-owned `character-hurt` four-frame strip and optional runtime-manifest entry.
      The web runtime and synthetic fixture already accept the optional role, but the Python recipe
      still produces only `character-attack`; bind generation, raster/alpha/scale validation,
      provenance, and producer-to-consumer tests before promoting artwork.
- [ ] Add one village gameplay-harness scenario that boots the authored social-hub map and proves
      the flat stage, resident loading and scale, dialogue gating, and portal transition together.
      Component and runtime unit coverage exists; this missing end-to-end scenario must use reviewed
      art before it becomes visual acceptance evidence.

## Media and publication

- [ ] Resolve the 12 stale lineage bindings across the four published gameplay/dialogue captures:
      verifier, fixture, and timeline for each gameplay artifact; source, fixture, and timeline for
      the dialogue showcase. Recapture and independently review current bytes, or retire the
      publication; never rewrite hashes to bless stale media.
- [ ] Keep `concept-studio/gallery/the-sky-remembers/` and its inventory entry uncommitted until the
      authenticated task owner explicitly authorizes publication of the exact reviewed WebP. Then
      update the repository media-count/binding test from six to seven and run the publication,
      storage, and documentation gates as one atomic change.

## Git reconciliation

- [ ] Reconcile origin commits `98e0214` and `00f90d1` only after the worktree is clean. Compare
      them with the local theme/compiler equivalents, retain each change once, and run the full
      offline gates; do not pull or merge them blindly over local work.
