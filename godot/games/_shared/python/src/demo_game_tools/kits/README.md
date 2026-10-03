# Game kits

What several games prepare alike, owned by no single game: the contracts, prompts,
validators and composition one kind of game asset needs. The asset product never imports
these kits; the games under `godot/games/` and their shared preparation code do.

| Kit | Public surface | Output or responsibility |
|---|---|---|
| Character identity | `character_profile.CharacterProfile` | Optional visual identity, expressions, and referenced artwork |
| Sprite playback/coherence | `actor_content.MotionPresentation`, `sideview_actor` | Frames, anchors, source extent, caller-defined visual scale, cross-state coherence |
| Terrain | `sideview_terrain`, `painted_terrain` | Mask-driven atlas or occupancy-conditioned painting |
| Structural terrain painting | `painted_terrain.structural_ground` | Occupancy-preserving paintings and compatible segment seams |
| Interface art | `ui_art.UiArt`, `ui_art.nodes` | Individually selected nine-slice, icon, cursor, or panel presets |
| Effects art | `effects_art.EffectsArt`, `effects_art.nodes` | Cut-in plates, masks, placement, and dust atlases; no event bindings |
| Screen pictures | `screen_art.ScreenPlateRequest` | One image with explicit geometry and optional reserved regions |
| Music | `music.MusicTrack`, `music.nodes` | One generated track or a caller-selected collection; no playlist policy |
| Voice identity | `voice_profile.VoiceProfile` | Casting, rights, and explicit provider voice binding |
| Spatial generation | `worldgen` | Caller-defined fields, point processes, masks, and placements |
| Optional domain design | `sideview_map_design` | Profile-constrained tile-layout generation and diagnostics |

UI artwork can request just one role:

```python
from demo_game_tools.kits.ui_art import UiArt
from demo_game_tools.kits.ui_art.nodes import document_roles

request = UiArt(references=[style_reference], panel_frame=panel_direction)
assert [role.role for role in document_roles(request)] == ["panel_frame"]
```

Effect images do not require a stage or encounter event:

```python
from demo_game_tools.kits.effects_art import EffectsArt
from demo_game_tools.kits.effects_art.models import DustAtlasDirection, SpriteDirection

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

`AssetScale(target_pixels_per_unit=80.0)` defines a visual ruler without choosing a player,
tile size, or camera controller. Sprite measurement and calibration use that ruler; a game can
derive it from its own units in its adapter.

Fixed geometry stays useful as named presets: the 47-mask terrain atlas, the four-frame motion
strip and the fixed UI glyph sheets do not claim to represent every terrain, animation or UI.
