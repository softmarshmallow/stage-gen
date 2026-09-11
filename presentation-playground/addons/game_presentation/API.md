# Canary API inventory

Version: **0.1.0-canary.1**. Script paths below are relative to this addon.
Public method signatures are listed verbatim; their source owns validation,
defaults and sample field definitions. Underscore-prefixed helpers are private.
This inventory does not imply that all components implement the same lifecycle.

## actors/actor_focus.gd

[Source](actors/actor_focus.gd). Base: `RefCounted`.

```gdscript
func initialize(actor_ids: Array[String], catalog_path: String) -> Array[String]:
func configure(selected_preset_id: String) -> Array[String]:
func set_focus(actor_id: String, animate: bool = true) -> Array[String]:
func replay() -> void:
func clear() -> void:
func advance(delta: float) -> void:
func sample(actor_id: String) -> Dictionary:
func get_presets() -> Array[Dictionary]:
```

## actors/cast_transition.gd

[Source](actors/cast_transition.gd). Base: `RefCounted`.

```gdscript
func initialize(actor_ids: Array[String], exit_catalog_path: String, spec_path: String) -> Array[String]:
func configure(settings: Dictionary) -> Array[String]:
func start() -> Array[String]:
func reset() -> void:
func advance(delta: float) -> void:
func sample(actor_id: String) -> Dictionary:
func is_busy() -> bool:
func get_settings() -> Dictionary:
func get_state() -> Dictionary:
```

## actors/character_exit.gd

[Source](actors/character_exit.gd). Base: `RefCounted`.

```gdscript
func initialize(actor_ids: Array[String], catalog_path: String) -> Array[String]:
func configure(selected_preset_id: String) -> Array[String]:
func exit_actor(actor_id: String) -> Array[String]:
func show_actor(actor_id: String) -> Array[String]:
func clear() -> void:
func advance(delta: float) -> void:
func sample(actor_id: String) -> Dictionary:
func is_visible(actor_id: String) -> bool:
func is_exiting(actor_id: String) -> bool:
func get_presets() -> Array[Dictionary]:
func get_state() -> Dictionary:
```

## actors/manpu_animation.gd

[Source](actors/manpu_animation.gd). Base: `RefCounted`.

```gdscript
func initialize(catalog_path: String) -> Array[String]:
func configure(selected_preset_id: String) -> Array[String]:
func sync(cues: Array, animate: bool = true) -> Array[String]:
func advance(delta: float) -> void:
func sample(actor: String, id: String) -> Dictionary:
func sample_with(actor: String, id: String, sampler: Callable) -> Dictionary:
func emit_one_shot(actor: String, id: String, selected_preset: String) -> Dictionary:
func one_shots() -> Array[Dictionary]:
func cancel_one_shots(actor: String = "") -> void:
func clear() -> void:
func replay(actor: String = "", id: String = "") -> Array[String]:
func get_presets() -> Array[Dictionary]:
func get_state() -> Dictionary:
```

## audio/text_reveal_audio.gd

[Source](audio/text_reveal_audio.gd). Base: `Node`.

```gdscript
func configure(settings: Dictionary = {}) -> Array[String]:
func begin(text: String, voice: AudioStream = null, visible_characters: int = 0, resume_voice_seconds: float = 0.0) -> void:
func update_reveal(visible_characters: int, delta: float, audible: bool = true) -> void:
func sync_reveal(visible_characters: int) -> void:
func set_paused(paused: bool) -> void:
func stop() -> void:
func get_state() -> Dictionary:
static func create_default_typing_stream() -> AudioStreamWAV:
```

## audio/voice_effects.gd

[Source](audio/voice_effects.gd). Base: `Node`.

```gdscript
func configure(settings: Dictionary = {}) -> Array[String]:
func get_output_bus() -> StringName:
func set_bypassed(value: Variant) -> Array[String]:
func set_strength(value: Variant) -> Array[String]:
func reset() -> void:
func cleanup() -> void:
func get_state() -> Dictionary:
```

## camera/camera_drift.gd

[Source](camera/camera_drift.gd). Base: `RefCounted`.

```gdscript
func start(settings: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func sample() -> Dictionary:
func is_active() -> bool:
func clear() -> void:
func get_state() -> Dictionary:
func restore(saved: Dictionary) -> Array[String]:
static func can_cover(base_background: Rect2, viewport_size: Vector2) -> bool:
static func constrain_offset(base_background: Rect2, viewport_size: Vector2, offset: Vector2) -> Vector2:
```

## camera/dialogue_camera.gd

[Source](camera/dialogue_camera.gd). Base: `RefCounted`.

```gdscript
func initialize(viewport_size: Vector2, background_rect: Rect2) -> Array[String]:
func focus(actor_id: String, world_point: Vector2, screen_anchor: Vector2, zoom: float, duration_seconds: float = 0.7) -> Array[String]:
func wide(duration_seconds: float = 0.7) -> Array[String]:
func clear() -> void:
func advance(delta: float) -> void:
func is_moving() -> bool:
func sample() -> Dictionary:
func get_state() -> Dictionary:
func restore(saved: Dictionary) -> Array[String]:
```

## camera/establishing_shot.gd

[Source](camera/establishing_shot.gd). Base: `RefCounted`.

```gdscript
func configure(settings: Dictionary) -> Array[String]:
func start(location_id: String, overrides: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func skip() -> void:
func clear() -> void:
func is_active() -> bool:
func get_settings() -> Dictionary:
func get_state() -> Dictionary:
func restore(saved: Dictionary) -> Array[String]:
func sample() -> Dictionary:
```

## camera/impact_shake.gd

[Source](camera/impact_shake.gd). Base: `RefCounted`.

```gdscript
func start(settings: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func sample() -> Dictionary:
func is_active() -> bool:
func clear() -> void:
func compose(base: Transform2D, background: Rect2, viewport: Vector2) -> Transform2D:
static func can_compose(base: Transform2D, background: Rect2, viewport: Vector2) -> bool:
func get_state() -> Dictionary:
func restore(saved: Dictionary) -> Array[String]:
```

## camera/walking_approach.gd

[Source](camera/walking_approach.gd). Base: `RefCounted`.

```gdscript
func initialize(viewport_size: Vector2, background_rect: Rect2) -> Array[String]:
func configure(partial_settings: Dictionary) -> Array[String]:
func start(overrides: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func is_active() -> bool:
func sample() -> Dictionary:
func skip() -> void:
func clear() -> void:
func get_settings() -> Dictionary:
func get_state() -> Dictionary:
func restore(saved: Dictionary) -> Array[String]:
```

## content/local_content.gd

[Source](content/local_content.gd). Base: `RefCounted`.

```gdscript
func configure(root: String = "res://", backend: String = "resources") -> Array[String]:
func get_settings() -> Dictionary:
func resolve(relative_path: String) -> Dictionary:
func read_bytes(relative_path: String) -> Dictionary:
func read_json(relative_path: String) -> Dictionary:
func load_texture(relative_path: String, mipmaps: bool = false) -> Dictionary:
func load_audio(relative_path: String, expected_sha256: String = "") -> Dictionary:
func load_video(relative_path: String) -> Dictionary:
```

## effects/actor_halo.gd

[Source](effects/actor_halo.gd). Base: `TextureRect`.

```gdscript
func configure(settings: Dictionary) -> Array[String]:
func set_source(source: Texture2D) -> void:
func set_rect(source_rect: Rect2) -> Array[String]:
func set_strength(strength: float) -> Array[String]:
func get_strength() -> float:
func get_settings() -> Dictionary:
func get_source_rect() -> Rect2:
func clear() -> void:
```

## effects/ominous_corruption.gd

[Source](effects/ominous_corruption.gd). Base: `Control`.

```gdscript
func configure(options: Dictionary) -> Array[String]:
func set_source(source: Texture2D) -> void:
func set_rect(rect: Rect2) -> Array[String]:
func set_pattern_transform(pattern_to_parent: Transform2D) -> Array[String]:
func reset_pattern_transform() -> void:
func get_pattern_transform() -> Transform2D:
func set_time(seconds: float) -> Array[String]:
func set_strength(value: float) -> Array[String]:
func clear() -> void:
func get_settings() -> Dictionary:
func get_source() -> Texture2D:
func get_source_rect() -> Rect2:
func get_strength() -> float:
func get_time() -> float:
```

## effects/particles/ambient_particles.gd

[Source](effects/particles/ambient_particles.gd). Base: `Control`.

```gdscript
func start(region: Rect2, textures: Array[Texture2D], options: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> Array[String]:
func seek(elapsed: float) -> Array[String]:
func stop() -> void:
func clear() -> void:
func set_textures(textures: Array[Texture2D]) -> Array[String]:
func present(camera: Transform2D) -> Array[String]:
func checkpoint() -> Dictionary:
func restore_time(state: Dictionary) -> Array[String]:
func get_state() -> Dictionary:
static func fallback_textures(kind: String) -> Array[Texture2D]:
```

## effects/particles/sprite_burst.gd

[Source](effects/particles/sprite_burst.gd). Base: `Control`.

```gdscript
func emit_burst(origin: Vector2, textures: Array[Texture2D], options: Dictionary = {}) -> Dictionary:
func advance(delta: float) -> Array[String]:
func present(camera: Transform2D) -> Array[String]:
func cancel(instance_id: int) -> void:
func clear() -> void:
func get_state() -> Array[Dictionary]:
```

## effects/refraction_field.gd

[Source](effects/refraction_field.gd). Base: `Control`.

```gdscript
func configure(options: Dictionary) -> Array[String]:
func set_rect(rect: Rect2) -> Array[String]:
func set_time(seconds: float) -> Array[String]:
func set_strength(value: float) -> Array[String]:
func clear() -> void:
func get_settings() -> Dictionary:
func get_source_rect() -> Rect2:
func get_strength() -> float:
func get_time() -> float:
```

## interaction/point_contact.gd

[Source](interaction/point_contact.gd). Base: `RefCounted`.

```gdscript
signal confirmed(point: Vector2)
static func hit_test(point: Vector2, center: Vector2, radius: float) -> bool:
func confirm_at(point: Vector2, center: Vector2, radius: float) -> bool:
func is_confirmed() -> bool:
func reset(confirmed_state: bool = false) -> void:
```

## motion/layer_pan.gd

[Source](motion/layer_pan.gd). Base: `RefCounted`.

```gdscript
func pan_to(offset: Vector2, settings: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func sample_transform() -> Transform2D:
func get_state() -> Dictionary:
func is_moving() -> bool:
func clear() -> void:
```

## motion/motion_curve.gd

[Source](motion/motion_curve.gd). Base: `RefCounted`.

```gdscript
static func validate(settings: Dictionary) -> Array[String]:
static func sample(progress: float, settings: Dictionary) -> float:
```

## motion/presentation_animation.gd

[Source](motion/presentation_animation.gd). Base: `RefCounted`.

```gdscript
static func sample(tracks: Dictionary, elapsed: float, duration_seconds: float, from_sample: Dictionary = {}, interpolation: String = "smooth") -> Dictionary:
static func evaluate(tracks: Dictionary, normalized_time: float, interpolation: String = "smooth") -> Dictionary:
static func track_value(keyframes: Array, normalized_time: float, interpolation: String = "smooth") -> float:
static func valid_id(value: Variant) -> bool:
static func finite_number(value: Variant) -> bool:
static func validate_catalog(value: Variant, track_groups: Array[String], catalog_label: String = "Presentation animation", allow_rotation: bool = false) -> Dictionary:
static func validate_tracks(value: Variant, context: String, errors: Array[String], allow_rotation: bool = false) -> void:
```

## text/intertitle.gd

[Source](text/intertitle.gd). Base: `RefCounted`.

```gdscript
func start(text: String, settings: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func request_advance() -> bool:
func sample() -> Dictionary:
func is_active() -> bool:
func clear() -> void:
func get_state() -> Dictionary:
func restore(state: Dictionary) -> Array[String]:
```

## text/text_set.gd

[Source](text/text_set.gd). Base: `RefCounted`.

```gdscript
func configure(sets: Dictionary, preferred_language: String = "en", fallback_language: String = "en") -> Array[String]:
func set_language(language: String) -> Array[String]:
func get_language() -> String:
func text(key: String, values: Dictionary = {}) -> String:
func text_in_language(key: String, language: String, values: Dictionary = {}) -> String:
func missing_keys(language: String) -> Array[String]:
```

## transitions/background_blackout.gd

[Source](transitions/background_blackout.gd). Base: `ColorRect`.

```gdscript
func fade_to(strength: float, duration_seconds: float = 0.4) -> Array[String]:
func advance(delta: float) -> Array[String]:
func clear() -> void:
func get_state() -> Dictionary:
func is_active() -> bool:
```

## transitions/eye_transition.gd

[Source](transitions/eye_transition.gd). Base: `RefCounted`.

```gdscript
func configure(partial_settings: Dictionary) -> Array[String]:
func start(mode: String, overrides: Dictionary = {}) -> Array[String]:
func advance(delta: float) -> void:
func sample() -> Dictionary:
func is_active() -> bool:
func skip() -> void:
func clear() -> void:
func get_settings() -> Dictionary:
func get_state() -> Dictionary:
func restore(state: Dictionary) -> Array[String]:
```


## Direct shader entry points

These two materials are directly host-bound public capabilities. Create a
separate ShaderMaterial instance for each independently controlled target.
Other bundled shaders are implementation dependencies of their owning components.

### Holographic Projection

[Shader](effects/shaders/character_hologram.gdshader). Bind to the actor or framed
portrait TextureRect. Supply `effect_time` from the host clock; pausing holds it.
`strength = 0` bypasses processing. The shader preserves the input alpha shape;
feed frame/UI and any paired voice processing are independently host-owned.

```glsl
uniform float strength : hint_range(0.0, 1.0) = 0.9;
uniform float effect_time = 0.0;
```

### Lens Flare Overlay

[Shader](effects/shaders/location_lens_flare.gdshader). Bind to a separate
screen-aligned overlay above scenery and below UI. `light_position` uses normalized
overlay UV coordinates; `aspect_ratio` is displayed width divided by height.
The host animates strength for an establishing shot; this shader owns no clock,
world light, automatic exposure, scene switch or camera movement.

```glsl
uniform vec2 light_position = vec2(0.8, 0.2);
uniform float strength : hint_range(0.0, 1.0) = 0.35;
uniform float aspect_ratio = 1.4222222;
```
