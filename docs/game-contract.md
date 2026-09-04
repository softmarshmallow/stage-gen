# Game contract

> **Contract maturity: ratified TO-BE master.**
>
> This document is the canonical high-level contract for game-oriented
> generation in `stage-gen`. It defines the target domain model, contract
> composition, ownership boundaries, and cross-contract invariants.
>
> It does not claim runtime support, enumerate implementation status, track
> migration work, or serve as a project plan. Currently executable fields and
> validation behavior are documented separately in the
> [authored game contract schema](spec/game/authored-contract-schema.md).

## Why the container is a game

A recipe produces one kind of artifact bundle: a side-scrolling stage, a
dialogue scene, or another game-facing package. A real game composes several of
those bundles under one durable identity. A dialogue scene can belong to the
same game as a hunting ground without either recipe owning the other.

The shared container is therefore a **game**, not a world, scene, recipe, or web
preview. A world is generated content inside a game; a scene is one presentation
and interaction context; a recipe is a producer; and a preview is one consumer.

This naming also keeps the contract distinct from the CURRENT `WorldSpec` and
`world_spec_<tag>.json` recipe artifacts. In the ratified target, authored map
sources replace `WorldSpec.layers` as the authority for map references, layer
planning, and ground direction.

## Why this is a contract

Game-wide direction cannot remain a flat bag of unrelated request flags. A
player profile can identify one actor, but it cannot by itself state the build
of an entire cast, the presentation profile shared by their assets, the motion
coverage required by combat, or the style that must remain coherent across
recipes.

The game contract is the place those facts are authored, versioned, validated,
digest-bound, and projected across producer and consumer boundaries. The
contract carries durable intent; it does not contain generated run paths or
engine-specific scene objects.

## Domain model

```text
game
├── identity
├── style profile
│   ├── rendering construction
│   ├── art direction
│   └── measurable visual properties
├── genre members (each owns its camera and cast)
│   ├── presentation / view profile
│   │   ├── scene dimensionality and projection
│   │   ├── camera pose and behavior envelope
│   │   ├── gameplay space and depth policy
│   │   └── asset-view requirements
│   └── cast
│       ├── player roles
│       ├── mob roles
│       └── resident and dialogue roles
├── motion
│   ├── locomotion
│   ├── action
│   ├── reaction
│   └── terminal states
├── scenarios
│   ├── dialogue
│   ├── cutscenes
│   ├── scripted gameplay
│   └── transitions
├── gameplay
│   ├── navigation
│   ├── interaction
│   ├── combat
│   └── population
├── content catalogs
│   ├── maps
│   └── soundtracks
├── rights and provenance
└── consumer bindings
    ├── runtime camera
    ├── rendering and scene adapter
    └── input, collision, and simulation adapter
```

Each branch is independently versionable. Sharing a game identity does not
make every branch one schema or one file.

## Canonical identity and library shape

Authored game material lives under one confined game identity:

```text
library/games/<game_id>/
├── game.toml
├── gameplay.toml
├── ui.toml
├── soundtrack.toml
├── maps/
│   └── <map_id>.toml
├── content/
├── references/
└── scenarios/
    ├── index.toml
    └── <sequence_id>.toml
```

`game_id` is durable and machine-readable. Display names are presentation text
and do not determine identity. Every authored source is independently
canonicalized, and the resolver computes its digest at capture, so editing a
soundtrack or map does not silently change the identity of unrelated game
direction.

Resolvers MUST confine reads to an explicitly selected library root, reject
path traversal and symlink escape, and persist only portable references. A
generated artifact MUST remain attributable to the exact authored source and
vocabulary that directed it.

## Contract composition

### Presentation

Presentation is the composition of a **view profile** and a **style profile**.
They remain separate:

- the view profile classifies scene projection, camera pose, gameplay space,
  depth policy, grid mapping, and required asset views;
- the style profile classifies rendering medium, mark making, edges, shading,
  palette, lighting, texture, shape language, proportions, and related visual
  measurements.

Neither profile may infer the other. A lateral game can be rendered in several
styles, and one style can serve several view profiles.

The canonical target terms and initial profile identities live in the
[Game view and style taxonomy](spec/game/view-and-style-taxonomy.md).

### Cast

Cast direction states which roles exist and which visual identity, anatomy,
proportion, facing coverage, and presentation requirements apply to each role.
A player, mob, resident, and dialogue portrait are not one role with many
optional fields; each role owns the invariants required by its use.

Character identity belongs to the authored character library. The game contract
binds that identity into a cast role and supplies game-wide direction around it.

### Motion

Motion direction defines semantic state coverage independently from sprite-sheet
layout. At minimum, a motion entry identifies:

- the semantic state, such as `idle`, `move`, `attack`, `hurt`, or `death`;
- which cast roles require it;
- the view and directional coverage under which it is valid;
- transition and interruption semantics; and
- the artifact contract that realizes it.

A gameplay subsystem MUST NOT advertise a visible actor transition unless every
required cast role has a validated asset or an explicitly contracted nonvisual
representation for that transition. In particular, combat that can damage the
player requires player `hurt` motion coverage; mob attack and mob hurt assets do
not satisfy that requirement.

Sprite-sheet extraction, alignment, and packing remain generic media operations.
The game or recipe supplies motion meaning, frame ordering, view requirements,
and acceptance criteria.

The prepared side-view vocabulary distinguishes capability from presentation.
`gameplay.toml` movement `crouch` authorizes the low player posture and its
movement/collision effects. Player-content motion `crouch` supplies that
posture's artwork. In V1 it means a stationary, on-both-feet crouch loop with
subtle balance or breathing phases; it does not mean crawl locomotion. `crawl`
is not an accepted alias at either contract boundary.

### Sequences

Sequences author control flow across presentation, cast, motion, gameplay, and
audio without collapsing those contracts into one timeline. The sequence layer
owns dialogue beats, choices, branches, shots, actor blocking, temporal cues,
control handoff, skip/resume semantics, and named outcomes.

A dialogue sequence is not merely a frontal camera profile. A cutscene is not
merely a video asset. Both are versioned semantic graphs whose visible and
audible requirements must resolve before playback. A cutscene may be staged
from runtime actors, 2D sprites, illustrated stills, pre-rendered video, or an
explicit hybrid.

The sequence contract references cast roles, motions, presentation profiles,
maps, soundtrack tracks, conditions, effects, and artifacts through portable
identities. It contains no executable scripts or engine object paths. Consumers
own deterministic playback and engine translation; they do not invent missing
dialogue, branches, cues, or fallback assets.

The target graph, dialogue, shot, cue, agency, and checkpoint semantics live in
the [Dialogue and cutscene sequence contract](spec/game/dialogue-and-cutscene-sequences.md).

### Gameplay

The target root `gameplay.toml` owns semantic simulation rules: navigation,
interaction, combat, population, map usage, and other systems. It describes
what must happen without embedding a particular engine's object graph or update
loop. Entry-map selection, stage flow, transitions, spawning, and map-specific
soundtrack usage belong here rather than in a map-generation source.

Combat names a weapon class rather than describing one. `weapon_class` selects
a member of a closed taxonomy, and `projectile_id` names the entry in the
projectile catalog a throwing class puts in the air; a throwing class MUST name
one and a non-throwing class MUST NOT. Both fields are identity and artwork
obligation only. Reach, damage, cadence, flight speed, and the distance an
automated policy holds are consumer-owned, exactly as the critical rate and the
experience curve are, so a game retunes without regenerating a package.

The artwork obligation is exact: the character the package draws must be able to
fight the way the package says they do. The player catalog declares `equipment`
from its own closed vocabulary, and a combat-enabled package whose pairing the
two vocabularies do not admit is refused - a `hand_weapon_v1` figure cannot
fight as `ranged_dps_v1`, and a `thrown_kit_v1` figure cannot swing. The check
is scoped to combat exactly as the required attack poses are: a package that
disables combat has no weapon class to contradict, and is free to draw whatever
its story wants. Two closed names,
compared; no authored prose is read, and the contract makes no judgement about
whether a weapon suits the character. The prose still names *which* object, and
the recipe supplies the structural direction the prose cannot carry - that the
object appears in every drawn frame, or that it is never drawn at all. Whether
the picture actually honours that is judged by the actor's semantic review,
which can see it, exactly as mob facing is.

A projectile is authored in its own catalog rather than borrowed from the item
catalog, because it is not something a character carries. Each entry names
three independent facets: a `silhouette` describing what is drawn and along
which axis, a `flight` describing how it travels, and an `impact` describing
what its arrival resolves against. Only the silhouette is an art-direction
input; the other two are consumer-owned names, and the generator excludes them
from the artwork's cache identity so retuning how an object moves regenerates
nothing. A projectile declares `length_units` rather than a height, because it
is drawn lying along its own travel axis.

Gameplay may require presentation and motion capabilities through explicit
references. It MUST NOT silently manufacture values absent from the current
authored contract.

### UI presentation

Root `ui.toml` owns game-global interface appearance, authored visual references,
generation prompts, layout identities, and alpha policies. It does not own
inventory capacity, contents, item behavior, input, or visibility state; those
remain gameplay semantics in `gameplay.toml`.

The current inventory-panel shape is defined by the
[Authored game UI contract](spec/game/ui.md). Future nine-slice or additional UI
roles extend that presentation contract without moving gameplay rules into it.

### Content catalogs

Maps and soundtracks are sibling contracts under the same game identity. A map
is one compound map-generation contract: it owns its image-reference closure,
view and continuity envelope, ordered layer plan, ground-generation mode,
the generated terrain request, the climbable roster, portal presentation
and endpoint anchors, and whole-map review unit. A soundtrack owns tracks.
Neither owns gameplay flow merely because the same consumer uses it.

`game.toml` catalogs the maps belonging to the package by exact source path.
`gameplay.toml` references them by durable `map_id`. The canonical current map
shape is the [Authored map-generation contract](spec/game/map-generation-contract.md).

### Consumer bindings

A consumer binding translates portable game contracts and generated manifests
into engine-native camera, scene, input, rendering, collision, and simulation
objects. The adapter may reject a profile it does not implement. It may not
redefine the profile or become its source of truth.

The optional web preview is one such consumer. Runtime behavior observed in web
does not by itself define a core game contract.

## Ownership boundaries

| Owner | Owns | Does not own |
| --- | --- | --- |
| Master game contract | Domain composition, shared identity, ownership, and cross-contract invariants | Field-level recipe schemas or engine behavior |
| Taxonomy specifications | Canonical terms and immutable profile definitions | Claims of recipe support |
| Core components | Provider-neutral contracts, validation, and deterministic media operations | Recipe genre, camera, or gameplay assumptions |
| Recipes | Generation-specific composition, supported profiles, artifacts, and semantic acceptance | Runtime camera controllers or engine scenes |
| Consumer adapters | Runtime translation, camera control, rendering, input, collision, and simulation | Canonical generation vocabulary |
| Web preview | Optional browser consumption and demonstration | Core contract authority or a second generator |

## Cross-contract invariants

1. **One term has one reference frame.** Camera pose, subject view, gameplay
   space, and screen direction are never collapsed into an unqualified label.
2. **Projection is not style.** Perspective, orthographic, and axonometric
   geometry are not rendering-medium keywords.
3. **Gameplay is not camera.** Navigation and collision domains are declared
   independently from how they are viewed.
4. **Assets declare compatibility.** A generated asset records the view,
   direction, style, proportion, and semantic motion contract it satisfies.
5. **Visible gameplay requires visual coverage.** Required actor states cannot
   exist only in simulation while their contracted 2D motion asset is absent.
6. **Sequence control is explicit.** Dialogue, branches, camera shots, actor
   blocking, player-agency changes, skips, and outcomes are authored semantics,
   not array-order or consumer-side inference.
7. **Map composition is not map usage.** A map owns referenced visual inputs,
   layer composition, binary terrain, climbable geometry and placement, portal
   presentation and anchors, ground direction, and review. Gameplay owns entry,
   movement permission, transition relationships, spawning, interactions, and
   other use of that map.
8. **Recipes fail before paid generation.** Unsupported profiles or incoherent
   cross-contract references are rejected during local resolution.
9. **Consumers fail closed.** A consumer requires the exact current contract
   identities and does not guess profile semantics, frame counts, or orientation
   behavior.
10. **Identifiers are portable and versioned.** Persisted fields use
   `lower_snake_case`; profile identifiers are opaque and explicitly versioned.
11. **Provenance follows semantics.** Contract and vocabulary changes invalidate
   reuse of assets they directed.
12. **Publication remains separate.** Contract validity and visual acceptance do
    not authorize generated-media publication.
13. **References are explicit.** Paid map generation consumes only image files
    explicitly bound by the map source, with exact digests and a documented
    rights basis. Directory presence and filename similarity never imply use.

## Current identity principles

- Authored sources and generated projections must match their exact current
  schema version and kind. Validators reject every other identity rather than
  upgrading or translating it.
- The current prepared closure uses repository selector `game-package-v4`, root
  `game-contract-v9`, `gameplay-contract-v1`, `game-ui-v4`, `game-map-v10`,
  `game-soundtrack-v1`, `player-content-v3`, V2 mob/prop/item catalogs, the
  optional `projectile-content-v2` catalog, `npc-content-v3`,
  `scenario-catalog-v1`, `scenario-v2`, `runner-gameplay-v4`,
  `runner-track-v4`, `runner-avatar-v3`, `runner-audio-v4`, and the optional
  `game-fx-v2` contracts.
  Provider-free
  integration emits `prepared-game-runtime-v12` for the platformer member
  and `sideview-runner-runtime-v13` for the runner member.
- Subsystems such as population, motion, scenarios, maps, and soundtrack
  catalogs retain independent current identities beneath the game identity.
- A new recipe capability adds declared profile support; it does not broaden an
  existing profile by implication.
- When a persisted shape changes, authored packages and generated projections
  must be updated or regenerated; adapters do not preserve obsolete schemas.
- Identity is exact-current; field presence is not. A field the current contract
  defines with a default may be absent from a projection carrying the current
  identity, and the consumer reads it at that declared default rather than
  guessing. A value that is present is validated in full, and an unrecognised
  field is still rejected.

## Subordinate authorities

| Contract | Authority |
| --- | --- |
| [Authored game contract schema](spec/game/authored-contract-schema.md) | Implemented current-only `game-contract-v9` package-root fields, vocabulary, validation, and binding |
| [Canonical game-generation pipeline](spec/game/generation-pipeline.md) | Machine-checked current scrolling DAG, stage and operation contracts, execution semantics, and separately labelled target evolution |
| [Authored map-generation contract](spec/game/map-generation-contract.md) | Exact-current `game-map-v10` references, layers, runtime presentation, binary terrain, map-local ladders and portals, validation, review, cache, and usage boundary |
| [Game view and style taxonomy](spec/game/view-and-style-taxonomy.md) | Proposed TO-BE terminology, profiles, and module namespace rules |
| [Dialogue and cutscene sequence contract](spec/game/dialogue-and-cutscene-sequences.md) | Proposed TO-BE dialogue graph, branching, shots, cues, control leases, skip/resume, and outcome semantics |
| [Case: the container above the narrative leaves](spec/game/case.md) | Exact-current `case-v1`, `case-catalog-v1` and the `case-runtime-v1` projection: the beat graph over scenarios and rooms, the declared fact namespace, the must-availability proof, and the leaf binding |
| [Screen FX: transitions and overlays](spec/game/fx.md) | Exact-current `game-fx-v2`: generated cut-in plates, the game-global moment vocabulary, the traced mask polygon a runtime draws, and the two host contracts |
| [Authored character library](character-library.md) | Durable character identity and character-source rights |
| [Authored game maps](game-maps.md) | Exact-current `game-map-v10` package placement, ownership summary, and runtime projection |
| [Authored game soundtracks](game-soundtrack.md) | Game-global track catalog and generation binding |
| [Sprite-sheet slicing and instance recovery](spec/sprite-sheet-processing.md) | Implemented alpha-component repacking default, known loss modes, and planned geometry and ownership recovery |
| [Generated-media publication](generated-media-publication.md) | Rights review and repository publication gates |

## Versioning discipline

Six rules, each written after the fifteen days that showed what its absence
costs. They govern every versioned document and every node type in the tree.

1. **Two words, never one.** A node type's `contract_version` is a cache key:
   it says whether paid work must be redone. A document's `schema_version` and
   `kind` are an identity: they say whether a consumer may read it. Neither is
   bumped to express the other.
2. **A paid node's `contract_version` moves only when its request moves** —
   prompt, size, references, provider, model. An acceptance criterion lives in
   the free validate node downstream and in the checkpoint's cache-admission
   callback, where tightening it costs exactly the artifacts that no longer
   pass. One validator change once redrew eleven layer images because it was
   expressed as a generate bump.
3. **Per-block versions in published manifests.** A runtime manifest is a set
   of named blocks, each carrying its own version; the document version moves
   on structural change only, and an unknown block version refuses that
   block's consumer rather than the run. Nine of the runner manifest's eleven
   bumps in two days touched one block.
4. **Additive optional fields bump nothing.** A new optional table or field
   is read by the consumer that wants it and ignored by the one that does
   not; it moves no version and drops no run.
5. **One authority per version string; documents derive.** A version literal
   lives in exactly one model and every mention elsewhere is generated or
   checked against it. The retired set is every version below the current
   one, computed, never listed by hand.
6. **Publish only what a consumer reads.** A field in a runtime manifest that
   no consumer parses is a defect, and the check is mechanical.

The rules apply forward. Where a shipped contract violates one today, the
violation is listed in `docs/plans/engineering-pass.md` with its price, and is
corrected when the family that owns the block lands.

The table of every current identity, with the module that declares each, is
generated into [contract-identities.md](contract-identities.md); the contract
test refuses a current document that cites any other version.

## Non-goals

This master contract does not:

- define a universal game-engine schema;
- make one recipe or web preview the definition of a game;
- claim that proposed presentation profiles are implemented;
- prescribe implementation order, milestones, or migration tasks;
- combine all game-owned data into one physical file; or
- replace field-level, recipe-level, media, rights, or consumer contracts.
