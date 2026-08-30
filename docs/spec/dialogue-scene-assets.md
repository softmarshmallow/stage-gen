# Visual Novel Scene Kit: dialogue-scene asset contract

> **Status: implemented v2 headless recipe.** The Python `dialogue-scene`
> recipe generates a portable, provider-neutral bundle. The web application is
> a consumer adapter and never generates assets.

The first slice packages one adult character identity, one required scene
background, four static expression sprites, caller-authored dialogue, and
presentation data. It does not own story generation, branching, relationship
state, animation, rigging, lip sync, or a game runtime.

## Ownership and boundary

| Location                                | Responsibility                                                                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/stage_gen/recipes/dialogue_scene/` | Adult/non-explicit policy, expression taxonomy, prompts, strict v2 models, stage graph, cache identity, validation, and bundle assembly.                                              |
| `src/stage_gen/components/`             | Provider-neutral structured generation, image generation, and background removal with one six-attempt retry owner.                                                                    |
| `src/stage_gen/media/`                  | Shared deterministic image inspection and transforms.                                                                                                                                 |
| `src/stage_gen/orchestration/`          | Provider composition and generic recipe dispatch.                                                                                                                                     |
| `web/`                                  | Strict bundle validation, immutable installation, projection into web runtime objects, activation, status, and rollback. It never imports Python recipe internals or calls providers. |

`dialogue-scene` is a sibling of `sideview-platformer`, not a mode within it.
Recipe vocabulary and visual assumptions do not enter generic components; web
camera, UI, and gameplay assumptions do not enter the producer bundle.

## Public request: `dialogue-theme-request-v2`

The JSON or TOML input is strict. Every application-owned key is
lower_snake_case; v1, camelCase, unknown keys, and implicit aliases are
rejected.

```json
{
  "schema_version": 2,
  "kind": "dialogue-theme-request-v2",
  "scene_brief": "Adult university study lounge after a graduate seminar",
  "appearance": {
    "id": "mio-researcher",
    "label": "Mio",
    "age": 23,
    "role": "Graduate researcher",
    "description": "Adult woman in a navy cardigan",
    "concept": {
      "mode": "generate",
      "description": "Original clean Japanese anime visual-novel character direction"
    }
  },
  "background": {
    "mode": "generate",
    "description": "Evening university study lounge with no people"
  },
  "dialogue": [
    {
      "id": "opening",
      "speaker": "Mio",
      "text": "I hoped you would stay after the seminar.",
      "expression_state": "neutral"
    }
  ],
  "presentation": {
    "slot": "right",
    "framing_zoom": 70,
    "source_framing_zoom": 70
  },
  "transparency_mode": "native"
}
```

Exactly one appearance and a required background are supported. Appearance age
is `21..120`; the recipe owns the locked `neutral`, `delighted`, `flustered`,
and `concerned` taxonomy. Dialogue contains `1..12` caller-authored beats and
passes through unchanged. Every beat must select a locked expression state.
`transparency_mode` is quality-first `native`, explicit compatibility `ai`, or
the explicit degraded `chroma` path.

Concept and background sources use `mode: "generate"` or `mode: "reuse"`.
Reuse requires a portable reference, exact SHA-256, and explicit rights state;
the recipe verifies and copies it into the isolated run rather than symlinking
or inferring redistribution permission.

## Plan and stage graph

Structured generation writes `dialogue-scene-plan-v2` with
`schema_version: 2`, `recipe_version: "dialogue-scene-v3"`,
`policy_version: "adult-romance-nonexplicit-v2"`, and
`expression_profile: "romance-core-v2"`. It binds the canonical request digest,
appearance id, shared identity/wardrobe/pose/lighting locks, fixed canvas
geometry, the four expression directions, and prompt-template digests.

Before planning or images, structured generation may select only one approved
style vocabulary mode. Deterministic local code materializes the exact medium,
observable traits, asset treatment, and exclusions into `style-anchor.json`.
Its anchor, skill, vocabulary, resource, and compiler digests bind cache, run
identity, plan provenance, and bundle provenance.

The exact stages are:

1. `prepare`: validate the request and ingest reusable references.
2. `style-selection`: select a mode and locally materialize the style anchor.
3. `appearance-concept`: produce or copy the opaque identity anchor.
4. `scene-plan`: produce and validate the strict structured plan.
5. `background`: produce or copy the required opaque scene plate.
6. `neutral`: derive the neutral opaque/chroma sprite from the concept.
7. `expressions`: edit the neutral reference into three expression variants.
8. `canonicalize`: create the four validated transparent runtime sprites.
9. `bundle`: validate all bindings and write the portable bundle.

Every provider operation owns one initial attempt plus at most five retries.
Transport, decoding, schema/media, dimension, chroma, and alpha failures remain
inside that service boundary. The recipe does not wrap providers in another
retry loop. Resume reuses only digest- and lineage-valid cache entries; force
invalidates the selected stage and required descendants.

Within structured provenance, standard JSON Schema vocabulary—including
`$defs`, `$ref`, `additionalProperties`, `maxLength`, and `minLength`—retains
its mandated spelling. Recipe-owned property names, definition identifiers,
and matching reference targets are lower_snake_case.

## Portable bundle: `dialogue-scene-bundle-v2`

`bundle.json` is the adapter's sole input. It has `schema_version: 2`,
`kind: "dialogue-scene-bundle-v2"`, `recipe: "dialogue-scene"`, and
`recipe_version: "dialogue-scene-v3"`. It binds canonical request and plan
files plus their provenance paths and SHA-256 digests, `attempts.json`, run
identity, review state, rights state, and exactly six selected assets:

- one opaque `concept` PNG at `1024x1536`;
- one opaque `background` PNG at `1672x941`; and
- four `1024x1536` alpha-bearing `expression` PNGs, one for each locked state.

Each asset record includes its id, role, optional expression state, portable
path, content digest, byte count, media facts, provenance path and digest, and
selected attempt. Rejected candidates and raw derivations remain lineage and
are never selected runtime assets.

The strict `scene_data` projection carries recipe/caller-owned copy only:
`scene_id`, title and label, concept/background asset bindings and background
alt text, appearance copy, placement and framing, available states, four
expression records with labels/descriptions/alts, and ordered dialogue beats.
The bundle validator requires these asset ids and state bindings to match the
selected inventory exactly.

The web adapter validates the complete portable bundle before copying it into
an immutable digest-addressed installation. Only then does it translate
`scene_data` into the web fixture's internal runtime naming. The adapter may
not invent missing copy, generation facts, review evidence, or rights.

Consumer compatibility is an explicit allowlist: historical
`dialogue-scene-v2` installations remain valid under their original contract,
while `dialogue-scene-v3` must bind the style-anchor artifact, its provenance,
and matching compiler/resource facts through plan and bundle provenance. No v2
style values are synthesized, and unknown recipe versions are rejected.

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

See the [operator workflow](../dialogue-theme-pipeline.md),
[preview boundary](../dialogue-scene-preview.md), and
[framing control](../dialogue-scene-framing.md).
