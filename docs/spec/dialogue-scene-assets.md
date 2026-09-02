# Visual Novel Scene Kit: dialogue-scene asset contract

> **Status: implemented v3 headless recipe.** The Python `dialogue-scene`
> recipe generates a portable, provider-neutral bundle. The web application is
> a consumer adapter and never generates assets.

One scene packages a cast of adult character identities, one backdrop per
declared stage, four static expression sprites per drawable actor, one music
track per declared track, and presentation data, around an authored `scenario`
that owns the narrative. It does not own story generation, relationship state,
animation, rigging, lip sync, or a game runtime.

The graph reads no fixed count anywhere: the scenario declares the cast, the
stages and the tracks, and the fan-out follows.

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

## Authored package: `dialogue-scene-v3`

One scene is one directory under `library/games/`, holding `scene.toml` beside
the members it names by exact relative path: the character profile it binds, and
the `references/` its art is drawn against. The document is strict TOML: every
key is lower_snake_case; camelCase, unknown keys, and implicit aliases are
rejected. The contract is temporary by intent - the standing goal is for every
game kind to be declared through `game.toml`.

```json
{
  "schema_version": 1,
  "kind": "dialogue-scene-v2",
  "game_id": "larkfield",
  "display_name": "Larkfield",
  "revision": 1,
  "scene_brief": "A student records an empty classroom after the last class of summer",
  "identity_reference_id": "cover",
  "character_profile": {
    "schema_version": 1,
    "kind": "character-profile-binding-v1",
    "ref": "character.toml",
    "source_sha256": "<sha256-of-the-exact-character.toml-bytes>"
  },
  "references": [
    {
      "reference_id": "cover",
      "source": "references/cover.png",
      "source_sha256": "<sha256-of-the-exact-plate-bytes>",
      "rights_status": "unreviewed",
      "rights_basis": ["Original brand-neutral first-party plate."]
    }
  ],
  "background": {
    "description": "An original empty classroom at blue hour, no people"
  },
  "scenario": {
    "schema_version": 1,
    "kind": "scenario-binding-v1",
    "ref": "scenario.toml",
    "source_sha256": "<sha256 of the authored scenario document>"
  },
  "presentation": {
    "slot": "right",
    "framing_zoom": 70,
    "source_framing_zoom": 70
  },
  "transparency_mode": "native"
}
```

Exactly one character and a background direction are supported. The profile's
age is `18..120`; the recipe owns the locked `neutral`, `delighted`, `flustered`,
and `concerned` taxonomy. Dialogue contains `1..12` authored beats and passes
through unchanged. Every beat must select a locked expression state.
`transparency_mode` is quality-first `native`, explicit compatibility `ai`, or
the explicit degraded `chroma` path.

**The identity plate is authored, not generated.** `identity_reference_id` names
one declared reference; the resolver reads its bytes from inside the package,
follows no symlink, and refuses a digest that no longer matches - offline,
before any spend. That plate is published into the run as the concept asset,
attached to every generated image, and its digest rides each image node's cache
identity, so replacing the file re-bills the scene deliberately rather than
leaving sprites drawn against a plate that no longer exists. Its rights decision
travels with the bytes, because the run ships a copy; the recipe never infers
redistribution permission. A declared reference nothing consumes is refused.

## Plan and stage graph

Structured generation writes one `dialogue-scene-plan-v7` per drawable actor,
with `schema_version: 7`, `recipe_version: "dialogue-scene-v7"`,
`policy_version: "coming-of-age-nonexplicit-v3"`, and
`expression_profile: "expression-core-v3"`. It binds the **art** request
digest - not the whole document, because a plan is not a function of a line of
dialogue and its cache key says so - the appearance id, the authored profile and
identity-plate digests, shared
identity/wardrobe/pose/lighting locks, fixed canvas geometry, the four
expression directions, and prompt-template digests.

Before planning or images, structured generation may select only one approved
style vocabulary mode. Deterministic local code materializes the exact medium,
observable traits, asset treatment, and exclusions into `style-anchor.json`.
Its anchor, skill, vocabulary, resource, and compiler digests bind cache, run
identity, plan provenance, and bundle provenance.

The exact stages are:

1. `prepare`: validate the package and read its digest-bound members.
2. `style-selection`: select a mode and locally materialize the style anchor.
3. `identity-plate`: publish the authored plate into the run; nothing generates it.
4. `scene-plan`: produce and validate the strict structured plan.
5. `backdrops`: one opaque plate per declared stage, against the style plate.
6. `neutral`: derive each actor's neutral sprite from the style plate.
7. `expressions`: edit each neutral reference into three expression variants.
8. `canonicalize`: create the validated transparent runtime sprites.
9. `tracks`: one music track per declared track, from its authored brief and
   generation intent. Ordered after the request but descended from neither the
   narrative nor the art: music owes nothing to a style plate, so its own brief
   and intent are the whole of its cache key.
10. `bundle`: validate all bindings and write the portable bundle.

Every provider operation owns one initial attempt plus at most five retries.
Transport, decoding, schema/media, dimension, chroma, and alpha failures remain
inside that service boundary. The recipe does not wrap providers in another
retry loop. Resume reuses only digest- and lineage-valid cache entries; force
invalidates the selected stage and required descendants.

Within structured provenance, standard JSON Schema vocabulary—including
`$defs`, `$ref`, `additionalProperties`, `maxLength`, and `minLength`—retains
its mandated spelling. Recipe-owned property names, definition identifiers,
and matching reference targets are lower_snake_case.

## Portable bundle: `dialogue-scene-bundle-v7`

`bundle.json` is the adapter's sole input. It has `schema_version: 7`,
`kind: "dialogue-scene-bundle-v7"`, `recipe: "dialogue-scene"`, and
`recipe_version: "dialogue-scene-v7"`. It binds the game id, canonical document
and per-actor plan files plus their provenance paths and SHA-256 digests, each
canonical character profile, the authored style plate and the package path it
came from, the compiled scenario, `attempts.json`, run identity, review state,
rights state, and the selected assets:

- one opaque `style` PNG at `1024x1536`, republished from the authored plate;
- one opaque `background` PNG at `1672x941` per declared stage;
- four `1024x1536` alpha-bearing `expression` PNGs per drawable actor, one for
  each locked state; and
- one `audio/mpeg` `track` per declared track; and
- one `1024x1024` alpha-bearing `ui` PNG per interface role, generated by the
  shared nine-slice atlas triplet the [UI contract](game/ui.md) declares.

Each asset record includes its id, role, optional expression state, optional
actor or track id, portable path, content digest, byte count, media facts,
provenance path and digest, and selected attempt. Media facts are discriminated
on mime type: an image carries width, height and alpha, a track carries its
probed duration, and each role is held to the one that fits it. Rejected candidates and raw derivations remain lineage and
are never selected runtime assets.

The strict `scene_data` projection carries recipe/caller-owned copy only:
`scene_id`, title and label, concept/background asset bindings and background
alt text, appearance copy, placement and framing, available states, four
expression records with labels/descriptions/alts, and the `ui` block: per role,
the geometry the producer's gate measured on the sheet plus the asset id the
sheet is. The dialogue box and the end card are the one `panel_frame` sheet at
two sizes; the choice list is the `button_rect` sheet, so an option's hover and
pressed looks are the producer's pixels rather than a tint that never moved. The bundle validator requires
these asset ids and state bindings to match the selected inventory exactly.

The narrative is not part of `scene_data`. A scene binds an authored
[scenario](game/scenario.md) instead, and the bundle names the compiled program
and the proof that admitted it (`scenario`, `scenario_validation`) beside the
binding it came from. A consumer plays from the program; a flat beat list would
only ever be walkable from the first line to the last.

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
