# The Grain: dialogue-scene asset format

Current ownership: this is The Grain's asset-preparation contract over its
supported v2 input. Game metadata and generation briefs remain in its reader
and shared game adapter. [Scenario](../../../packages/scenario_runtime/README.md)
owns narrative compilation/execution under Godot; this document does not define
new v3 staging, presentation capabilities or the asset product's input schema.

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`, `tests/unit/games/dialogue_scene/test_workflow.py`.

> **Scope: The Grain preparation.** The gnode build `pipeline/workflow.py:scene`
> generates a portable, provider-neutral bundle. The Godot host plays it and never
> generates assets.

One scene packages a cast of adult character identities, one backdrop per
declared stage, a static sprite for each face a drawable actor's own profile
declares, one music track per declared track, and presentation data, around the
authored `scenario` members that own the narrative. It does not own story generation, relationship
state, animation, rigging, lip sync, or a game runtime.

A scene binds **several** scenarios and generates the **union** of their art
exactly once. An episode is split into scenarios so that each one's admission
proof stays under its state ceiling — but six beats of one episode are still one
cast, one look and one set of rooms, and drawing them once is most of the art
budget. The alternative, one scene package per scenario, would also put the
scenario and script files in the tree once per beat, which is a second source of
truth for the words.

The builder reads no fixed count anywhere: the bound scenarios declare the cast,
the stages and the tracks between them, and the fan-out follows the union.

## Ownership and boundary

| Location                                | Responsibility                                                                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `godot/games/the_grain/pipeline/workflow.py` (`scene`) and `pipeline/nodes/scene.py` | The build: one step per plan, image, track and interface sheet, the judges that hold each one, and the package step that writes the bundle. |
| `godot/games/the_grain/pipeline/src/the_grain_pipeline/dialogue_scene/` | Adult/non-explicit policy, the package reader, prompts, strict models, the briefs and gates the build calls, and bundle assembly. |
| `src/gnode/`                            | The engine: provider-neutral structured, image and music steps with one six-attempt retry owner, judged redraws, the cache and the run's records. |
| `src/stage_gen/media/`                  | Shared deterministic image inspection and transforms. |
| Scenario and soundtrack owners          | The independent Godot `scenario_authoring` distribution owns narrative compilation and admission, `demo_game_tools.scenario` the production envelope, and the game-owned soundtrack binding authored track intent and the music prompt compiler. |
| `gameplay/dialogue_scene/` (Godot)      | Strict bundle validation and play. It never imports Python build internals or calls providers. |

The scene build is a sibling of the room build and of Bellweather's, not a mode
within either. Its vocabulary and visual assumptions do not enter generic
components; host camera, UI, and gameplay assumptions do not enter the bundle.

## Authored package: `dialogue-scene-v5`

The Grain owns its scene under `godot/games/the_grain/inputs/`, holding `scene.toml` beside
the members it names by exact relative path: the scenarios it plays, the
character profiles it binds, and the `references/` its art is drawn against. The
document is strict TOML: every key is lower_snake_case; camelCase, unknown keys,
and implicit aliases are rejected. This format belongs to the demo builders that
read it. It is not a required input format for other games or asset pipelines.

The following excerpt shows one scenario binding and one profile from
[The Grain](../inputs/scene.toml). The complete file owns
the remaining scenarios and cast; this excerpt is not an independently runnable
package. The style reference supplies the look, not an actor identity.

```json
{
  "schema_version": 5,
  "kind": "dialogue-scene-v5",
  "game_id": "the_grain",
  "display_name": "The Grain — Episode One",
  "revision": 1,
  "scene_brief": "Flat-ink screen print, never photography: a 1972 farewell supper in a closed department store",
  "style_reference_id": "cover",
  "scenarios": [
    {
      "schema_version": 1,
      "kind": "scenario-binding-v1",
      "ref": "scenarios/e1_way_in.toml",
      "source_sha256": "<sha256 of the authored scenario document>"
    }
  ],
  "cast": [
    {
      "actor_id": "edwin",
      "character_profile": {
        "schema_version": 1,
        "kind": "character-profile-binding-v1",
        "ref": "characters/edwin.toml",
        "source_sha256": "<sha256-of-the-exact-edwin.toml-bytes>"
      }
    }
  ],
  "references": [
    {
      "reference_id": "cover",
      "source": "references/cover.png",
      "source_sha256": "<sha256-of-the-exact-plate-bytes>",
      "rights_status": "unreviewed",
      "rights_basis": ["Original brand-neutral first-party plate."]
    }
  ],
  "presentation": {
    "framing_zoom": 70,
    "source_framing_zoom": 70
  },
  "transparency_mode": "native"
}
```

`scenarios` holds `1..16` bindings and `cast` holds `1..16` actors. Each cast
entry says which package members draw one actor the bound scenarios can show:
the scenario says who exists and what they may wear on their face, and never
which profile or plate supplies it, because the same scenario is meant to be
staged by more than one consumer. The profile's age is `18..120`.
`transparency_mode` is quality-first `native` or the explicit degraded `chroma`
path. It selects alpha processing, not an image provider. The format also admits
`ai`, which would need a background-removal route; the game declares none, so the
builder refuses it while planning.

### Expressions are authored, per actor

The recipe used to own a locked `neutral | delighted | flustered | concerned`
taxonomy, and one model-written set of four directions was applied to every actor
in the scene. That is a set of faces for one genre wearing the costume of a
safety rule. A murder mystery has no reading of `delighted` that belongs on a
detective at a crime scene, and a shared direction set guaranteed that nine
people got the same four faces.

An expression now has two authors and neither may do the other's job:

| Half | Owner | Why there |
| --- | --- | --- |
| Which faces exist, by id | the scenario's `[[cast]] expressions` | the narrative is what can ask for a face, and admission already proves the script only names declared ones |
| What each face looks like | the actor's `character-profile-v1` `[[expressions]]` | a face is a fact about the person, like `visual_identity` and `wardrobe`, and travels with the profile wherever it is staged |

```toml
[[expressions]]
expression_id = "composed"                       # lower_snake_case
label = "Composed"                               # <= 96 chars, shown to people
description = "Level and unreadable, giving nothing away"   # <= 200 chars, shown to people
direction = "Level gaze held a beat longer than comfortable, lips closed and even, chin fractionally raised, brows still."  # <= 1000 chars, the only text a provider sees
```

`label` and `description` are displayed copy; `direction` is the only text handed
to a provider. Keeping them apart is what stops provider instructions leaking
into a caption, and a caption from being asked to draw a face.

Three rules the resolver enforces offline:

1. **The first entry is the base plate.** It is generated from scratch against
   the style plate; every other entry is a face-only edit of it. So the resting
   face leads — `composed` for Ruth, `blunt` for Ward. Nothing anywhere recovers
   the base from a name: the builder draws the first entry against the plates and
   wires every other face to its output.
2. **Set equality, both directions.** An actor's profile ids must be exactly the
   union of that actor's `expressions` across the bound scenarios. An id the
   script uses and the profile does not describe would be a missing plate; one
   the profile describes and no script ever shows is a plate paid for and never
   seen. This is the same rule the drawable cast and the stage list are already
   held to, one level down.
3. **Two to eight faces** per drawable actor: a base plus at least one edit.

The union across scenarios merges expression sets rather than refusing them: a
scenario that only ever shows an actor `shut` and one that shows her `exposed`
are the same person. It is the *stage* and *track* declarations that refuse a
disagreement, because those are one image and one recording.

Note the cost this puts on authoring: the directions live in the profile, so the
profile digest covers them, and editing one direction re-bills all of that
actor's plates. Get an actor's faces right in one pass rather than iterating one
at a time.

**The style plate is authored, not generated.** `style_reference_id` names one
declared reference; the resolver reads its bytes from inside the package, follows
no symlink, and refuses a digest that no longer matches - offline, before any
spend. Its shape is the author's: a portrait of one character and a wide
establishing shot of a place are both legitimate art direction, and the resolver
checks only that each edge is `512..4096`px, which catches a thumbnail pasted in
by mistake. Nothing composites the plate - it is attached to provider calls as a
reference for medium, palette and light - so the bundle pins no canvas for it
either. It is the one asset in the bundle the pipeline did not make: the run
republishes the author's exact bytes, proven by digest, so a canvas rule there
could only ever refuse a valid package at the package step after every image had
been drawn and paid for. The generated roles keep their canvases, because those
are checks on something the pipeline produced.

The plate is published into the run as the style asset and attached to every
generated image; it is an input of each image step, so its digest is part of
that step's identity, and replacing the file re-bills the scene deliberately rather than leaving sprites
drawn against a plate that no longer exists. It fixes medium, palette and light
for the whole scene and asserts nobody's identity; only an actor that binds a
plate as its own `reference_id` is held to the person in it. Its rights decision
travels with the bytes, because the run ships a copy; the recipe never infers
redistribution permission. A declared reference nothing consumes is refused.

## Plan and build

The game's folder is a gnode project; `pipeline/workflow.py:scene` reads the scene
package with the scene's own reader and writes one step per plan, image and track.
From `godot/games/the_grain`:

```bash
gnode plan pipeline/workflow.py:scene --arg package=inputs
gnode run pipeline/workflow.py:scene --arg package=inputs --live --max-usd 150 \
  --deliver package=../../../out/<tag>/{key}
```

Structured generation writes one `dialogue-scene-plan-v8` per drawable actor,
with `schema_version: 8`, `recipe_version: "dialogue-scene-v8"`,
`policy_version: "coming-of-age-nonexplicit-v3"`, and
`expression_profile: "expression-core-v3"`. It binds the **art** request
digest - not the whole document, because a plan is not a function of a line of
dialogue and its identity says so - the appearance id, the authored profile and
identity-plate digests, shared
identity/wardrobe/pose/lighting locks, fixed canvas geometry, the actor's own
authored expression directions copied from its profile, and prompt-template
digests. Only pose, lighting and style are generated: identity and wardrobe are
composed deterministically from the profile, and the expressions are authored, so
a provider is never asked to invent a face for anybody. The model answers with
those three locks alone; a judge holds the answer inside the authored frame and
asks again when it does not fit, and the plan is the frame with the accepted
locks in it. The plan's prompt carries the art request — exactly the fields
its digest covers — and never the narrative, so rewording a line asks for no plan
again. (v8 sent the whole request, scenario digests included, and relied on its
cache key to ignore them; with the request as the step's identity, that would have
re-asked every plan for a reworded line.)

Before any image, one structured call selects one approved style vocabulary
mode, judged so it treats every asset kind the scene draws. Deterministic local
code materializes the exact medium, observable traits, asset treatment, and
exclusions into `style-anchor.json`, and every image prompt ends with the
anchor's clause for its asset kind. The anchor's skill, vocabulary, resource and
compiler digests bind the bundle's run identity.

### The union, and what it may not silently reconcile

`scenarios` is a list of `scenario-binding-v1` entries, each holding the scenario
by exact digest exactly as the single binding did. The scene then declares the
union of what they name:

| Union | Key | Fan-out |
| --- | --- | --- |
| Stages | `stage_id` | one backdrop (paint, judge, fit) per distinct stage |
| Drawable cast | `actor_id` | one plan, a base face and one edit per remaining face, each judged and finished into a sprite, per distinct actor |
| Tracks | `track_id` | one track (compose, judge) per distinct track |

Order is first declaration across the bound scenarios, which is the order the
build fans out in and the order the bundle lists.

Two scenarios that name one id with different content are **refused while
resolving**, offline. A stage is one backdrop and a track is one recording, so
two briefs for one id is not a merge the pipeline may perform: silently taking
the first-bound scenario's brief would make the art depend on binding order.
Expressions merge instead of clashing — an actor two scenarios show with
different expression sets is one person — but a disagreement about an actor's
display name is refused for the same reason a stage brief is. The refusal names
both scenarios and both briefs: keeping the first-bound one would let the order
`scene.toml` happens to list its scenarios in decide which writer's room gets
drawn, and discard the other silently.

A step's identity is what it is asked and shown, never which scenario asked for
it: a backdrop step is named for its stage and reads that stage's own brief, an
actor's faces are named for the actor and read the profile, the plan and the
plates, and a track reads its own brief and intent. Binding another scenario that
shows only the existing cast therefore leaves every existing step's identity
untouched, and costs only the stages and tracks it introduces. One that adds an
actor changes the cast the style is selected for and the art request every plan
binds, so it re-bills the scene's art deliberately.

Before any step runs, the builder resolves the scene: it validates the package,
admits every bound scenario (a scenario the proof refuses is refused while
planning, and nothing is paid for against it) and refuses `ai` transparency. The
steps are:

1. `style`: the selection's shape, the selection, its judge, and the anchor with
   one clause per asset kind.
2. `stages/<stage>`: paint the backdrop against the style plate at the provider
   canvas, judge it, and fit it to the runtime canvas.
3. `actors/<actor>/plan`: the plan's shape, the draft locks, their judge, and the
   plan.
4. `actors/<actor>/<expression>`: compose the face's brief from the plan, draw it,
   judge it, and finish the sprite. The first face is drawn against the style
   plate (and the actor's own identity plate when it binds one); every other face
   is an edit of it.
5. `tracks/<track>`: compose the track and judge it (a playable MP3 of at least
   20 seconds).
6. `interface/<role>`: the shared UI sheet family, one sheet per role.
7. `package`: read the scene again from its own files, lay out every member the
   bundle binds — request, profiles, plans, compiled scenarios and their proofs,
   the style plate and every published asset — and write `bundle.json`. A
   published file the bundle does not bind is refused.

The checked plan contract below pins the build of The Grain's scene package:

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "dialogue-scene-gnode-plan-contract-v1",
  "fixture_ref": "godot/games/the_grain/inputs",
  "builder": "pipeline/workflow.py:scene",
  "workflow_id": "the-grain-scene",
  "topology_sha256": "bfd00e9eb348e842f74b12976def7db3c4eace9d2ce16b312866e8d05c3f9e28",
  "node_count": 827,
  "step_count": 227,
  "first_take_operation_counts": {
    "image.edit": 47,
    "local": 164,
    "music.generate": 4,
    "structured.generate": 12
  },
  "outputs": [
    "package"
  ],
  "type_ids": [
    "./pipeline/nodes/interface.py#admit_ui_sheet",
    "./pipeline/nodes/interface.py#publish_ui_sheet",
    "./pipeline/nodes/interface.py#ui_review_schema",
    "./pipeline/nodes/interface.py#ui_template",
    "./pipeline/nodes/scene.py#admit_plan",
    "./pipeline/nodes/scene.py#admit_scene_image",
    "./pipeline/nodes/scene.py#admit_scene_track",
    "./pipeline/nodes/scene.py#backdrop",
    "./pipeline/nodes/scene.py#face_brief",
    "./pipeline/nodes/scene.py#plan_record",
    "./pipeline/nodes/scene.py#plan_schema",
    "./pipeline/nodes/scene.py#scene_package",
    "./pipeline/nodes/scene.py#sprite",
    "./pipeline/nodes/style.py#admit_style",
    "./pipeline/nodes/style.py#selection_schema",
    "./pipeline/nodes/style.py#style_record",
    "gnode/image.edit@1",
    "gnode/music.generate@1",
    "gnode/structured.generate@1"
  ]
}
```
<!-- pipeline-graph-contract:end -->

### Image routing

Each backdrop, face and UI sheet is a `gnode/image.edit@1` step with its
references attached in order, its exact provider canvas and an opaque or
transparent background. A transparent face requires the route's
`transparent_background` feature. The game's `gnode.yaml` binds the image steps,
structured calls and music to their routes; a route without a feature a step
requires is refused while planning, before any key is checked. The 1680x944
backdrop is fitted locally to 1672x941 for the bundle. Nothing replaces a failed
or uncredentialed provider automatically; re-route by editing the binding table.

`native` and `chroma` remain explicit alpha strategies after routing. `native`
asks the route for provider-generated transparency, judges that the alpha is
really there, and covers it onto the 1024x1536 canvas. `chroma` asks for an
opaque draw on the key colour, judges that it keys, and keys and cleans it
locally. Neither changes the selected route.

Every provider operation owns one initial attempt plus at most five retries.
Transport, decoding and media failures remain inside that service boundary. A
judge's rejection is a redraw, not a retry: each judged painting, plan and track
gets at most six takes, then the run stops on it. A rerun reuses only cached
results whose content and lineage still match.

Within structured requests, standard JSON Schema vocabulary—including
`$defs`, `$ref`, `additionalProperties`, `maxLength`, and `minLength`—retains
its mandated spelling. Recipe-owned property names, definition identifiers,
and matching reference targets are lower_snake_case.

## Portable bundle: `dialogue-scene-bundle-v9`

`bundle.json` is the host's sole input. It has `schema_version: 9`,
`kind: "dialogue-scene-bundle-v9"`, `recipe: "dialogue-scene"`, and
`recipe_version: "dialogue-scene-v8"`. It binds the game id, the request and
per-actor plan files by SHA-256, each canonical character profile, the authored
style plate and the package path it came from, the compiled scenarios and their
proofs, run identity, review state, rights state, and the selected assets:

- one opaque `style` PNG, republished byte for byte from the authored plate at
  whatever size the author drew it;
- one opaque `background` PNG at `1672x941` per distinct stage;
- one `1024x1536` alpha-bearing `expression` PNG per face a drawable actor's
  profile declares, two to eight of them; and
- one `audio/mpeg` `track` per distinct track; and
- one `1024x1024` alpha-bearing `ui` PNG per interface role — two nine-slice
  sheets and the preview icon grid — generated by the shared sheet triplet the
  [UI contract](../../_shared/docs/formats/ui.md) declares.

Each asset record includes its id, role, optional expression state, optional
actor or track id, portable path, content digest, byte count and media facts.
Copy the projection derives from authored prose - titles and alt text - is cut
to its field's budget on a word boundary and trimmed, so an author whose sentence
happens to be the wrong length is not refused by the package step. Media facts
are discriminated on mime type: an image carries width, height and alpha, a track
carries its probed duration, and each role is held to the one that fits it.

v9 binds files by path and digest alone. v8 also bound a provenance sidecar per
file, the attempt each asset came from and an attempt ledger; which call made
each file and how many takes it needed is now the gnode run's record, and
rejected takes stay there and are never delivered.

The strict `scene_data` projection carries recipe/caller-owned copy only:
`scene_id`, title and label, concept/background asset bindings and background
alt text, appearance copy, placement and framing, `available_states` (the sorted
union of every actor's own expression ids — the vocabulary, not a per-actor
promise), each actor's own expression records with labels/descriptions/alts
carried through from its profile, and the `ui` block: per role,
the geometry the producer's gate measured on the sheet plus the asset id the
sheet is. The dialogue box and the end card are the one `panel_frame` sheet at
two sizes; the choice list is the `button_rect` sheet, so an option's hover and
pressed looks are the producer's pixels rather than a tint that never moved; the end card's
play-again control is the `preview_icons` grid's `retry` glyph on that same button sheet. The bundle validator requires
these asset ids and state bindings to match the selected inventory exactly.

`scene_data.scenarios` carries the compiled narratives, in the order the scene
bound them, and `bundle.scenarios` names each published program, the proof that
admitted it, and the binding both came from. A consumer plays from the programs;
a flat beat list would only ever be walkable from the first line to the last. The
`stages`, `actors` and `tracks` beside them are exactly the union over those
programs — checked in both directions, so a `stage` or `show` naming something
with no plate is a refused package rather than a missing texture at play time,
and a plate nothing shows is refused as art paid for and unseen.

The Godot host accepts exactly one contract: it validates the complete bundle
before it plays anything, checks that the published plate is the one the package
declared, by digest rather than by path, and refuses any other kind or version
with a notice naming the build that makes the current one. It may not invent
missing copy, generation facts, review evidence, or rights.

## Provenance, review, and publication

The gnode run is the provenance: every step's request, route, references by
digest, takes, judge verdicts and outputs, in the run's records. Nothing the
build delivers carries credentials, signed URLs, or private absolute paths.

Generation emits `review.status: "pending"`,
`rights.aggregate: "unreviewed"`, and
`rights.publication_authorized: false`. `demo-games dialogue-scene review` records an
independent digest-bound verdict beside the bundle. A review pass never grants
rights, and local play never authorizes export, repository publication, or
redistribution; those remain subject to the separate generated-media publication
gate.

## Historical built-in assets

The original showcase once kept under web/public/dialogue-scene/demo/anime has
been removed from the tree; its provenance survives in history only. It is not a portable v1 bundle, not an accepted current
wire schema, and not a compatibility fixture for v2. The separately versioned
built-in `anime-v2/` demo set is also consumer-owned fixture data rather than a
producer bundle example. Neither tree is rewritten by theme generation or by
this contract migration.

See [framing control](dialogue-framing.md).
