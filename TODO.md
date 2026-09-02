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
- [x] M1 increment 4 — script-driven music. The scenario already declared tracks and admission
      already proved every `play`/`stop` names one; what was missing was generation and playback.
      One track per declared track, carrying the soundtrack component's own `TrackGenerationIntent`
      rather than a second shape, compiled by the one prompt compiler both recipes now share.
- [x] Independent semantic review of the twelve expression plates, three backdrops, and three
      music tracks in `out/larkfield/`, and of the visual novel's play. Given by the task owner on
      2026-09-01; the producer did not give it. This covers acceptance of the run in `out/larkfield`
      only - publication remains a separate authorization.
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
- [x] Collapse the last parallel narrative shape. `game-sequence-v1` and
      `game-sequence-catalog-v2` are deleted rather than aliased, bellweather's four conversations
      are authored scenarios proven finishable offline, and the platformer walks
      `web/lib/scenario/runtime.ts` instead of an untyped inline graph reached through
      `as unknown as`. `dialogue-box.ts` and `lib/dialogue/conversation.ts` went with them. One
      authored narrative contract, one runtime, two genres.

## Runtime acceptance

- [ ] Add the producer-owned `character-hurt` four-frame strip and optional runtime-manifest entry.
      The web runtime and synthetic fixture already accept the optional role, but the Python recipe
      still produces only `character-attack`; bind generation, raster/alpha/scale validation,
      provenance, and producer-to-consumer tests before promoting artwork.
- [ ] Draw the runner's `hurt` motion, and switch both runner packages to
      `hurt_representation = "drawn_v1"`. The seam is already built and costs no second schema
      bump: `runner-gameplay-v3` refuses `drawn_v1` without a declared `hurt` motion and
      `blink_v1` with one, so the upgrade is a one-word authored change plus regeneration. What it
      does cost is real: `RUNNER_MOTION_ORDER` grows, the graph gains a generate/validate pair per
      package, `topology_sha256` and the embedded runner contract move, `runner_prompts.py` needs a
      hurt direction beside its death one, and the art needs semantic review by a non-producer.
      Pairs naturally with the platformer `character-hurt` strip above - one art pass, two genres.
- [ ] Consider binding a `hurt` audio cue. Deliberately not taken with the vitals pass: it would
      bump `runner-audio-v1` for feedback the platformer does not have either, and the blink plus
      the bar's dim already say a blow connected. Authoring only when it happens - one binding and
      one oscillator realization per package, no art spend.
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

## Rendering

- [ ] Sprites are still minified without mipmaps. Every game now draws at device pixel resolution
      (`web/lib/device-pixels/device-camera.ts`, `40a3750`), which removed the visible pixelation
      on the runner's player, but the underlying sampling is unchanged: an actor sheet's figure
      is 500-700 source pixels tall and drawn at 154 design pixels, so even at a 2x device ratio
      the GPU takes one bilinear tap per output pixel across a 2x2 texel footprint or wider.
      Phaser leaves `mipmapFilter` empty by default and only generates mipmaps for power-of-two
      textures, which the 1536x1024 atlases and alpha-trimmed cells are not. If jagged sprites
      return - on a 1x screen, a taller design-space character, or a heavier minification - the
      fix is a filtered pre-shrink of the trimmed cells at load time toward display height times
      device ratio, or power-of-two padding plus `render.mipmapFilter`. Higher source resolution
      makes it worse, not better.

## Runner gameplay: the CookieRun adoption

The reference is **CookieRun: OvenBreak**, adopted for its level *language* and explicitly refused
for its level *architecture*. Canabalt is the closer structural mirror - procedural, un-memorisable,
one verb - and its famous rule, that the maximum gap is a live function of current speed so the
world cannot lie to you, is the runtime-heuristic version of a proof we already run offline and
earlier: `JUMP_PROFILES["single_arc_v1"]`
(`src/stage_gen/components/runner_gameplay/models.py:50-52`) is consumed by
`_validate_runner_member` (`src/stage_gen/orchestration/game_package.py:789-864`) before any
provider node exists. Picking Canabalt would mostly teach us we are already right. CookieRun is the
reference for what we genuinely lack: a level language whose vocabulary matches the verb set. Its
four obstacle classes key one-to-one to inputs, and its Jelly trail writes each class as a distinct
shape - a rising arc means jump, a low ground-hugging band under an overhang means slide. The trail
is routing, not decoration, and because the collectible is also the score, greed and survival point
the same way: the player is never asked to learn the level, only to be greedy, and being greedy
walks them down the safe line.

That device is the only teaching channel that survives our architecture, and it is the compensating
mechanism rather than a nicety. `selectChunkIndex` (`web/lib/sideview-runner/segments.ts:54-69`)
draws uniformly from every eligible chunk, so the chunk that teaches and the chunk that tests cannot
be ordered and every telegraph must work on first sight. At `tile_px` 64 against a 1280px viewport
with the avatar pinned at column 5, lookahead is 15 columns - 2.50s at base speed, 1.67s fully
ramped - against a terminal `hazard` consequence, which was the only
      consequence `runner-gameplay-v2` could express. A package that now spends a point instead
      buys reaction time the argument below never priced in: the budget still has to hold for a
      one-hit-kill package, so the reasoning stands as the worst case rather than as the only case. Enough to react, not enough to plan. Rayman's
contextual verbs need non-local state the seam rule forbids by construction; BIT.TRIP's trail
arrives welded to a beat contract; Jetpack Joyride's to a flight verb that discards our terrain
contract. CookieRun hands us the device with nothing bolted to it, and `RunnerPickup` is already
`{item_id, column, row}` (`src/stage_gen/components/runner_track/models.py:64-69`), capped at 32 per
chunk, streamed and scored. **The whole trail mechanic is expressible today at zero contract cost
and zero art cost, and the committed fixture spends its pickups on three decorative dots.**

What is refused from the reference, so the adoption is not mistaken for wholesale: CookieRun
hand-builds 25-stage episodes whose fairness guarantee is a human seeing the next 40 columns. Ours
is an offline admission proof run credential-free before a cent is spent, which turns an unclearable
gap into an authoring error rather than a playtest discovery. That is strictly the better property
and is not for trade. Also refused is their per-stage economy tuning, because every one of those
dials is an *authored number* and this contract's docstring says it has none.

Sequencing note, learned the hard way in review: the selection grammar must NOT ship before the
catalog is re-authored. Simulated against the shipped `{meadow_flat 1, cart_lane 2, brook_gap 3,
hay_run 3}`, a sliding difficulty band has nowhere to slide to and converts "difficulty stops
progressing after twenty seconds" into "the track becomes an empty flat treadmill for the remaining
four minutes of the speed ramp" - strictly worse than today, and no gate catches it, because the web
suites use their own fixtures and the Python gate never touches runtime selection.

- [x] **Admission hardening I - the seam apron, hazard spacing, and the rise that skips across
      pits.** Two proven holes ship unwinnable moments today. First the seam: a chunk ending a
      3-column pit at columns W-4..W-2 with W-1 supported passes every check (`max_pit_run()` is
      exactly `max_clear_gap_columns`, both seam columns sit at `walk_surface_row`), and any chunk
      with a hazard at column 0 may follow it - `cart_lane` already places one at column 6 and
      column 0 is equally legal. The avatar lands on the seam and meets the hazard one column later:
      0.167s at base speed against 0.767s of airtime and a ~200ms human reaction. No surviving
      launch frame exists. Per-chunk admission structurally cannot see it because the loop at
      `game_package.py:829` never touches a neighbour - which is the seam rule's whole purpose, so
      the apron is the price of keeping it, not an argument against it. Second the rise:
      `game_package.py:857` guards on `right_column == left_column + 1` and the `supported` list
      omits pit columns, so a pit followed by a bank four tiles higher than `max_rise_tiles`
      resolves clean against an arc peaking at 2.75 rows. `docs/spec/game/runner.md` already
      *claims* interior rises stay within the profile; this makes the claim true. Add a frozen
      `PlacementProfile` beside `JumpProfile` carrying `apron_headroom`,
      `min_hazard_separation_columns`, `min_landing_clear_columns`, `min_hazard_clear_seconds` and
      `telegraph`, selected by a module constant `RUNNER_PLACEMENT_PROFILE = "reaction_fair_v1"`. Do
      NOT hang these on `JumpProfile`: that conflates traversal capability with placement
      discipline, forces every future jump name to re-declare the whole discipline, and is the half
      that will not transpose to a jumper. Do NOT persist a `placement_profile` field yet - a
      one-member vocabulary nobody can choose between is a constant; add the field in one bump the
      moment a second discipline exists. **Derive the spacing rather than asserting it**: a single
      jump spans 4.6 columns at base speed, so `min_hazard_separation_columns` is >= 6 with a
      reaction margin, not the 4 first proposed, and the clearance rule must be stated over hazard
      *sets* within one arc span rather than per hazard. **The apron alone closes only the
      cross-chunk case** - add `min_landing_clear_columns` measured forward from every pit's landing
      column and every interior rise's landing column, or the same counterexample survives verbatim
      one column inside a chunk boundary. Five refusal tests already exist in
      `tests/unit/orchestration/test_runner_member.py` (six tests total, not four - the
      hazard-over-pit refusal is already there and must not be re-added). Offline, zero provider
      operations, no authorization.

- [x] **Re-author the bellweather track: depth, width, jelly arcs, the ground line, and a real
      difficulty spread.** The design payload, and the answer to "how are obstacles placed". Every
      edit is inside today's contract bounds. Depth: `rows` 8 -> 11 and `walk_surface_row` 5 -> 8
      (the contract allows 6-32; at `tile_px` 64 against 720px, 11.25 rows are visible). Today's 5
      rows of air leave 2.6 above a 2.4-tall avatar, which makes the overhead half of the obstacle
      space un-prototypable later - free now, expensive to retrofit once the catalog grows. Width:
      12/12/16/16 -> 24-32 columns (`MAX_SEGMENT_COLUMNS` is already 64). A 12-column chunk is 2.0s
      at base speed, too short to hold a setup-then-payoff motif, and too short to afford the apron:
      at headroom 1.15 the apron is 5 columns at each end, which leaves a 12-column chunk two
      authorable columns and refuses `hay_run` at both ends. Widen first, then raise
      `apron_headroom` in the same commit. The trail: every pit and hazard gets a 5-9 token arc
      sampled from the real parabola - `jumpArcFor(2, 3)` peaks 2.75 rows over 4.6 columns - leaving
      the ground two columns *before* takeoff so the player is committed to the ascent when the
      hazard arrives, which is the takeoff cue expressed as geometry rather than a warning icon.
      `brook_gap`'s single token at (7,3) over a three-column pit becomes a seven-token arc. Safe
      stretches get the ground line: tokens one row above the surface, overlapping only while the
      feet sit within 0.8 rows, so a jump forfeits 0.646s of a 0.767s airtime - about 84% of a
      jump's worth of tokens. That is the crouch gate. The spread: author rank-1 chunks that teach
      one motif with a full trail and no death pressure and rank-5..8 chunks that interleave two,
      because the sliding band below is worthless over `{1,2,3,3}`. **Fold in the pickup chain
      multiplier**, which the first pass dropped without refusing it: `collectedThisFrame` is
      already published every frame (`web/lib/sideview-runner/obstacles.ts:84-112`) and `run.score`
      has a single writer, so a combo that breaks on a missed ground token is free - and it is the
      missing *instrument* for the crouch gate, because a flat 10-points-per-token score makes an
      84% forfeiture nearly invisible while a breaking multiplier makes it legible to the player and
      measurable by us. Fold in the per-event audio one-shots here too: short synthesised Web Audio
      cues on takeoff, hazard-cleared, land and collect, through the existing `ParallaxStageView` /
      `HudView` injection seams so the headless suites keep passing. That is BIT.TRIP's real trick -
      the cue is specific to *how* you avoided the obstacle - at zero provider cost. Zero image
      operations; the arcs reuse the generated `sunleaf_token`. Authored bytes change, so the next
      run re-bills exactly two structured operations, and **reaching this increment's own play-QA
      gate needs a credentialed live run** (`runner_executor.py:121-124` raises without both keys
      before any cache lookup) - it is cheap, but it is not offline.

- [x] **Chunk selection grammar: a sliding band, anti-repeat, and a forced rest cadence.** Ships
      *after* the re-authoring, for the reason in the preamble. Difficulty progression in the
      shipped game is over in twenty seconds: `difficultyCeiling = min(10, 1 + floor(distance/60))`
      reaches 3 at column 120, after which the pool is fully open and never changes again for the
      remaining 1800 columns of the speed ramp, a difficulty-1 flat chunk stays exactly as likely as
      the hardest one forever, the same `segment_id` can be drawn five times running, and there is
      no guaranteed breather after a crisis. Every reference generator surveyed has at least three
      of {weighting, anti-repeat, rest cadence, placement grammar, connector classes}; we have zero
      of five, and the seam rule makes the last two structurally unavailable, which makes the first
      three the whole budget. The fix is entirely consumer numbers inside the existing closed name
      `gentle_ramp_v1` - the other half of the experience_curve idiom. `RampProfile` gains
      `minCeilingLag` so the pool is a sliding band rather than a growing set; `selectChunkIndex`
      takes the previously drawn index and excludes it unless the pool would otherwise be empty;
      `streamAhead` forces a floor-difficulty chunk every K appends on one new `SegmentStream` field
      written only by `runner/segments`, which is already its sole writer. No new `GameSystem`, so
      no `reads`/`writes`/`after` moves and the `DOCUMENTED_ORDER` pin in
      `web/lib/sideview-runner/game.test.ts:18-41` does not move. Determinism survives -
      `streamAhead` already takes the rng off the single `world.run.rng` - but rng *consumption*
      changes, so any seed recorded before this lands reproduces a different track. Contract-free,
      zero provider operations.

- [x] **Complete the declared arithmetic: move the five arc constants into the SDK and publish
      them.** The precondition for the clearance proof and a latent defect on its own. Admission
      proves gaps and rises from two integers, but the arc the player actually flies is shaped by
      five numbers the SDK has never seen: `JUMP_PEAK_MARGIN_TILES` 0.75 and `AIRTIME_HEADROOM` 1.15
      (`web/lib/sideview-runner/avatar.ts:19,:22`), `BASE_SPEED_COLUMNS_PER_SECOND` 6
      (`difficulty.ts:40`), `AVATAR_HALF_WIDTH_COLUMNS` 0.3 and `HAZARD_COLUMN_INSET` 0.15
      (`obstacles.ts:32,:35`). The offline proof and the runtime arc agree only by convention:
      `avatar.test.ts:63-79` asserts `jumpArcFor(2,3)` against hard-coded literals, never against
      the manifest's published `max_clear_gap_columns`. Retune `AIRTIME_HEADROOM` to 1.0 for
      game-feel and every "provably clearable" claim in the repo becomes silently false with no gate
      catching it. Tolerable while admission compares integers; not tolerable once a refusal is
      *computed from* those numbers. The rule worth writing down, because it settles this for every
      genre that follows: **a number belongs in the SDK constant table iff a REFUSAL depends on it;
      it stays consumer-owned iff only the FEEL depends on it.** That correctly leaves the ramp
      numbers in `difficulty.ts` and moves the five above. Published values equal today's constants
      exactly, so the increment is observation-neutral by construction - a large diff with nil
      behaviour delta, which makes it trivially reviewable. **Two traps found in review.** The
      manifest bump `sideview-runner-runtime-v1 -> -v2` DOES move `topology_sha256`, because
      `src/gnode/graph.py:319-352` hashes each node's ports including `port.kind` - so
      `scripts/write_pipeline_graph_contract.py --write` and the embedded block in
      `docs/spec/game/runner.md` move in the same change or
      `tests/contract/test_generation_pipeline_docs.py` fails inside `scripts/check.py`. And the
      node cache key (`src/gnode/build.py:165-174`) does NOT include ports, so regenerating the
      dropped run is a cache hit that replays the old v1 manifest byte-identically and is still
      refused by the v2 parser: **the manifest NodeType's `contract_version` must be bumped too**,
      or purge that one cache entry. Zero image operations; the regeneration bills zero provider
      operations once the contract_version moves it off cache, or two structured if package bytes
      also change.

- [x] **Admission hardening II: prove hazards are jumpable, and make the telegraph a refusal.**
      Terrain is proved offline and props are not. `_validate_runner_member` never reads
      `height_units`, which `platformer_content/models.py` bounds only at 0.05..32.0, so a hazard's
      height has never been checked against the arc that must clear it. From the now-published
      arithmetic: `v0 = 14.348 rows/s`, `g = 37.426 rows/s^2`, a hazard box is `height_units x 2.40`
      rows, and the x-overlap between the 0.6-column avatar box and the 0.7-column hazard box spans
      1.3 columns, crossed in 0.2167s at base speed (base is the worst case - airtime is fixed by
      construction, so ramping only shortens the crossing). The results are stark. **`toppled_cart`
      at `height_units = 1.00` clears for 0.2736s against a 0.2167s crossing - a 3.4-frame press
      window at 60Hz, in the run that is playable right now.** `hay_bundle` at 0.75 gives 14.0
      frames and is comfortable. Anything above 1.146 exceeds the 2.75-row arc peak and is
      physically unjumpable, admitted silently. Add the proof against `min_hazard_clear_seconds =
      0.15` (9 frames) and recalibrate `toppled_cart` to 0.85, which yields 10.4 frames. Write the
      designer's rule into `docs/spec/game/runner.md` in the same change, because the first time a
      beautiful prop fails admission someone will quietly edit the threshold: **if the silhouette is
      wanted at full height, the correct fix is a taller jump profile, not a lowered threshold.**
      The recalibration is free on the art side - `height_units` is absent from the catalog image
      node's `input_digests` (`runner_graph.py:494-499`), so the generated cart PNG stays a cache
      hit and needs no new semantic review. Then harden the telegraph: when `telegraph ==
      "pickup_arc_v1"`, every chunk carrying a pit or interior rise must place at least three
      pickups on cells the declared arc passes through, using the same closed-form sampling the
      clearance proof uses - one piece of arithmetic serving both, which is the point. New refusals
      `segment_hazard_unclearable` and `segment_untelegraphed`. Deliberately one increment after the
      authoring: the authoring tells us what the predicate should be, and an unenforced authoring
      habit rots. The escape hatch is `telegraph = "none_v1"` on a different placement name, so a
      deliberately unsignposted chunk is a declared intent rather than a violation - CookieRun's own
      introduce-safely-then-weaponise discipline needs that door. Zero image operations; the
      `props.toml` edit re-bills the two structured judges, and its play-QA gate needs credentials
      like the re-authoring above.

- [x] **Double jump as `double_arc_v1`: a second name whose second hop is recovery, never reach.**
      The best ratio available. Our design condition is content the player cannot memorise, 1.67s of
      lookahead fully ramped, and one-hit death - precisely the condition where forgiveness beats
      precision. A mistimed first jump is currently terminal at the moment of takeoff; one air jump
      makes the same configurations recoverable, which is what lets a designer place tight patterns
      without being cruel. It also gives the trail a second altitude band for free: a high flat
      token line is uncollectable with a single hop, so the collectible teaches the input by being
      unreachable otherwise. The encoding is where the standing objections dissolve and is not
      optional: `double_arc_v1` declares `max_clear_gap_columns = 3` and `max_rise_tiles = 2`, the
      single-hop worst case unchanged. The second hop is pure forgiveness and never reach, so
      admission stays a one-dimensional existential over launch columns rather than a search over
      `(launch, air-jump)` sequences - the road to a reachability solver is the one property not for
      trade. No authored chunk ever demands both hops, so a player who spends the air jump early is
      never stranded, and soundness is preserved by construction because strictly more capability
      keeps every admitted chunk clearable. **The hop count does not go on `JumpProfile`**: by this
      plan's own rule a number belongs in the SDK table iff a refusal depends on it, and admission
      reads this one for nothing - the closed NAME is the entire contract surface and the count
      belongs in the runtime profile table beside `columnsPerCeilingStep`. Runtime: `AvatarState`
      gains `airJumpsUsed`, reset at the landing branch and in `resetRunnerWorld`; the gate at
      `avatar.ts:82` widens. `runner/avatar` is already the sole writer of `avatar` and already
      reads `intent`, so no declaration moves. **Fix the animation bug in the same change**:
      `game.ts:271` swaps texture and animation only when `state !== wornState` and
      `contract.ts:442-443` pins the jump strip to `once`, so a second hop inside the same `jump`
      state finds the atlas already finished and holding its last frame - the second jump would read
      as having no animation at all. Replay on the impulse, not the state change, and make the
      state-to-animation rule table-driven here since the slide wants the same eleven lines.
      **`avatar.test.ts:179-188` breaks and must be rewritten** - it does not model a held key (the
      latch would have consumed the edge) but re-applies one latched object across two steps, and
      under the widened gate step 2 relaunches to exactly `risingVy`, failing a strict
      `toBeGreaterThan`. Zero image operations if the second hop reuses the existing `jump` atlas,
      which it should - CookieRun's distinct spin for hop two is cosmetic.

- [x] **Crouch: the slide motion state, overhead hazards, and the proof that a ducked avatar fits.**
      The only paid increment, and the only one needing explicit authorization. **Yes on crouch**:
      with one verb there is exactly one question per obstacle ("when?"), one sentence in the
      collectible language, and two difficulty dials. No amount of admission hardening raises that
      ceiling. Slide is the only verb in the entire reference set that *punishes a jump* - a hanging
      obstacle is unreachable by any jump-family verb, which is what stops "be airborne as much as
      possible" from being dominant - and it is the first thing that makes hazard artwork
      load-bearing on the vertical axis, since today every hazard has one correct answer and the
      player never has to look at the sprite. **Three entry conditions:** the increments above
      shipped; the ground-token measurement taken; and the legibility question answered at zero cost
      by drawing an existing prop sprite at the overhead anchor in a scratch build - a 1.6-row band
      is ~102px at `tile_px` 64 with a ducked avatar at ~77px under a standing 154px, which is
      geometrically fine and might be visually mush. Do not spend an image operation to answer a
      layout question. **Buy the avatar state and the hazard vertical anchor as ONE change, never
      two**: `RunnerHazard` is `{prop_id, column}` and `validate_placements` actively refuses a
      hazard whose column is unsupported, so "a thing at head height with clearance beneath it" is
      literally unsayable, and an overhead prop with nothing to duck under is one image op of dead
      art. Three contracts move together with no aliases: `runner-track-v1 -> v2` (`RunnerHazard`
      gains a required `anchor: "surface" | "overhead"` with no default, plus `clearance_rows`),
      `runner-gameplay-v1 -> v2` (a closed `duck_profile = "slide_v1"` whose `DuckProfile` declares
      `ducked_height_fraction` and `min_overhead_clearance_rows` as SDK constants, so the overhead
      proof is increment 5's ground proof with the anchor flipped - which is exactly why that one
      had to come first), and `runner-avatar-v1 -> v2`. While bumping the avatar contract, **fix the
      shape rather than extending it**: make the required motion set a FUNCTION of what the track
      declares ("this track declares an overhead hazard, therefore the avatar must declare slide")
      rather than a universally required frozenset, or every future runner pays +1 image op forever
      including games with no overhead hazards, and the jumper inherits a set that is simply wrong
      for it. **The motion-state vocabulary is declared in three independent places with no test
      tying them** - `runner_content/models.py:39` (the frozenset that validates),
      `runner_graph.py:98` (the tuple that drives node fan-out and the rebase plate bands), and
      `web/lib/sideview-runner/contract.ts` (the runtime's own copy). Edit only the first and every
      `avatar.toml` is refused while no slide node is emitted; edit only the second and a strip is
      generated the contract will not admit. All three move in one commit, and a test tying them is
      worth adding while the reason is fresh. **Cost, corrected by rebuilding the graph rather than
      counting by hand: node census 25 -> 31** (one motion state and two overhead props each add a
      generate plus a validate node), `image_generation` 12 -> 15, `local` 11 -> 14,
      `structured_generation` stays 2 but both execute, and `topology_sha256` moves. Nominal
      $0.13-$0.76 at the binding table's declared rates; all-attempts-exhausted ceiling $4.56.
      Budget 4-6 image ops realistically - a crouch is exactly the pose that reads as a stumble or
      breaks the established proportion on first pass, and a semantic rejection is a regeneration,
      not a provider retry. `runner_prompts.py:89-106` falls through to a weak generic line for
      unlisted states, so **a dedicated slide direction sentence must be written before any spend**
      or we pay for a generic crouch. Semantic review of the slide strip and both props by someone
      other than their producer.

- [x] **Rhythm is refused, and the refusal belongs in `docs/spec/game/runner.md` so it is not
      re-litigated.** Not on cost - it would still be no with unlimited budget. The seam rule and
      beat sync are mutually exclusive: both references that actually sync map a *through-composed*
      song onto a *fixed* level, and our defining property is that any chunk may follow any chunk,
      drawn uniformly at runtime. You cannot through-compose against a random permutation. **The
      exact property that makes the runner infinite is the property that forbids the rhythm model.**
      It is independently disqualified by the ramp: `speedMultiplier` is continuous in distance, so
      the column-crossing period slides from 167ms to 111ms across one run and a column has no fixed
      beat phase at any point; the only compatible model is a loop grid with constant tempo and
      integer columns-per-bar, which forfeits the difficulty ramp entirely - a different genre, not
      a feature. The producer does not exist either: `MusicGenerationRequest` has no tempo in or
      out, `AudioProbe` returns only duration/format/bit-rate, and the dependency set has no onset
      or tempo-estimation stack, so a beat grid needs a new artifact kind, a new node type with a
      retry owner, and a new analysis dependency before one unit of design value lands - against a
      provider whose BPM adherence nothing here tests, where a missed tempo is a *semantic
      regeneration* rather than a retry. That is the worst risk profile in the whole survey:
      unbounded cost against unmeasured capability. **Do not let a tempo field into
      `game-soundtrack-v1`** - it is the one member already shared across genres, and neither a
      jumper nor a cinematic platformer has a tempo. If "feels musical" is the real want, the
      per-event audio one-shots folded into the re-authoring above are the cheap 80%: that is
      BIT.TRIP's actual trick, at zero provider cost.

- [x] **Take the rebase judges off the whole-package digest.** `avatar-rebase-judge` and
      `avatar-rebase-verify` declare `input_digests=(package.closure_sha256,)`
      (`runner_graph.py:446,:459`), so **any** authored edit anywhere in the package re-bills two
      structured operations - editing a track chunk, moving a pickup, or bumping a prop's
      `height_units` all re-run a judge that never looks at the track. Several increments above are
      pure authoring and each pays this toll. The rebase pass reads the motion atlases and nothing
      else, so its identity should be the motion-validate lineage it already depends on, not the
      closure. This is the same over-broad-digest defect as the open
      `PLACEMENT_ONLY_CLIMBABLE_FIELDS` item under platformer map design, one recipe further along,
      and it must move the graph contract and its cache-identity assertions in the same change.
      Related and worth noting while here: only 7 of the 12 image nodes are barrier-cut with
      `cache_depends_on=()`; the three `avatar-{state}-generate` and two layer loop-paint nodes
      carry lineage from their parents, so a change to the avatar concept prompt re-bills four image
      operations, not one.

- [x] **Move runner audio authorship into the package and add BGM.** The seven semantic runtime
      events remain the stable trigger vocabulary, but `runner/audio.toml` now binds each event to
      a named effect and owns every `oscillator_sweep_v1` parameter the web consumer previously
      hard-coded. The realization boundary is explicit so generated-file SFX can extend it later
      without remapping gameplay events. Bellweather also declares two original loop-ready tracks
      in `runner/soundtrack.toml`; this activates the existing runner music graph and adds two music
      operations. The exact-current cutover is `game-contract-v9` and
      `sideview-runner-runtime-v3`, with the manifest assembly cache re-keyed at v3. No provider
      operation is part of this authored/implementation change; producing and listening-reviewing
      the two BGM files is a separate live gate.

- [ ] **The adoption's open tail: the user's eyes and one measurement.** Everything above landed
      2026-09-01 in one working-tree change (contracts at runner v2/root v9, admission live, track
      re-authored, grammar/combo/authored-audio/double-jump/slide in the runtime, graph at 35 nodes).
      Still open, and not
      mine to close: semantic review of the three newly generated visuals (the slide strip and the
      `festival_garland` / `orchard_bough` overhead props) by someone other than their producer;
      the ground-token measurement (does an ~84%-of-a-jump chain forfeiture visibly change how
      often a good player is airborne?), which decides whether overhead hazards get authored
      generously or adversarially in the next track pass; and the known `hedgerow_band` backdrop
      defect from the first run, unchanged by this pass.

## Runner: the next pass

Assessed against the played `iron-petal-unit-live-20260902-v9` run. Grouped by what each item
actually costs, because three of these share one regeneration and one of them changes what "fair"
means.

### Ground: the pipeline validates coverage and geometry, never projection

- [ ] **Adopt a declared ground projection.** A side-scroller's ground must be drawn in **oblique
      projection** - a parallel projection whose receding edges never converge and which therefore
      has no vanishing point. This is a correctness rule, not taste: parallel projection is the only
      projection invariant under horizontal translation, and `auto_run_x_v1` scrolls the ground past
      a fixed camera while chunks repeat in arbitrary order. A vanishing point encodes a camera
      position, so a converging tile swims as it scrolls and has no repeat unit at all. Jetpack
      Joyride is the reference: every receding edge leans the same way at the same angle
      (`\\\\`), never splaying (`\|/`). The two numbers a spec needs are the **receding angle**
      and the **depth ratio** (cabinet oblique = 0.5, cavalier = 1.0); both are refusal-bearing once
      a gate reads them, so they belong in the SDK constant table under a closed projection name.
      Avoid "isometric"/"axonometric"/"planometric" - those rotate all three axes; oblique is the
      family that keeps the front face square-on, which is what a side view means.
- [ ] **Gate it.** Measured on `world/ground/rescue_calibration.png`, dominant non-horizontal edge
      lean by horizontal third: left `-36.8` deg, middle `+30.8` deg, right `+40.2` deg. The sign
      flips and the magnitude drifts ~9 deg across the rest - one tile carrying at least two
      projection systems. A gate that refuses a sign flip, or a spread past a tolerance, is provable
      offline before spend and is the missing third check beside coverage and occupancy.
- [ ] **Guide paint is shipping as ground art.** In the same raster, the walk-surface row (row 8,
      y 512-576) reads: y 512-522 lilac `(163,181,199)` - the guide's surface marker; y 524-534
      brown `(85,60,34)` - the guide's raw occupancy fill; painted deck only from y~536. So the top
      ~23px of a 64px cell is unpainted guide, on the row the avatar stands on. Root cause is a
      blind spot rather than bad luck: source admission counts painted coverage at alpha >= 128, and
      guide pixels are opaque, so an alpha test cannot distinguish paint-by-model from
      guide-showing-through. **The gate measures alpha, not authorship.** It needs a guide-palette
      residue check, and the prompt needs to demand the guide be painted over rather than around.
- [ ] **The seam bridge fixes the join and breaks its own borders.** Every chunk ends with shared
      bridge column 0 and starts with bridge column 1, so an A-to-B join is continuous by
      construction - but the bridge is the same two columns everywhere, lifted from the first
      segment's apron, so it lands as a foreign panel: two hard vertical edges 128px apart at every
      join, where each chunk's own art meets the insert. Direction is edge *conditioning* - each
      chunk paints toward a shared edge profile - rather than a foreign insert.

### Content fidelity

- [ ] **Background layers float.** `botanical_terraces` is disconnected pipe runs hanging in void:
      horizontal runs terminating mid-air on open cut faces, no vertical support, large dead
      regions. Nothing in the layer contract requires an object to be supported, attached, or
      terminated, so this is an authoring and prompt gap first; whether any part of it is gateable
      is the open question.
- [ ] **The coin needs a drawn spin, and the right projection.** Two separate defects.
      `lumen_seed.png` is rendered in 3/4 perspective while the game is strict side view. And
      `collectiblePresentation` fakes rotation by squashing `scaleX` on a cosine, which on a
      perspective disc reads as a wobble rather than a spin. Rotation should be sprite-based (a face
      -> narrowing -> edge-on -> widening strip); the bob stays code motion. Note the cost is low:
      items carry no motion support at all today - only the avatar has `motions` - but a four-frame
      strip is still one image node, so this is a content-contract addition, not new provider spend.
- [x] **The run should scroll faster.** `swift_runner_v1` (9 columns per second, same 1.5x cap),
      a union widening with no schema bump. The caveat bit exactly as predicted: every press window
      scales as 1/base, and Iron Petal's `filter_stack` (0.68 player-heights) capped the track at
      8.3 columns per second, so it was re-authored to 0.60 - a shorter silhouette, not a lowered
      threshold. Zero provider re-keys.

### The gauge's other half

- [ ] **Nothing heals.** `restore()` exists on the shared gauge, fully tested, and is called by
      nothing outside its own tests. Two authored sources are wanted: a combo/chain threshold that
      restores a point, and a heal item. Both fit the existing primitive; what is missing is the
      authored vocabulary saying when a package grants them, mirroring `[run.consequences]`.

### Locomotion: the one that needs new admission arithmetic

- [ ] **Make the genre agnostic over its mechanism - run versus fly.** Jetpack Joyride and Geometry
      Dash both carry two. This is not a mode flag but a **locomotion profile**: the map from intent
      to vertical motion *plus its own admission arithmetic*. Today `jump_profile` is that,
      implicitly, for running only - admission proves gap spans and jump arcs. A thrust track has no
      gaps to clear; it has corridors to fit through, so it needs a different proof rather than a
      relaxed one. The hard constraint: whatever locomotion a package declares, admission must still
      prove that locomotion's fairness offline before spend, or this becomes the first
      unfair-by-construction genre in the repo.
- [ ] **Fever time falls out of locomotion once it exists.** Model it as a **timed locomotion
      override** - switch locomotion, optionally suspend consequences, for a bounded window - so
      "fever is flying" is a parameter the input author chooses rather than a special case in the
      runtime.

### Still owed on the played run

- [ ] Semantic visual review of `iron-petal-unit-live-20260902-v9` by someone other than its
      producer, and a separately recorded listening verdict on its two regenerated tracks. Every
      item above that regenerates art inherits this obligation.

## Future genres

Two families worth reserving now so they cannot drift, and one of them needs a name badly enough
that naming it is the deliverable.

- [ ] **`2d/sideview/jumper` - the vertical endless jumper (Doodle Jump). Its own genre member
      family, not a camera mode inside the runner.** The temptation is to add a `ratchet_y_v1` name
      to `RunnerCamera` and call it done. Three of `runner-track-v1`'s load-bearing invariants are
      horizontal by construction rather than by parameter, and the mode flag makes each
      conditionally meaningless: `walk_surface_row` is the seam datum the whole validator is built
      around and a jumper has no continuous contact surface at all; `bottom_contiguous_surface_row`
      is a bottom-up column scan every hazard, pickup and pit-run check calls; and
      `max_clear_gap_columns` measures a quantity a bounce does not have. One contract with two
      mutually exclusive readings selected by a mode flag is exactly the compat-reader shape this
      repo forbids. The verb set inverts too - the runner's one verb is an edge-triggered jump, the
      jumper's is a held continuous steering axis with no jump at all, which the `RunnerIntent`
      latch's consume-on-sample semantics actively corrupts. The precedent is the runner itself,
      which reused the shared `2d/sideview/*` modules rather than extending the platformer. Build
      the Doodle Jump variant, not Icy Tower: auto-bounce plus screen wrap collapses reachability to
      a single one-dimensional condition on delta-y - screen wrap means no horizontal distance is
      ever unreachable - which is the cleanest offline proof in the repo, whereas Icy Tower's
      landing-momentum jump height makes reachability a function of prior traversal and is not
      provable ahead of time. The seam rule's replacement is a **landing band**: each band declares
      an entry and an exit datum row, its lowest platform sits within `max_rise_rows` of the entry
      datum, and its topmost platform *is* the exit datum - restoring exactly the property the
      runner bought. What transfers free is substantial: the authored rectangular occupancy reads
      the same rotated 90 degrees, `difficulty` ranks and ceiling selection transpose verbatim,
      `terrain-atlas-3x3-minimal-v1` is a general autotile so an isolated one-row ledge is already
      an expressible mask, the prop and item contracts come over unchanged, and
      `PreparedMapCamera.follow_axes` already admits `["y"]` with a docstring naming a climbing
      tower. What does not: `PreparedMapContinuity.seamless_axis` is `Literal["x"]` and
      `src/stage_gen/media/loop_construction.py` is column-native end to end, so the reflection tier
      transposes for free while the interior and anchored tiers need their conditioning masks
      re-derived on rows. **`2d/sideview/loop_y` is the one genuine asset-side blocker, and
      `docs/spec/asset-taxonomy.md:130-135` already reserved it and already says an infinite-jumper
      demo is impossible until it has a caller.** The avatar art does not transfer - `run` is wrong
      for a game whose avatar never runs, and one `jump` strip cannot serve both halves of a bounce
      since an arc read left-to-right reads as a stall at apex; the closed set is `{rise, fall,
      death}`. A first jumper run mirrors the runner's census almost exactly: 12 image operations
      plus the 2 structured rebase, with +3 if the avatar needs two-way authored rather than
      mirrored coverage. Layer paintings must be regenerated even to get the same picture, because a
      y-loop repeat unit is a different artifact than an x-loop one.

- [ ] **The Limbo / Badland / Ori family: these are three genres, not one, and the first thing to
      refuse is the premise that they share a name.** "Atmospheric side-view adventure" names the
      art direction, not the gameplay composition, and our taxonomy defines the `genre` slot as the
      gameplay composition profile the module assumes, so mood-words are structurally disqualified
      as segments. The decomposition: **Limbo / Inside -> cinematic platformer**, subtype
      puzzle-platformer, with Playdead's own term "trial and death" for the failure mode - realistic
      proportions, momentum-carrying movement that takes time to reach speed and time to stop, a
      vulnerable ordinary protagonist, environmental puzzles, no HUD, no score, no combat. **Badland
      -> `2d/sideview/one_touch_flier`**, a one-touch physics side-scroller whose avatar is a rigid
      body never grounded by design, where standing on terrain is a failure state rather than the
      base case; it is closer to our runner than to Limbo and is not a platformer at all. It
      *consumes* `2d/sideview/painted_terrain` rather than being homed there - conflating a genre
      with a module it uses is the exact confusion the taxonomy exists to prevent. **Ori ->
      metroidvania / action-platformer**: ability-gated connected world, combat, HP, player-placed
      saves, backtracking. **Build Limbo/Inside first and name it
      `2d/sideview/cinematic_platformer`**, bound to the same `lateral_orthographic_side_plane_v1`
      profile as `platformer` and `runner`, with members under a matching `cinematic_platformer/`
      package prefix so the segment and the prefix are identical and the name is greppable once.
      Ruling out the alternatives, since specificity means ruling things out: `adventure` names
      nothing checkable and is precisely the label worth rejecting; `puzzle_platformer` over-claims,
      because the word promises a solvability proof and Limbo's puzzles are physics contraptions
      whose solvability is not decidable offline - putting a claim in the contract name that no
      validator can honour is the opposite of what `single_arc_v1` does; `metroidvania` is a
      different game; `atmospheric` and any mood word are style facets the visual taxonomy already
      owns, and a genre segment must not duplicate a style facet; bare `cinematic` collides with
      `game_cutscene_*`, which the namespace table already assigns to shots and blocking. The
      compound disambiguates, is the established term in the literature anyway, and two-word
      segments are already precedented. The word `cinematic` does **not** commit us to a rotoscoped
      animation budget - the taxonomy separates genre from the `motion_treatment` style facet, so
      the animation claim lives there and stays honest. Why this one first, decisively: it is the
      only one of the three whose new requirement is **authoring vocabulary** rather than a new
      simulation substrate. It needs a finite non-looping level with an authored end - a gap
      `docs/spec/asset-taxonomy.md` validation case 3 already reserved.

## Git reconciliation

- [ ] Reconcile origin commits `98e0214` and `00f90d1` only after the worktree is clean. Compare
      them with the local theme/compiler equivalents, retain each change once, and run the full
      offline gates; do not pull or merge them blindly over local work.
