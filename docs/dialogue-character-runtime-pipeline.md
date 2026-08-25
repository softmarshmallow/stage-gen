# Dialogue character runtime pipeline

The dialogue-scene recipe and the scrolling-preview recipe remain independent
producers. A reviewed, character-only dialogue bundle is their explicit
composition seam. The scrolling game never reads another run directory at
runtime, and the browser does not define the reusable contract.

This pipeline imports only the full-body character expression images and the
ordered dialogue beats. It does not import or render a dialogue-scene
background.

## Roles and responsibilities

| Name | Owner | Responsibility |
| --- | --- | --- |
| Authored game contract | `game.toml` and the game-contract component | Own durable game direction, cast identity, camera, and render profiles. It does not point at generated run files. |
| Scrolling producer | `scrolling-preview` recipe | Generate the scrolling run, its village manifest, and the resident identity artifact that a later import must match. |
| Dialogue producer | `dialogue-scene` recipe | Generate a standalone scene run and character-only expression assets. It remains independently demoable. |
| Edge sanitizer | Provider-neutral `media` transform, invoked by dialogue canonicalization | Remove only transparency-connected hot-magenta edge pixels after chroma or AI/FAL alpha derivation. It preserves the original assets, records exact transform facts, and leaves review pending. |
| Character bundle packager | `dialogue-scene` recipe | Validate the character-only spike and publish the portable `dialogue-character-bundle-v1` contract with locked expression states and provenance bindings. |
| Independent semantic reviewer | Review boundary outside the producer | Accept the exact bundle and exact asset digests for restricted local-demo use. Review does not authorize publication. |
| Scrolling character binder | `scrolling-preview` recipe | Verify the reviewed bundle against one resident slot and identity digest, copy content-addressed assets across the run boundary, and project `dialogue_characters` into the current scrolling manifest V7. Every other envelope version is rejected. |
| Manifest consumer | `web/lib/runtime/` | Strictly parse the lower-snake-case public contract, verify each PNG digest, byte count, dimensions, and alpha, then translate into runtime-native names. |
| Dialogue presentation | Phaser `DialogueBox` | Own screen-fixed portrait, text, expression changes, interaction, and movement gating. It does not generate assets or weaken import checks. |
| Playability verifier | Production browser workflow | Drive the player to the bound resident, traverse every beat, check movement lock and resume, collect diagnostics, and capture the rendered canvas. |

## Dependency topology

Arrows point from a consumer to the contract or module it depends on:

```text
production playability verifier
  -> Phaser dialogue presentation
     -> strict web manifest consumer
        -> composed scrolling run manifest V7

scrolling character binder
  -> reviewed dialogue-character bundle
  -> scrolling run manifest V7 and resident identity artifact

reviewed dialogue-character bundle
  -> independent review record and acceptance specification
  -> pending dialogue-character bundle

pending dialogue-character bundle
  -> sanitized dialogue-scene character-only run

dialogue-scene canonicalization and sanitize transition
  -> provider-neutral media edge transform

scrolling-preview producer
  -> authored game contract

dialogue-scene producer
  -> source character identity artifact
```

The data flow is one-way:

```text
character-only assets
  -> deterministic edge sanitization
  -> pending portable bundle
  -> digest-bound independent review
  -> resident-identity verification and content-addressed import
  -> composed scrolling manifest V7
  -> verified browser textures
  -> screen-fixed cutscene overlay
```

There is no import from Python into `web/`, no import from the dialogue recipe
into the scrolling recipe, and no runtime reference from the scrolling run
back into the dialogue run. The binder is the composition root between the two
recipe-owned contracts.

## Why binding precedes gameplay

The browser asset route serves one confined file from one completed run. A
path into a sibling run would be non-portable, bypass the run's provenance,
and enlarge the route's filesystem authority. The binder therefore copies the
four reviewed PNGs into the scrolling run under names derived from their
SHA-256 digests and writes portable import provenance before updating the
manifest atomically.

Binding must fail closed when any of these checks fail:

- the bundle or review provenance does not match its artifact bytes and media
  type;
- review is absent, belongs to a different bundle or acceptance specification,
  or authorizes anything beyond restricted local-demo use;
- the target NPC slot, name, or source identity digest differs from the bundle;
- a source image differs in digest, byte count, media type, dimensions, alpha,
  or locked expression state;
- a destination filename already contains different bytes;
- the existing manifest already contains a different dialogue-character
  projection.

An identical repeated bind is idempotent. When `dialogue_characters` is absent
from a valid manifest V7, the binder adds the current projection. A declared but
malformed dialogue block is rejected as a whole; the consumer must not mix a
partially accepted portrait set into gameplay.

## Current integration choice

The correct immediate integration is package, review, then bind through the
headless Python interface. A Node plugin system is not a prerequisite and
would put the contract in the wrong owner. A future automated game build may
invoke the same binder as a composition stage and persist its input digests,
but `game.toml` should continue to own durable direction rather than local
generated paths.

For an existing unreviewed character-only spike, the headless transition order
is:

```text
dialogue-character sanitize
  -> dialogue-character package
  -> dialogue-character review
  -> dialogue-character bind
```

Dialogue-scene canonicalization invokes the same provider-neutral edge transform
automatically after either chroma transparency or AI/FAL alpha composition. The
explicit sanitize command remains available for pending manual inputs; it
refuses to run after package or review outputs exist, so a review can never
silently drift to different image bytes.

The standalone dialogue-scene demo remains useful for producer development and
semantic review. Gameplay consumes only the reviewed portable projection, so
either side can evolve behind that contract without becoming the other side's
implementation dependency.
