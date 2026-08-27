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

## Climbable band atlas

- [ ] Close the middle-band rung phase before the tiled climbable contract admits generated bands.
      The model reliably obeys countable direction (how many rungs, which cells carry them) and
      unreliably obeys proportional direction (`one quarter of the cell height`), so roughly one
      band in three places its rungs such that every stacked join is 34-38% wider than the spacing
      inside a band, about 14-18px at the 64px runtime visual width. Cutting one rung period out of
      the band removes it deterministically and applied to 16 of 16 sampled ladders, but that
      changes the repeat unit from an authored band to a measured rung gap, so land it together
      with the world-unit mapping rather than as a patch. Constraining the rung count in the prompt
      is not the fix: it corrected phase direction but pushed rung spacing to 0.88 of the ladder
      width against 0.74-0.77 for the accepted baseline, which reads as a ladder no one could climb.
- [ ] Measure strand-type climbables before any claim of tiling correctness covers them. The rung
      rhythm metric keys on rows whose ink exceeds the strand baseline width, so a rope or vine
      carries no crosswise structure for it to see and every strand column reports unmeasurable.
      Ropes look correct in every composition rendered so far and nothing quantitative supports
      that. Either add a strand-specific periodicity measurement or restrict the contract to
      rung-bearing climbables and reject strands at admission.
- [ ] Replace the operator-supplied band-structure reference before promoting any climbable
      artwork. Every accepted band was generated with a reference the task owner licensed for spike
      use only and explicitly excluded from promotion. Its digest is recorded beside each run. A
      self-authored band template with a documented rights basis, as
      `fixtures/image_gen_templates/terrain_atlas_12x4_template.png` carries, must replace it and
      the artwork must be regenerated; do not promote bytes derived from the spike reference.

## Git reconciliation

- [ ] Reconcile origin commits `98e0214` and `00f90d1` only after the worktree is clean. Compare
      them with the local theme/compiler equivalents, retain each change once, and run the full
      offline gates; do not pull or merge them blindly over local work.
