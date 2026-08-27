# Dialogue character runtime pipeline

> **Contract maturity: exact-current prepared-package path.**

Prepared games author NPC visual identity in `content/npcs.toml` and dialogue
control flow in `sequences/*.toml`. Those sources are resolved together before
generation, generated inside one immutable run, and projected into
`prepared-game-runtime-v4`. The browser never reaches into a sibling run or
invents missing dialogue.

## Ownership

| Owner | Responsibility |
| --- | --- |
| `game.toml` | Catalog NPC identities and digest-lock content plus the sequence catalog |
| `content/npcs.toml` | NPC concept reference, runtime motion/expression requests, playback selection, and visual rights |
| `sequences/index.toml` | Catalog and digest-lock sequence sources |
| `sequences/<sequence_id>.toml` | Speakers, nodes, authored text, expressions, control flow, effects, and outcomes |
| Prepared-package resolver | Validate IDs, expressions, targets, reachability, effects, and complete source/reference closure |
| Scrolling recipe | Generate NPC concepts and state sheets, recover canonical frames, review the NPC catalog, and integrate artifacts |
| Prepared manifest | Publish digest-bound NPC states and the resolved sequence graph as one portable runtime closure |
| Web consumer | Validate the exact manifest, load declared textures, run interaction/sequence state, and render dialogue |

The sequence owns what is said and which expression is requested. NPC content
owns how that expression looks. Neither copies the other’s authored data.

## Dependency topology

```text
game.toml
  -> content/npcs.toml
     -> NPC concept generation
        -> per-NPC motion/expression generation
           -> canonical frame recovery
              -> NPC catalog review
  -> sequences/index.toml
     -> sequences/<sequence_id>.toml

NPC catalog review + resolved sequences + all other asset branches
  -> provider-free integration
     -> prepared-game-runtime-v4
        -> strict prepared web consumer
           -> interaction prompt and dialogue presentation
```

All independent NPC concepts and sheets are scheduled subject only to their
declared dependencies. Sequence resolution is local and does not wait for image
generation. Integration is the first point where the complete visual and
narrative closure meet.

## Resolution invariants

Before a provider operation, the package resolver rejects:

- an NPC cast ID absent from the NPC catalog;
- duplicate NPC, motion, expression, node, outcome, or sequence IDs;
- an unknown speaker or requested expression;
- an unreachable node or missing branch target;
- an effect, item, quest, map, or outcome reference outside the package;
- a sequence source or visual reference whose digest changed; and
- an orphaned or implicit package file.

The recipe does not generate replacement dialogue or silently substitute an
unrelated expression. Incomplete generated presentation can be diagnosed by a
consumer, but malformed authored semantics fail before paid work.

## Runtime behavior

The prepared consumer exposes an interaction prompt only for a nearby NPC with
a resolvable authored sequence. Starting the sequence leases player movement,
advances through its authored nodes, selects the requested NPC expression, and
applies declared outcomes/effects through gameplay state. Exiting returns
control deterministically.

NPCs without a dialogue binding remain ordinary world actors and do not show a
misleading interaction prompt. A malformed declared sequence is a hard manifest
error, not a signal to synthesize text at runtime.

## Evidence boundary

Structural validation proves that images decode, canonical frames exist,
identities resolve, and runtime bytes are complete. Semantic review separately
judges whether generated expressions and motion states visually match their
authored intent. Publication still requires its own authorization.

See [Dialogue and cutscene sequences](spec/game/dialogue-and-cutscene-sequences.md)
for graph semantics and [Canonical game-generation pipeline](spec/game/generation-pipeline.md)
for the executable asset fan-out.
