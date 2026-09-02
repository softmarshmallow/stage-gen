# Visual Novel Scene Kit: dialogue-scene asset contract

> **Status: implemented v5 headless recipe.** The Python `dialogue-scene`
> recipe generates a portable, provider-neutral bundle. The web application is
> a consumer adapter and never generates assets.

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

The graph reads no fixed count anywhere: the bound scenarios declare the cast,
the stages and the tracks between them, and the fan-out follows the union.

## Ownership and boundary

| Location                                | Responsibility                                                                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/stage_gen/recipes/dialogue_scene/` | Adult/non-explicit policy, expression taxonomy, prompts, strict v3 models, stage graph, cache identity, validation, and bundle assembly.                                              |
| `src/stage_gen/components/`             | Provider-neutral structured generation, image generation, music generation, and background removal with one six-attempt retry owner. `scenario/` owns the narrative contract and its proof; `game_soundtrack/` owns authored track intent and the one music prompt compiler both recipes use. |
| `src/stage_gen/media/`                  | Shared deterministic image inspection and transforms.                                                                                                                                 |
| `src/stage_gen/orchestration/`          | Provider composition and generic recipe dispatch.                                                                                                                                     |
| `web/`                                  | Strict bundle validation, immutable installation, projection into web runtime objects, activation, status, and rollback. It never imports Python recipe internals or calls providers. |

`dialogue-scene` is a sibling of `sideview-platformer`, not a mode within it.
Recipe vocabulary and visual assumptions do not enter generic components; web
camera, UI, and gameplay assumptions do not enter the producer bundle.

## Authored package: `dialogue-scene-v5`

One scene is one directory under `library/games/`, holding `scene.toml` beside
the members it names by exact relative path: the scenarios it plays, the
character profiles it binds, and the `references/` its art is drawn against. The
document is strict TOML: every key is lower_snake_case; camelCase, unknown keys,
and implicit aliases are rejected. The contract is temporary by intent - the
standing goal is for every game kind to be declared through `game.toml`.

```json
{
  "schema_version": 5,
  "kind": "dialogue-scene-v5",
  "game_id": "larkfield",
  "display_name": "Larkfield",
  "revision": 2,
  "scene_brief": "A student records an empty classroom after the last class of summer",
  "style_reference_id": "cover",
  "scenarios": [
    {
      "schema_version": 1,
      "kind": "scenario-binding-v1",
      "ref": "scenarios/last_class.toml",
      "source_sha256": "<sha256 of the authored scenario document>"
    }
  ],
  "cast": [
    {
      "actor_id": "nao",
      "reference_id": "cover",
      "character_profile": {
        "schema_version": 1,
        "kind": "character-profile-binding-v1",
        "ref": "characters/nao.toml",
        "source_sha256": "<sha256-of-the-exact-nao.toml-bytes>"
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
`transparency_mode` is quality-first `native`, explicit compatibility `ai`, or
the explicit degraded `chroma` path.

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
   the base from a name: the graph decides which node is the base and records it
   in that node's declared type, and the handlers read the type.
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
could only ever refuse a valid package at the terminal node after every image had
been drawn and paid for. The generated roles keep their canvases, because those
are checks on something the pipeline produced.

The plate is published into the run as the style asset, attached to every
generated image, and its digest rides each image node's cache identity, so
replacing the file re-bills the scene deliberately rather than leaving sprites
drawn against a plate that no longer exists. It fixes medium, palette and light
for the whole scene and asserts nobody's identity; only an actor that binds a
plate as its own `reference_id` is held to the person in it. Its rights decision
travels with the bytes, because the run ships a copy; the recipe never infers
redistribution permission. A declared reference nothing consumes is refused.

## Plan and stage graph

Structured generation writes one `dialogue-scene-plan-v8` per drawable actor,
with `schema_version: 8`, `recipe_version: "dialogue-scene-v8"`,
`policy_version: "coming-of-age-nonexplicit-v3"`, and
`expression_profile: "expression-core-v3"`. It binds the **art** request
digest - not the whole document, because a plan is not a function of a line of
dialogue and its cache key says so - the appearance id, the authored profile and
identity-plate digests, shared
identity/wardrobe/pose/lighting locks, fixed canvas geometry, the actor's own
authored expression directions copied from its profile, and prompt-template
digests. Only pose, lighting and style are generated: identity and wardrobe are
composed deterministically from the profile, and the expressions are authored, so
a provider is never asked to invent a face for anybody.

Before planning or images, structured generation may select only one approved
style vocabulary mode. Deterministic local code materializes the exact medium,
observable traits, asset treatment, and exclusions into `style-anchor.json`.
Its anchor, skill, vocabulary, resource, and compiler digests bind cache, run
identity, plan provenance, and bundle provenance.

### The union, and what it may not silently reconcile

`scenarios` is a list of `scenario-binding-v1` entries, each holding the scenario
by exact digest exactly as the single binding did. The scene then declares the
union of what they name:

| Union | Key | Fan-out |
| --- | --- | --- |
| Stages | `stage_id` | one `backdrop.generate` per distinct stage |
| Drawable cast | `actor_id` | one profile, plan, base plate, three edits and four canonicalizations per distinct actor |
| Tracks | `track_id` | one `track.generate` per distinct track |

Order is first declaration across the bound scenarios, which is the order the
graph fans out in and the order the bundle lists.

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

Node identity is derived from what the image **is**, never from which scenario
asked for it: a backdrop node is named for its stage and keyed on that stage's own
brief, an actor's plates are named for the actor and keyed on the profile and
plate digests, and a track is keyed on its own brief and intent. Binding a
seventh scenario to a scene therefore leaves every existing node's cache key
untouched, and costs only the art that scenario introduces.

The exact stages are:

1. `prepare`: validate the package and read its digest-bound members.
2. `scenario-admission`: one node per bound scenario, publishing its compiled
   program at `scenarios/<id>.json` and the proof that admitted it at
   `scenarios/<id>.validation.json`. One node each rather than one node for all
   of them, so editing the fourth scenario does not re-publish the other five and
   each proof stays an artifact of its own.
3. `style-selection`: select a mode and locally materialize the style anchor.
4. `identity-plate`: publish the authored plate into the run; nothing generates it.
5. `scene-plan`: produce and validate the strict structured plan, per actor.
6. `backdrops`: one opaque plate per distinct stage, against the style plate.
7. `base-plate`: draw each actor's first authored face from the style plate.
8. `expressions`: edit that base plate into the actor's remaining faces, one
   node each, from each face's own authored direction.
9. `canonicalize`: create the validated transparent runtime sprites.
10. `tracks`: one music track per distinct track, from its authored brief and
    generation intent. Ordered after the request but descended from neither the
    narrative nor the art: music owes nothing to a style plate, so its own brief
    and intent are the whole of its cache key.
11. `bundle`: validate all bindings and write the portable bundle.

Every provider operation owns one initial attempt plus at most five retries.
Transport, decoding, schema/media, dimension, chroma, and alpha failures remain
inside that service boundary. The recipe does not wrap providers in another
retry loop. Resume reuses only digest- and lineage-valid cache entries; force
invalidates the selected stage and required descendants.

Within structured provenance, standard JSON Schema vocabulary—including
`$defs`, `$ref`, `additionalProperties`, `maxLength`, and `minLength`—retains
its mandated spelling. Recipe-owned property names, definition identifiers,
and matching reference targets are lower_snake_case.

## Portable bundle: `dialogue-scene-bundle-v8`

`bundle.json` is the adapter's sole input. It has `schema_version: 8`,
`kind: "dialogue-scene-bundle-v8"`, `recipe: "dialogue-scene"`, and
`recipe_version: "dialogue-scene-v8"`. It binds the game id, canonical document
and per-actor plan files plus their provenance paths and SHA-256 digests, each
canonical character profile, the authored style plate and the package path it
came from, the compiled scenarios, `attempts.json`, run identity, review state,
rights state, and the selected assets:

- one opaque `style` PNG, republished byte for byte from the authored plate at
  whatever size the author drew it;
- one opaque `background` PNG at `1672x941` per distinct stage;
- one `1024x1536` alpha-bearing `expression` PNG per face a drawable actor's
  profile declares, two to eight of them; and
- one `audio/mpeg` `track` per distinct track; and
- one `1024x1024` alpha-bearing `ui` PNG per interface role — two nine-slice
  sheets and the preview icon grid — generated by the shared sheet triplet the
  [UI contract](game/ui.md) declares.

Each asset record includes its id, role, optional expression state, optional
actor or track id, portable path, content digest, byte count, media facts,
provenance path and digest, and selected attempt. Copy the projection derives
from authored prose - titles and alt text - is cut to its field's budget on a
word boundary and trimmed, so an author whose sentence happens to be the wrong
length is not refused by the terminal node. Media facts are discriminated
on mime type: an image carries width, height and alpha, a track carries its
probed duration, and each role is held to the one that fits it. Rejected candidates and raw derivations remain lineage and
are never selected runtime assets.

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
with no plate is a refused package rather than a missing texture in a browser,
and a plate nothing shows is refused as art paid for and unseen.

The web adapter validates the complete portable bundle before copying it into
an immutable digest-addressed installation. Only then does it translate
`scene_data` into the web fixture's internal runtime naming. The adapter may
not invent missing copy, generation facts, review evidence, or rights.

The consumer accepts exactly one contract. It must bind the style-anchor
artifact, its provenance, and matching compiler/resource facts through plan and
bundle provenance, and it checks that the published plate is the one the package
declared, by digest rather than by path. No style values are synthesized, and
unknown recipe versions are rejected.

## Provenance, review, and publication

Every selected request, plan, image, and bundle sidecar uses provenance
`schema_version: 2` and binds the exact artifact digest. Sidecars preserve the
sanitized final prompt, provider/model/tool disclosure, seed availability,
parameters, validation, references and digests, attempts/retries, derivation,
timestamp, and rights state. Paths are portable and never contain credentials,
private absolute paths, or signed URLs.

Generation emits `review.status: "pending"`,
`rights.aggregate: "unreviewed"`, and
`rights.publication_authorized: false`. Installation may retain such a bundle
for inspection, but activation fails closed. Activation requires an
independent digest-bound `pass` review plus `restricted` local-demo rights and
`publication_authorized: false`. A review pass never grants rights. Local web
activation never authorizes export, repository publication, or redistribution;
those remain subject to the separate generated-media publication gate.

## Historical built-in assets

`web/public/dialogue-scene/demo/anime/` is preserved historical provenance for
the original showcase. It is not a portable v1 bundle, not an accepted current
wire schema, and not a compatibility fixture for v2. The separately versioned
built-in `anime-v2/` demo set is also consumer-owned fixture data rather than a
producer bundle example. Neither tree is rewritten by theme generation or by
this contract migration.

See [framing control](../dialogue-scene-framing.md).
