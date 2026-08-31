# TODO

Only unresolved current-tree work belongs here. Provider runs, generated-media promotion, and
publication still require explicit authorization even when their implementation gates are ready.

## Exact current contracts

- [ ] Remove remaining alternate public shapes instead of maintaining readers for them. The
      audited debt includes camelCase artifact/capability and doctor output, the scrolling manifest,
      `legacyDialogueBeats`, and tracked historical JSON below `web/public/dialogue-scene/demo/anime/`
      and `docs/media/`, plus `docs/generated-media-inventory.json`. Replace or retire each contract
      atomically with its consumers, digest bindings, and rejection tests; do not add aliases.

## Scenario

The decision and target contract are in [scenario](docs/spec/game/scenario.md). M1 and M2 are
ordered but coupled: branching without skip-already-read is unexplorable in practice.

- [x] M1 increment 1 — the authored contract, the Ren'Py-shaped script surface, the compiler, and
      the reachability proof. `src/stage_gen/components/scenario/`, the authored
      `library/games/larkfield/scenario.toml` beside its script, and `stage-gen scenario check`.
      Recipe-neutral by construction: it is a component, not a recipe, because two genres are meant
      to consume one authored shape.
- [x] M1 increment 2 — the runtime reducer (`web/lib/scenario/`), the scene's digest-bound scenario
      binding, and both consumers drawing choices and named endings. The visual novel is registered
      in `web/lib/shell/scene-modules.ts`, which it had never been.
- [x] M1 increment 3 — the cast-and-stage fan-out. The graph reads no fixed count: one backdrop per
      declared stage, one profile/plan/neutral/derive/canonicalize chain per drawable actor.
      Larkfield now ships three drawn actors across three stages, generated in one 38-node run
      (15 provider images).
- [ ] Independent semantic review of the twelve expression plates and three backdrops in
      `out/larkfield/`. Generated visuals are unreviewed by default and need a verdict from someone
      other than their producer before any of it is treated as acceptance evidence or published.
- [ ] Larkfield's style plate still shows one specific character. This is an authoring defect in
      one package, not a system one: `style_reference_id` and a cast member's `reference_id` are
      independent, a plate bound by nobody validates, and `has_identity_plate` then goes false for
      every actor, so a character-free art-direction plate is already fully expressible with no
      code change. Larkfield simply points both at `cover`. Nothing is broken today - the prompt
      clauses were split so only Nao is held to the plate's identity - but a second scene reusing
      this package would inherit Nao's face as its house style. The fix is a split rather than a
      swap: declare a character-free `style` plate and let Nao keep the current image as her own
      identity plate, since a swap alone would leave her identity binding pointing at nobody. Pure
      authoring, but the style plate's digest is in every image node's cache identity, so it
      re-bills all 15 images - batch it with the next run that regenerates anyway.
- [ ] M2 — land the player shell: persistence, save slots, backlog, skip-already-read,
      auto-advance, preferences. Cross-genre, and the same missing substrate the champion roster
      is blocked on — build it once for both.
- [ ] Collapse the last parallel narrative shape. `[[dialogue]]` and the theme installer are gone;
      what remains is `game-sequence-v1` in bellweather and the platformer's untyped inline graph
      walk in `web/lib/sideview-platformer/prepared-scene.ts` (reached through an `as unknown as`
      cast), plus `web/lib/sideview-platformer/dialogue-box.ts`, which is dead code nothing imports.
      Rewrite bellweather's four sequences in the scenario surface, delete `game-sequence-v1` and
      `game-sequence-catalog-v2` rather than aliasing them, and point the platformer at
      `web/lib/scenario/runtime.ts`. `web/lib/dialogue/conversation.ts` is then the degenerate case
      of that runtime and should go with it.

## Runtime acceptance

- [ ] Add the producer-owned `character-hurt` four-frame strip and optional runtime-manifest entry.
      The web runtime and synthetic fixture already accept the optional role, but the Python recipe
      still produces only `character-attack`; bind generation, raster/alpha/scale validation,
      provenance, and producer-to-consumer tests before promoting artwork.
- [ ] Add one village gameplay-harness scenario that boots the authored social-hub map and proves
      the flat stage, resident loading and scale, dialogue gating, and portal transition together.
      Component and runtime unit coverage exists; this missing end-to-end scenario must use reviewed
      art before it becomes visual acceptance evidence.

## Sprite anchoring

- [ ] Give every motion frame a real anchor point. The pipeline has never had one. Registration is
      inferred from an alpha-bounding-box edge instead: `repack_alpha_components` aligns each crop
      against a cell edge, and the runtime places the sprite with
      `repackedMotionFootOriginY`, which is `1 - gutter / frameHeight` - the bottom of the cell. A
      bbox edge is not an anchor. It is a property of whatever pixels happen to be painted, so it
      moves whenever a limb extends past its previous extreme, and it cannot express a registration
      point that sits inside the figure. The point a 2D animator would actually pin - the pelvis for
      most locomotion, the contact foot for a walk cycle, the grip for anything hanging - is
      interior, differs per frame, and coincides with a bbox edge only by accident.
- [ ] The gap stayed invisible because every state until now kept its feet on the ground. When the
      feet are the contact point and the pose is upright, the bbox bottom is within a few pixels of
      the true anchor, so bottom-anchoring was right by luck rather than by contract. Player
      `climb_rope` is the first state whose stable point is not its feet, and it failed loudly: with
      bottom anchoring the two cells agreed on the feet to the pixel and disagreed on the head by
      751px, a quarter of the figure, which read in play as the character bouncing rather than
      climbing. `climb_ladder` sat at 58px and looked fine, which is exactly why nothing caught it
      earlier - the defect scales with how far a state's true anchor sits from its bbox edge.
- [ ] Note that the repo has already learned half of this lesson somewhere else. Scale is matched on
      the head, not the feet: `scale_reference.py` records that a figure's painted height is a
      property of its pose rather than its build, and `headMatchedScale` in the runtime sizes every
      sheet against the idle head for that reason. Sizing therefore uses a stable interior feature
      while registration still uses an unstable outer edge. Anchoring should end up on the same
      footing as scale, and the head-matching machinery is the closest working precedent to copy.
- [ ] Scope the experiment before building anything, because the acquisition method is the open
      question and each option has a different failure mode. Candidates: author anchors per state in
      the game package; ask the image model to place a visible registration marker and detect it;
      label anchors after generation with a VLM pass; estimate them geometrically from the silhouette
      (torso centroid, hip line); or assume a skeleton and fit it. Prompted markers and VLM labels
      both need an accuracy budget measured in pixels against hand-labelled truth before either can
      be trusted, and both add a per-frame failure mode the current edge rule does not have. Whatever
      wins has to be persisted in the artifact contract and the runtime manifest, and consumed in
      place of `repackedMotionFootOriginY`, so it is a contract change on both sides rather than a
      recipe tweak.
- [ ] Whatever replaces this must be re-applied at draw time, not only baked into the packing.
      `loadFrameStrip` re-measures every cell with `extractCellsBbox` and registers each Phaser frame
      as a tight alpha crop, so the producer's packing offsets are gone before a sprite ever draws:
      however the strip was packed, every frame arrives flush against its own painted bounds. A
      first attempt at the climb fix packed the artifact correctly and changed nothing on screen for
      exactly this reason - the artifact measured top-registered while the runtime kept standing
      each frame on its own lowest pixel. Any anchor that survives only in the packed bytes is
      erased by that step.
- [ ] Until the real system lands, the climb states carry a deliberate stopgap: `anchor` on
      `MotionPresentation`, authored per motion, `bottom` or `top`, consumed by
      `anchorMotionFrame` in the runtime. It is still an edge rule and inherits every limitation
      above - it can only pin an extreme, so a state whose stable point is interior, or which needs
      a different anchor per frame, remains unrepresentable. Do not mistake it for the anchor system;
      it buys correct registration for two states whose stable point happens to be an extreme.

## Player identity reference

- [ ] Give the prepared concept sheet a rear view, or stop declaring states rear-facing. Today
      `_generate_concept` asks for exactly two views, "one complete side-view game-scale figure and
      one front-three-quarter identity view", and that string has been unchanged since the first
      prepared commit `025d6b5`, so the prepared path has never rendered the back of any actor.
      That same sheet is the only reference every later atlas receives: `_generate_motion` and
      `_generate_dialogue` each pass a single `ImageReference` to `concept.png` and nothing else,
      while the concept prompt calls itself "the strict identity source for all later motion and
      dialogue atlases". The player climb states are declared rear-facing by `motion_source_facing`,
      so the states whose artwork is entirely back-facing are extrapolated from a sheet that has no
      rear information at all - the back of the costume, the hang of the satchel, and whether the
      sword reads from behind have never been authored, generated, or reviewed anywhere. The legacy
      tag path did render front, side, and back (`_turnaround_prompt`, executor.py) and appended
      `character_proportion_prompt(heads_tall)`; the prepared path dropped both, and relies instead
      on a "2.25-head-tall" phrase duplicated by hand into `style.keywords` with nothing keeping it
      in sync with the structured `[proportion]` field. Note what this is not: a measured fix for
      equipment drift. Supplying a faked rear view as a second reference did not improve it in a
      four-strip spike - the sword survived one of two strips generated from the concept alone and
      neither of two generated with the rear view added - so close this as the contract gap it is
      and gate equipment separately. Landing it re-digests the concept node and invalidates the
      whole player fan-out, roughly twelve provider images, so sequence it before any other player
      regeneration rather than paying that cost twice.

- [ ] Pick one canonical name for the multi-view character sheet and make it a first-class input or
      a first-class node. The artifact that should be the single source of truth for an actor's
      identity is currently called at least seven things across the tree - `identity concept` (6
      occurrences), `character-master` (4), `concept turnaround` and `turnaround sheet` (2 each),
      plus `character turnaround`, `concept sheet`, and `identity source` - and the file is
      `concept.png` in the prepared path against `character_concept_<tag>.png` in the legacy one.
      Settle on a single term, rename the stage, the artifact, the prompt wording, and the docs
      together, then decide where the sheet comes from: either the authored game-input package
      supplies a reviewed multi-view sheet directly, the way `references/` already supplies rights-
      bound source images, or the graph gains an explicit node that generates one before any motion
      or dialogue node depends on it. Today neither is true - `library/games/bellweather` authors
      only `references/cover.png`, a scene illustration with one three-quarter pose, and the sheet
      is a side effect of the concept node. Doing this together with the rear-view gap above avoids
      re-digesting the concept node and re-running the player fan-out twice.

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

## Platformer map design

- [ ] Add the `canopy` word to the chunk vocabulary and measure it against the row-painting
      baseline. Density is the one axis the grammar measurably does worst: chunk maps average a
      platform width of about 4-5 columns where the run-length row format averaged about 9-11, so
      chunk silhouettes have real shape and thin cover while RLE maps had broad cover and no
      shape. The fix is a vocabulary word, not a second format - a scatter of jump-linked
      platforms over a declared span, which is composition sugar over the primitives the contract
      already carries and needs no validator, profile, or contract change. Measure the resulting
      mean platform width against the recorded RLE figure, because adding the word without
      re-measuring leaves the density claim exactly as unproven as it is now.
- [ ] Split `PLACEMENT_ONLY_CLIMBABLE_FIELDS` out of the climbable atlas cache identity, mirroring
      `PLACEMENT_ONLY_GROUND_FIELDS`. The ground node already excludes `occupancy`, `vertical_fit`,
      and `walk_surface_row` from what the image model is asked to paint, which is why reshaping
      terrain costs nothing; the climbable node still digests its whole authored block, so moving
      one placement's `normalized_x` re-bills an atlas image that would return byte-identical.
      Placement is consumed downstream of generation on both sides, so the asymmetry is an
      oversight rather than a contract difference. Landing it makes iterating on climbable
      positions free the way terrain already is, and it must update the graph contract and its
      cache-identity assertions in the same change.
- [ ] Do not let any profile declare `biomes` until a ground mode can consume them. The design
      module can already express per-region appearance - the tag is physics-neutral, membership
      and paintable span are validated, and per-chunk tagging lands switches on landmarks for free
      - but `game-map-v9` binds exactly one terrain atlas per map and exposes no per-region style
      surface, so the choice would have nowhere to go. This needs a new mode under `[ground]` with
      its producer, validation, manifest, and consumer paths implemented first, exactly as the map
      contract requires of every future ground mode. A profile that declares biomes before then
      lets the designer make a claim no consumer can honour, and the failure would surface as
      wrong art rather than as a rejected package.
- [ ] Treat applying a design to a shipped map as its own authorized operation, never as a step
      inside a design run. The shipped map TOMLs are pinned byte-for-byte, so a new occupancy
      matrix co-updates the byte-level assertions in
      `tests/unit/components/game_map/test_prepared_game_map.py`. The edit stays inside the map
      TOML, because the resolver computes every member digest at capture time rather than reading
      an authored one. It also re-bills the climbable atlas image for as long as the cache split
      above is open. Sequence the split first if a run intends to move placements, and keep the
      design and the apply as one reviewed change rather than two partial ones.

## Camera

- [ ] Retire the deleted scene's two orphaned camera helpers. `verticalCameraScrollY` in
      `web/lib/runtime/vertical.ts` and `horizontalCameraScrollX` in
      `web/lib/runtime/camera-follow.ts` both drove `scene.ts`, which `6853a3d` replaced with
      `prepared-scene.ts`. The prepared scene uses Phaser's own dead-zone follow on both axes, so
      neither helper has a caller and only their own tests reference them. Leaving them in place
      reads as if they were the intended path. Delete them with their tests, keep
      `VERTICAL_CAMERA_MIN_SCROLL_Y` only if the platform bound in `createVerticalWorld` still
      wants it, and re-pin `GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS` in
      `web/tests/gameplay/harness.ts`, whose exact scroll values date from that same deleted scene.
- [ ] Take `map_direction` out of the terrain node's identity. Terrain is geometry; the game's
      visual direction and `continuity` are art direction, and neither shapes a chunk sentence.
      Today an unrelated palette or loop-construction edit re-composes both maps. The camera and
      the terrain request are the real inputs and are already recorded. This is the same split the
      ground and climbable nodes already have, applied one node further along.
- [ ] Decide whether partial vertical parallax is wanted before any layer needs it. The layer
      contract now resolves in two spaces, world and screen, which needs no vertical slack because
      a world layer moves with the world and a screen layer does not move at all. A coefficient
      between the two would need slack that does not exist: map layers are painted 1536x1024 and
      scaled by 720/1024, so they are exactly one viewport tall. Scaling to fill width instead
      would yield 133px of slack with no regeneration, at the cost of an 18 percent change in
      apparent scale and therefore a fresh semantic review of every map layer.

## Git reconciliation

- [ ] Reconcile origin commits `98e0214` and `00f90d1` only after the worktree is clean. Compare
      them with the local theme/compiler equivalents, retain each change once, and run the full
      offline gates; do not pull or merge them blindly over local work.
