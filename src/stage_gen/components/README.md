# Asset capabilities

Components own bounded generation or processing capabilities. Recipes compose them; the public `stage_gen.pipeline` harness plans, executes, caches, and inspects those compositions. A component can expose several GNode nodes. It does not need a game package or a particular runtime.

| Capability | Public surface | Output or responsibility |
|---|---|---|
| Repeating images | `image_repeat.ImageRepeatService` | Explicit repeat admission or repair, with validation and lineage |
| Layered scenery | `sideview_layers.models.LayerRequest`, `sideview_layers.nodes` | Layer generation, repeat construction, and placement |
| Supplied-layer parallax | `sideview_layers.parallax`, `recipes.looping_parallax` | Repeating PNGs, portable composition metadata, and a scrolling preview |
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
| Optional narrative tooling | `scenario` | Script parsing, compilation, and proof; asset binding remains optional |

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

Existing fixed geometry remains useful as named presets. The 47-mask terrain atlas, four-frame motion strip, fixed UI glyph sheets, and local eye/mouth portrait pipeline do not claim to represent every terrain, animation, UI, or Live2D workflow. Authors can compose different capabilities or add their own nodes through the same harness.

Runnable examples live beside recipes. Start with `../recipes/looping_parallax/examples/supplied_layers/`: its small Python input generator produces original geometric layers without a provider, and its `pipeline.py` runs through the standard authoring harness. Inspecting or scrolling the result requires no game definition.
