# Actor Halo / Outer Glow

`actor_halo.gd` renders a soft colored glow outside a transparent actor's alpha
silhouette. It is a separate, padded `TextureRect` behind the host's original
sprite. The original texture, color, shader, and alpha remain untouched. Dark
eyes, costume seams, and other RGB details do not become glow edges. Transparent
holes in the silhouette can admit glow; an opaque rectangular image cannot
provide a character silhouette.

This is an actor-local presentation effect, distinct from a location lens flare,
screen bloom, a halo ring graphic, and ambient particles. For example, warm Outer
Glow can separate a softly cropped close-up from an indoor background while a
Camera Drift moves the entire shot. It does not generate lighting within the art.

## Contract

```gdscript
const ActorHalo = preload("res://addons/game_presentation/effects/actor_halo.gd")
var halo = ActorHalo.new()
actor_layer.add_child(halo) # Before the original sprite, under the same crop/camera parent.
halo.configure({"color": Color(1.0, 0.78, 0.55, 0.8), "radius": 28.0, "intensity": 1.1})
halo.set_source(character_texture)
halo.set_rect(character_display_rect)
halo.set_strength(0.8)
```

| API | Input and result |
| --- | --- |
| `configure(settings)` | Partial dictionary; returns `Array[String]` errors. Keys are `color` (`Color`, finite RGBA in 0–1), `radius` (0–128 logical pixels), and `intensity` (0–4). Invalid input is atomic. Defaults: warm color `(1, .79, .57, .8)`, radius 24, intensity 1. |
| `set_source(texture)` | Full `Texture2D`; null removes the visible source. Treat an atlas region as a separate extracted texture before binding. |
| `set_rect(rect)` | Full source texture's actual displayed rectangle, in parent-local coordinates, with finite positive size. Returns errors without mutation for invalid geometry. The host resolves aspect-fit layout first. |
| `set_strength(value)` | Finite 0–1 strength; returns errors without mutation. The host owns any tween, pause, or elapsed time. |
| `get_settings()`, `get_source_rect()`, `get_strength()` | Read current configuration/binding/strength; settings are a copy. |
| `clear()` | Removes source and rectangle, keeping configuration and strength for reuse. |

There is no processing, completion signal, scene ownership, UI, camera dependency,
or persistent state format. Two instances own separate materials and settings.
Settings apply immediately. Zero strength, radius, intensity, or color alpha hides
the effect; a missing texture or rectangle also hides it. `configure`,
`set_source`, `set_rect`, and `set_strength` recompute this visibility. If the host
temporarily hides the actor, hide its shared parent rather than relying on a
manual `halo.visible = false` that a later binding update would overwrite.

The adapter expands the original rectangle by `radius + 2` on every side and
remaps UVs within it. The halo therefore reaches beyond the original sprite quad
without a clipped rectangle. Out-of-source samples return zero instead of
smearing texture-edge pixels. Radius is measured in logical parent units;
parent/camera/window scaling scales sprite and halo together. No low-resolution
offscreen buffer or full-screen bloom is involved. The shader uses a bounded
48-tap approximation near transparent pixels and skips opaque interiors.

The host owns sibling ordering, matching actor visibility/modulation, crop parent,
and camera transform. A parent's `clip_contents` deliberately clips both layers;
allow enough parent bounds if the glow should spill outside a crop. For a shader
that fades only the original sprite's pixels (rather than its common parent),
also drive halo strength from that fade to avoid a detached glowing silhouette.

## Verification

`Godot --headless --path godot/games/playground --script res://qa/actor_halo_checks.gd`
checks atomic validation, padded layout, logical scaling, isolated materials, and
reset. A rendering run without `--headless` additionally checks alpha-derived
glow outside the source quad, invisible interiors, RGB-edge independence, and
parent clipping using synthetic textures and a native `SubViewport`.
