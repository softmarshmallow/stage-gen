# Components

A component is an independently testable capability under `src/stage_gen/components/`: node
types, graph fragments (`add_*_nodes`), contracts and services. It never runs alone and never
imports a workflow. Workflows compose components; the SDK, `stage_gen.pipeline`, plans,
executes, caches and inspects those compositions. A component can expose several GNode nodes,
and it does not need a game package or a particular runtime.

## Capabilities

| Capability | Public surface | Output or responsibility |
|---|---|---|
| Repeating images | `image_repeat.ImageRepeatService` | Explicit repeat admission or repair, with validation and lineage |
| Layered scenery | `sideview_layers.models.LayerRequest`, `sideview_layers.nodes` | Layer generation, repeat construction, and placement |
| Supplied-layer parallax | `sideview_layers.parallax`, `workflows.looping_parallax` | Repeating PNGs, portable composition metadata, and a scrolling preview |
| Character identity | `character_profile.CharacterProfile` | Optional visual identity, expressions, and referenced artwork |
| Sprite playback/coherence | `actor_content.MotionPresentation`, `sideview_actor` | Frames, anchors, source extent, caller-defined visual scale, cross-state coherence |
| Fixed portrait motion | `portrait_motion` | Local eye/mouth patches, registration, review, and diagnostic playback |
| Terrain | `sideview_terrain`, `painted_terrain` | Mask-driven atlas or occupancy-conditioned painting |
| Structural terrain painting | `painted_terrain.structural_ground` | Occupancy-preserving paintings and compatible segment seams |
| Interface art | `ui_art.UiArt`, `ui_art.nodes` | Individually selected nine-slice, icon, cursor, or panel presets |
| Effects art | `effects_art.EffectsArt`, `effects_art.nodes` | Cut-in plates, masks, placement, and dust atlases; no event bindings |
| Screen pictures | `screen_art.ScreenPlateRequest` | One image with explicit geometry and optional reserved regions |
| Music | `music.MusicTrack`, `music.nodes` | One generated track or a caller-selected collection; no playlist policy |
| Voice identity | `voice_profile.VoiceProfile` | Casting, rights, and explicit provider voice binding |
| Sound effects | `sound_effect.SoundEffectRequest` | One effect asset or pinned take; gameplay response is separate |
| Speech | `speech.SpeechRequest` | One line and admission budget with a caller-owned voice binding |
| Audio processing | `audio_normalization.FfmpegAudioNormalizer` | Measured and validated loudness normalization |
| Video inspection | `video_clip` | Caller-specified size, codec, duration, and optional aspect constraints |
| Spatial generation | `worldgen` | Caller-defined fields, point processes, masks, and placements |
| Optional domain design | `sideview_map_design` | Profile-constrained tile-layout generation and diagnostics |

UI artwork can request just one role:

```python
from stage_gen.components.ui_art import UiArt
from stage_gen.components.ui_art.nodes import document_roles

request = UiArt(references=[style_reference], panel_frame=panel_direction)
assert [role.role for role in document_roles(request)] == ["panel_frame"]
```

Effect images do not require a stage or encounter event:

```python
from stage_gen.components.effects_art import EffectsArt
from stage_gen.components.effects_art.models import DustAtlasDirection, SpriteDirection

request = EffectsArt(
    sprite=SpriteDirection(
        dust=DustAtlasDirection(
            layout="fx_dust_atlas_1024x1024_v1",
            alpha_policy="transparent_exterior_v1",
            prompt="Warm clay particles with soft painted edges",
        )
    )
)
```

Music, speech, and sound requests describe assets. Gain, event-strength pitch changes, death/restart routing, and playlist selection belong to consumer playback configuration. The named Godot games own their corresponding models and preparation packages; shared soundtrack binding lives in `demo_game_tools`. These optional game packages are not product dependencies.

`AssetScale(target_pixels_per_unit=80.0)` defines a visual ruler without choosing a player, tile size, or camera controller. Sprite measurement and calibration use that ruler; a game can derive it from its own units in its adapter.

Existing fixed geometry remains useful as named presets. The 47-mask terrain atlas, four-frame motion strip, fixed UI glyph sheets, and local eye/mouth portrait pipeline do not claim to represent every terrain, animation, UI, or Live2D workflow. Authors can compose different capabilities or add their own nodes through the same SDK.

Runnable inputs live beside workflows. Start with [`../workflows/looping_parallax/inputs/supplied_layers/`](../workflows/looping_parallax/inputs/supplied_layers/): its small Python input generator produces original geometric layers without a provider, and its `pipeline.py` runs through the SDK. Inspecting or scrolling the result requires no game definition.

## Contract

A Stage Gen component is an independently testable application capability under
`src/stage_gen/components/`, such as sprite-sheet processing, soundtrack assembly,
or an authored game contract. Components use the provider-neutral modality services
exported from `gnode`: image generation, background removal, structured generation,
and music generation live in ring 1 under `src/gnode/modalities/`. Provider adapters
live in ring 2. See the [gnode rings](../../../docs/spec/gnode-rings.md) for their import boundaries.

Shared, workflow-neutral media inspection and transforms live under
`src/stage_gen/media/`; capability-specific processing stays with its component,
and workflow-specific canonicalization stays with its workflow. A workflow composes
components into a graph; a runtime or preview consumes its artifacts.

### Required properties

Artifact-producing components must:

1. accept typed or schema-validated input;
2. write only below the caller-provided output directory;
3. return an artifact manifest rather than relying on implicit filenames;
4. validate media before reporting success;
5. use one retry owner per provider operation, with at most six attempts
   (one initial attempt plus five retries) and capped backoff;
6. include silent contract failures such as empty media or malformed JSON
   within that same retry boundary;
7. persist provenance and a content hash beside the artifact;
8. make deterministic post-processing explicit and independently testable;
9. support cancellation/timeouts without leaving a success marker; and
10. expose enough information for a headless benchmark.

When a component uses a gnode modality service, that service owns provider retries;
the component and provider adapter must not add nested retry loops.

### Structure

The properties above say what a component does; this says what one looks like, so
that a reader who has seen one has seen them all. A component is a package under
`src/stage_gen/components/` whose `__init__.py` exports its surface in `__all__`,
holding:

- `models.py` — the authored contract: the pydantic models and the vocabulary they
  close over, with their persisted `kind` and version literals;
- `loader.py` and `library.py` where the component reads authored files or resolves a
  library binding;
- one or more node-family modules, `nodes.py` or `<family>_nodes.py`, each holding a
  family's `NodeType` declarations (with `<family>_node_types(identity_prefix=…)` when
  a graph shipped the family under its own type ids), an `add_<family>_nodes` graph
  helper that declares the nodes and their ports over a builder, and a
  `<Family>Handlers` kit over a `<Family>Host` that a workflow or game graph binds into its own node
  handler - the soundtrack, motion-rebase, layer, UI atlas, inventory-panel and cut-in
  families are the shape;
- private helpers as `_<name>.py`, shared across components through
  `components/_node_kit.py` and its siblings rather than copied.

A component imports the engine, `stage_gen.media`, `stage_gen.canonical` and other
components; never a workflow, a game, the orchestration layer or a provider. Workflows and
game graphs host node families; they do not own node semantics. Two departures stand today and are named in
the conformance test so they cannot silently multiply: `painted_terrain/nodes.py`
declares its four types but its graph helper and handlers still live in the Bellweather
platformer graph (workstream D9), and `game_fx/sprite_nodes.py` exposes request builders rather
than a handler kit because the runner drives its retries.

### Independence rule

The reusable contract does not assume a genre, camera, engine, coordinate
system, movement model, combat model, or gameplay loop. Those may be explicit
inputs to a specialized workflow, but they are never ambient global state.

For example, a sprite-sheet component may accept `{ rows, columns, anchors }`.
It must not silently assume that row 2 is a jump animation. A depth-layer
component may accept a requested projection and loop axis. It must not assume a
horizontal follow camera because one preview happens to use one.

The provider-neutral recovery, crop, and packing boundary is specified by the
[sprite-sheet slicing and instance-recovery contract](../../../docs/spec/sprite-sheet-processing.md).
The Python core implements its minimal alpha-component repacker; generic grid detection and
semantic ownership recovery remain planned. The contract does not reserve workflow or consumer
behavior inside reusable components.

Components must not import `web/`. The viewer and the site consume exported manifests and
examples; they never reach into a component.

## Artifact result

A successful result should provide this information, directly or through a
manifest. This offline example constructs only an in-memory result record with
illustrative paths, digest, and media facts. It does not generate, validate, or
persist an artifact:

```python
from gnode import ArtifactResult

result = ArtifactResult(
    component="image-generation",
    artifact_path="out/concept.png",
    provenance_path="out/concept.png.meta.json",
    media_type="image/png",
    sha256="0" * 64,
    bytes=1,
    attempts=1,
    validation={"width": 1, "height": 1},
)
```

Image dimensions, audio duration, channel count, or other media-specific facts
belong in `validation`. Never infer success from HTTP 200 alone.

## Failure contract

Failures distinguish provider/transport errors, response-contract failures,
input validation errors, and deterministic post-processing failures. Error
messages may name environment variables but must never include credential
values or full authorization headers.

Partial outputs may remain for debugging only when clearly marked incomplete.
They must not satisfy skip-if-exists or cache checks.
