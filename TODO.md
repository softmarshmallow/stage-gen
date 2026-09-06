# TODO

Only unresolved current-tree work belongs here, one line per open item, each linking to the document that holds its context. Provider runs, generated-media promotion, and publication still require explicit authorization even when their implementation gates are ready.

Rulings live in [decisions](docs/decisions/README.md) — one record per ruling, each carrying the observation that would overturn it. Paths that die when they are walked live in [plans](docs/plans/). Contracts live in [spec](docs/spec/). This file is none of those: it is the list of what is not done.

## Exact current contracts

- [ ] Remove the remaining alternate public shapes rather than maintaining readers for them — camelCase artifact/capability and doctor output, the scrolling manifest, `legacyDialogueBeats`, tracked historical JSON under docs/media, and docs/generated-media-inventory.json — replacing or retiring each atomically with its consumers, digest bindings and rejection tests, and adding no aliases ([0005](docs/decisions/0005-one-narrative-contract-deleted-not-aliased.md)).

## Game UI

The contract is [authored game UI](docs/spec/game/ui.md); the taxonomy is [ui-atlas](docs/spec/game/ui-atlas.md).

- [ ] Replace the drawn `inventory_panel` with a composition: retire the fixed `inventory_grid_4x2_v1` role (one picture of eight slots that no game outside the platformer's pack shape can use) and promote `slot_cell` from the taxonomy as a generated role beside `panel_frame`, so a pack of any slot count is the panel frame stretched around a grid of slot cells. Drop the role and its nodes, gate, evidence and review with the two Bellweather documents that declare it, re-pin the platformer's UI group and the web `InventoryHud`, and switch the survival host's code-drawn slot wells to the new cell — one contract bump, no alias. Until then the survival host draws its slots as plain dark wells inside the generated frame, on purpose.
- [ ] Re-brief Ember Hollow's `preview_icons` to the two flat tones its style plate has, or take the one-tone clause out of the role's prompt: the run `out/ember-hollow-v8` review rejected the set for the lit-and-shadow facets the package's `[style]` asks of every shape, while every glyph registered and the set reads as one hand. One image operation, and nothing reads the sheet yet — the host's glyphs are the pack's own icon sheet ([ui.toml](library/games/ember-hollow/ui.toml)).

## Scenario

The contract is [scenario](docs/spec/game/scenario.md); the component ruling is [0001](docs/decisions/0001-scenario-is-a-component.md).

- [ ] Split Larkfield's style plate from Nao's identity plate — authoring in one package, and it re-bills all fifteen images, so batch it with the next run that regenerates ([0056](docs/decisions/0056-the-style-plate-is-split-not-swapped.md)).
- [ ] M2, the player shell: persistence, save slots, backlog, skip-already-read, auto-advance, preferences. Cross-genre, and the same missing substrate the champion roster is blocked on — build it once for both.

## Runtime acceptance

- [ ] Add the producer-owned `character-hurt` four-frame strip and its optional runtime-manifest entry: the web runtime and the synthetic fixture already accept the role, the Python recipe still produces only `character-attack`, and generation, raster/alpha/scale validation, provenance and producer-to-consumer tests bind before any artwork is promoted.
- [ ] Draw the runner's `hurt` motion and switch both runner packages to `hurt_representation = "drawn_v1"` — a one-word authored change plus regeneration, a hurt direction beside the death one in `src/stage_gen/recipes/sideview_runner/runner_prompts.py`, and a non-producer semantic review. One art pass with the strip above, two genres.
- [ ] Consider binding a `hurt` audio cue, deliberately not taken with the vitals pass: it bumps the audio contract for feedback the platformer does not have either, and the blink plus the bar's dim already say a blow connected.
- [ ] Add one village gameplay-harness scenario booting the authored social-hub map, proving the flat stage, resident loading and scale, dialogue gating and portal transition together — it must use reviewed art before it counts as visual acceptance evidence.

## Sprite anchoring

- [ ] Give every motion frame a real anchor point, replacing the alpha-bounding-box edge rule and the two-word `anchor` stopgap; scope the acquisition method before building anything ([0047](docs/decisions/0047-a-bbox-edge-is-not-an-anchor.md)).

## Player identity reference

- [ ] Give the prepared concept sheet a rear view, or stop declaring states rear-facing — it re-digests the concept node and invalidates the whole player fan-out, so sequence it before any other player regeneration ([0048](docs/decisions/0048-the-concept-sheet-has-no-rear-view.md)).
- [ ] Pick one canonical name for the multi-view character sheet and make it a first-class input or a first-class node: it is called at least seven things across the tree and the file has two names. Rename the stage, the artifact, the prompt wording and the docs together, then decide whether the authored package supplies a reviewed sheet or the graph generates one — do it with the rear-view gap above so the fan-out is not re-run twice.

## Media and publication

- [ ] Resolve the 12 stale lineage bindings across the four published gameplay/dialogue captures: recapture and independently review current bytes, or retire the publication; never rewrite hashes to bless stale media ([VERIFICATION.md](VERIFICATION.md)).
- [ ] Keep `concept-studio/gallery/the-sky-remembers/` and its inventory entry uncommitted until the authenticated task owner authorizes publication of the exact reviewed WebP, then move the repository media-count test and run the publication, storage and documentation gates as one atomic change ([0004](docs/decisions/0004-acceptance-of-a-run-is-not-publication.md)).

## Climbable band atlas

- [ ] Close the middle-band rung phase before the tiled climbable contract admits generated bands; the deterministic cut lands with the world-unit mapping, not as a patch ([0050](docs/decisions/0050-rung-phase-is-cut-not-prompted.md)).
- [ ] Measure strand-type climbables or refuse them at admission: the rung rhythm metric keys on crosswise structure a rope or vine does not have, so every strand column reports unmeasurable and nothing quantitative supports the ropes that look correct.
- [ ] Replace the operator-supplied band-structure reference and regenerate every accepted band before promoting any climbable artwork ([0049](docs/decisions/0049-spike-licensed-reference-artwork-is-not-promotable.md)).

## Platformer map design

The contract is [platformer map design](docs/spec/game/platformer-map-design.md).

- [ ] Add the `canopy` word to the chunk vocabulary and measure the resulting mean platform width against the recorded row-painting figure — composition sugar over primitives the contract already carries, and adding the word without re-measuring leaves the density claim as unproven as it is now.
- [ ] Split `PLACEMENT_ONLY_CLIMBABLE_FIELDS` out of the climbable atlas cache identity, mirroring the ground node, moving the graph contract and its cache-identity assertions in the same change ([0034](docs/decisions/0034-a-judges-identity-is-its-lineage-not-the-closure.md)).
- [ ] Do not let any profile declare `biomes` until a ground mode can consume them ([0051](docs/decisions/0051-no-profile-declares-biomes-until-a-ground-mode-can-consume-them.md)).
- [ ] Apply a design to a shipped map only as its own authorized operation, sequencing the cache split above first if a run intends to move placements ([0052](docs/decisions/0052-applying-a-design-to-a-shipped-map-is-its-own-operation.md)).

## Camera

- [ ] Take `map_direction` out of the terrain node's identity: terrain is geometry, visual direction and continuity are art direction, and neither shapes a chunk sentence — the split the ground and climbable nodes already have, one node further along ([0034](docs/decisions/0034-a-judges-identity-is-its-lineage-not-the-closure.md)).
- [ ] Decide whether partial vertical parallax is wanted before any layer needs it ([0054](docs/decisions/0054-a-layer-resolves-in-two-spaces-not-on-a-coefficient.md)).

## Rendering

- [ ] Sprites are minified without mipmaps; no action until jagged sprites return, and the fix then is a filtered pre-shrink at load time or power-of-two padding with an explicit mipmap filter ([0053](docs/decisions/0053-sprites-are-minified-without-mipmaps.md)).

## Platformer hunting ground

The reference and its six measured axes are [0007](docs/decisions/0007-the-hunting-reference-is-adopted-for-feel.md).

- [ ] Promote `placement` to the Python `SpawnZone` model as a defaulted field, once the clustered policy has proven itself in play ([0009](docs/decisions/0009-a-consumer-policy-proves-itself-before-it-is-authored.md)).
- [ ] Play Crowncrag Road on the shipped run and record a short capture of the impact feedback for a non-producer review.
- [ ] Keep an attacking archetype on the common mob the automation encounter fixture uses, or make the fixture pick another rank: it expects a mob to engage within its focus window ([0015](docs/decisions/0015-aggression-is-derived-from-rank.md)).
- [ ] Add platform-footed climbables (`bottom_surface` on the placement plus runtime support) so a rope can join two storeys — today a ladder can only foot on terrain, so every ladder-fed deck sits one height above the floor and the lowest storey reads as low ([0012](docs/decisions/0012-a-shelves-tier-is-a-lane-not-a-stack.md)).
- [ ] Decide whether the hunting map buys more world in view: widening the design viewport is free at the cost of re-pinning automation captures, and a camera zoom below 1 is not ([0054](docs/decisions/0054-a-layer-resolves-in-two-spaces-not-on-a-coefficient.md)).
- [ ] Settle the road's standing map-review `reject` — mirror-repeat loop joins, reference fidelity, portal and climbable atlas presentation — by satisfying it or by saying in the contract that the review is advisory, which is how the checkpoint already treats it.
- [ ] Break the tile-grid read with edge props: large non-colliding rock and root props snapped to deck edges, at zero contract cost. Authoring plus art, no code beyond what the village already uses.
- [ ] Decide whether Bellweather itself adopts painted terrain — an authoring flip of four lines and a re-pin, a taste call rather than a technical one, and the in-scene comparison is on file ([0019](docs/decisions/0019-painted-ground-is-opt-in-and-collision-stays-authored.md)).
- [ ] Generated VFX sprites, deferred: a slash/spark/burst family is a new taxonomy entry with its own contract, review and cache identity, and has no caller until the procedural feedback has shown which shapes are worth drawing ([0014](docs/decisions/0014-every-presentation-effect-is-a-pure-sampler.md)).
- [ ] Painted structures, deferred; open before it starts is whether the standable lines are hand-authored beside the prompt or designed by a structured node, and whether a structure may carry solid regions rather than only floors ([0021](docs/decisions/0021-painted-structures-are-a-separate-family.md)).

## Runner

The adoption and what it refuses are [0025](docs/decisions/0025-cookierun-is-adopted-for-its-level-language.md); the contract is [runner](docs/spec/game/runner.md).

- [ ] Semantic review of the slide strip and the two overhead props by someone other than their producer, and the ground-token measurement — does an ~84%-of-a-jump chain forfeiture visibly change how often a good player is airborne? It decides whether overhead hazards are authored generously or adversarially ([0029](docs/decisions/0029-the-trail-is-routing-and-the-combo-makes-it-legible.md)).
- [ ] Fix the known `hedgerow_band` backdrop defect from the first run, unchanged by the adoption pass.
- [ ] Build an instrument local to the surface run, rather than a statistic over the tile, if one receding top face ever has to be refused — worth it only when a package is drawn badly enough to want it ([0037](docs/decisions/0037-the-projection-gate-refuses-two-projections-in-one-tile.md)).
- [ ] Decide whether a floating layer object is gateable, when a second package needs it ([0041](docs/decisions/0041-a-floating-layer-object-is-fixed-in-the-brief.md)).
- [ ] Draw the coin a spin and the right projection: it is rendered in 3/4 perspective against a strict side view, and the runtime fakes rotation by squashing a perspective disc. Items carry no motion support today, so a four-frame strip is a content-contract addition rather than new provider spend ([asset unit](docs/spec/asset-unit.md)).
- [ ] Nothing heals: the shared gauge's `restore()` is tested and called by nothing outside its own tests. Two authored sources are wanted, a chain threshold and a heal item, and what is missing is the vocabulary saying when a package grants them.
- [ ] Declare thrust for a whole track, not only as an encounter override — it needs a corridor-fit proof over authored terrain, a different proof from the lane pigeonhole a flat empty arena gets for free ([0043](docs/decisions/0043-locomotion-is-a-profile-with-its-own-arithmetic.md)).
- [ ] Fever time is one field away: the override machinery is built and played and `fever_start` is already reserved in the moment table, so what is missing is the vocabulary saying when a package grants it.
- [ ] Bind audio to the encounter: none of the four fight events the director already emits has one ([0035](docs/decisions/0035-runner-audio-authorship-moves-into-the-package.md)).
- [ ] A boss takes a hit without showing it — the runtime flashes the sprite for 64ms and nothing contracts that, so either name it in the contract or draw a `hurt` strip and pay for it.
- [ ] Pay a defeated boss something besides score, once the healing vocabulary above exists: it is the obvious first authored source of a restored point.
- [ ] A calibrated actor is measured by its alpha, not by its body; deferred until a second actor carries a tail ([0055](docs/decisions/0055-a-calibrated-actor-is-measured-by-its-alpha.md)).
- [ ] Semantic visual review of `iron-petal-unit-live-20260902-v9` by someone other than its producer, and a separately recorded listening verdict on its two regenerated tracks. Every item above that regenerates art inherits this obligation.
- [ ] Semantic visual review of the encounter art in `iron-petal-unit-live-20260903-boss-big`: the boss's three strips at 2.6 player heights, the two projectiles, the avatar's `fly` strip, and the `encounter_start` portrait.
- [ ] Semantic visual review of the ground and the middle-distance layer in `iron-petal-unit-live-20260903-ground-5`: does a chunk join read as a joint rather than as inserted scenery, does every slab's top edge read as the material's own, and is every branch of the layer carried and terminated? The producer measured all three and looked at all three; none of that is the verdict.

## Survival

The contract is [oblique-survival](docs/spec/survival/generation-v1.md); the host ruling is [0057](docs/decisions/0057-the-survival-game-runs-on-godot.md). The game has no browser surface; its runs are legible at `/runs` through the registered `oblique-survival-execution-view-v1` kind, which is the only place `web/` names the recipe.

- [ ] Act on the seasons review's advisory that the standing-plant sheet's thin outlines and brighter palette sit a step outside the set's muted ink: it is a re-brief of the sheet's style emphasis and one image operation, and the user's verdict comes first ([survival ground](docs/spec/survival/ground.md)).
- [ ] Remove the snow mound the winter look clause invites under a tuft's base — the ground has its own snow, so a look must not paint it twice; one clause edit plus per-state overrides for the three pairs whose winter twin re-branches rather than caps ([survival seasons](docs/spec/survival/seasons.md)).
- [ ] Re-brief the road plate the way the two field plates were re-briefed, or give it a torn edge: the dirt track's stub now reads as a soft pale band against the darker turf ([survival ground](docs/spec/survival/ground.md)).
- [ ] Semantic review of an oblique-survival run's ground, props and actors by someone other than their producer, and a separately recorded listening verdict on its music and sound takes ([VERIFICATION.md](VERIFICATION.md)).
- [ ] Draw a mob a `back` facing, or keep `single_mirrored` as the admitted coverage for a mob and stop treating it as a gap ([oblique-survival](docs/spec/survival/generation-v1.md)).
- [ ] Alpha-test the pointer pick: a click in the empty corner of a card's rectangle still picks that card; reading the hit texel needs the card images kept CPU-side or a per-template mask ([host README](godot/oblique_survival/README.md), "Playing it").

## Future genres

- [ ] `2d/sideview/jumper`, the vertical endless jumper and its own genre member family, blocked asset-side on a y-loop module ([0045](docs/decisions/0045-the-vertical-jumper-is-its-own-genre-family.md)).
- [ ] `2d/sideview/cinematic_platformer`, the first of the three genres the "atmospheric side-view adventure" premise was hiding; its new requirement is authoring vocabulary — a finite non-looping level with an authored end ([0046](docs/decisions/0046-limbo-badland-and-ori-are-three-genres.md)).

## Survival world

The contract is [world](docs/spec/survival/world.md); the ruling is [0059](docs/decisions/0059-the-world-is-a-point-process-and-the-object-owns-its-habitat.md).

- [ ] Chunked visibility on the Godot host, so a 1 km world (the generator already lays one) does not submit every card every frame; the sim's flat entity walks are the second cost.
- [ ] Biome adjacency rules (which biome may touch which): a climate-parameter solver, not the threshold fields; the object-owned habitat is unaffected.
- [ ] Rendered relief from the rules-only height field, and puddles solved into its hollows rather than scattered.
- [ ] A road between set pieces: the one track still leaves the spawn and ends where the land does.
