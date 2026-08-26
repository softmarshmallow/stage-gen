# Game contract

> **Contract maturity: proposed TO-BE master.**
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

This naming also keeps the contract distinct from `WorldSpec` and
`world_spec_<tag>.json`, which already mean the generated bible for one
scrolling stage.

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
├── presentation
│   ├── view profile
│   │   ├── scene dimensionality and projection
│   │   ├── camera pose and behavior envelope
│   │   ├── gameplay space and depth policy
│   │   └── asset-view requirements
│   └── style profile
│       ├── rendering construction
│       ├── art direction
│       └── measurable visual properties
├── cast
│   ├── player roles
│   ├── mob roles
│   └── resident and dialogue roles
├── motion
│   ├── locomotion
│   ├── action
│   ├── reaction
│   └── terminal states
├── sequences
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
├── soundtrack.toml
├── maps/
│   └── <map_id>.toml
└── sequences/
    ├── index.toml
    └── <sequence_id>.toml
```

`game_id` is durable and machine-readable. Display names are presentation text
and do not determine identity. Every authored source is independently
canonicalized and digest-bound so editing a soundtrack or map does not silently
change the identity of unrelated game direction.

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

Gameplay contracts own semantic simulation rules: navigation, interaction,
combat, population, and other systems. They describe what must happen without
embedding a particular engine's object graph or update loop.

Gameplay may require presentation and motion capabilities through explicit
references. It MUST NOT silently manufacture values absent from the current
authored contract.

### Content catalogs

Maps and soundtracks are sibling contracts under the same game identity. A map
owns durable map identity and references to allowed game-global content. A
soundtrack owns tracks. Neither becomes an unstructured extension table inside
`game.toml` merely because the same consumer uses it.

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
7. **Mechanism coverage composes exactly.** A map that requires a managed
   mechanism has exactly one matching game-owned policy entry; missing or
   unexpected entries are rejected rather than approximated.
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

## Current identity principles

- Authored sources and generated projections must match their exact current
  schema version and kind. Validators reject every other identity rather than
  upgrading or translating it.
- The current closure is `game-contract-v3`, `game-soundtrack-v1`,
  `game-map-book-v1` containing only `game-map-v2` sources, and scrolling
  manifest V7 with soundtrack and map-book projection V2.
- Subsystems such as population, motion, sequences, maps, and soundtrack
  catalogs retain independent current identities beneath the game identity.
- A new recipe capability adds declared profile support; it does not broaden an
  existing profile by implication.
- When a persisted shape changes, authored packages and generated projections
  must be updated or regenerated; adapters do not preserve obsolete schemas.

## Subordinate authorities

| Contract | Authority |
| --- | --- |
| [Authored game contract schema](spec/game/authored-contract-schema.md) | Implemented current-only `game-contract-v3` fields, vocabulary, validation, binding, and manifest V7 projection |
| [Canonical game-generation pipeline](spec/game/generation-pipeline.md) | Machine-checked current scrolling DAG, stage and operation contracts, execution semantics, and separately labelled target evolution |
| [Game view and style taxonomy](spec/game/view-and-style-taxonomy.md) | Proposed TO-BE terminology, profiles, and module namespace rules |
| [Dialogue and cutscene sequence contract](spec/game/dialogue-and-cutscene-sequences.md) | Proposed TO-BE dialogue graph, branching, shots, cues, control leases, skip/resume, and outcome semantics |
| [Authored character library](character-library.md) | Durable character identity and character-source rights |
| [Authored game maps](game-maps.md) | Map identity, ordering, and map-owned references |
| [Authored game soundtracks](game-soundtrack.md) | Game-global track catalog and generation binding |
| [Sprite-sheet processing](spec/sprite-sheet-processing.md) | Planned provider-neutral grid detection, extraction, alignment, and packing |
| [Generated-media publication](generated-media-publication.md) | Rights review and repository publication gates |

## Non-goals

This master contract does not:

- define a universal game-engine schema;
- make one recipe or web preview the definition of a game;
- claim that proposed presentation profiles are implemented;
- prescribe implementation order, milestones, or migration tasks;
- combine all game-owned data into one physical file; or
- replace field-level, recipe-level, media, rights, or consumer contracts.
