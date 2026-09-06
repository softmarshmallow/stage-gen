extends Node3D

## The ground: one 256 m plane carrying the whole patchwork shader.
##
## A port of the viewer's `buildGround` (index.html:3270-3395). Every uniform
## is bound from the manifest exactly as the viewer binds it, including the
## defaults it falls back to, so a run authored for the web viewer draws the
## same ground here. The shader itself is `view/shaders/ground.gdshader`.
##
## The plane is flat: the 32 segments exist because the viewer had them (its
## `v_world` is interpolated per vertex), not because there is a heightmap.

const Plates := preload("res://view/plates.gd")
const ProcNoise := preload("res://view/proc_noise.gd")
const GROUND_SEGMENTS := 32

var material: ShaderMaterial = null
var mesh_instance: MeshInstance3D = null
## `levelGain(base)`, which the decal module tints with (index.html:3388).
var ground_level: float = 1.0
## `[blend] shadow_scale`, `shadow_strength`, `decal_gain` — read out of the
## same block, published here so the seam modules do not re-read the manifest.
var shadow_scale: float = 1.0
var shadow_strength: float = 1.0
var decal_gain: float = 1.0
var size_meters: float = 256.0

var _snow_cover: float = 0.0

func setup(pkg, world, fu) -> void:
	var manifest: Dictionary = pkg.manifest
	var ground: Dictionary = manifest.get("ground", {})
	var biomes: Dictionary = ground.get("biomes", {})
	var base_id := String(ground.get("base_biome", ""))
	if not biomes.has(base_id):
		push_warning("ground: no base biome; the ground is not drawn")
		return
	var base: Dictionary = (biomes[base_id] as Dictionary).duplicate()
	base["biome_id"] = base_id
	# The base plus one plate per channel of the biome-weight plate, in channel
	# order; a missing plate falls back to the base so the slot exists.
	var by_channel := {}
	for biome_id: String in biomes.keys():
		var biome: Dictionary = (biomes[biome_id] as Dictionary).duplicate()
		biome["biome_id"] = biome_id
		by_channel[String(biome.get("weight_channel", ""))] = biome
	var slots: Array = []
	for channel in ["r", "g", "b"]:
		slots.append(by_channel.get(channel, base))
	var splat: Dictionary = ground.get("splat", {}) if ground.get("splat") is Dictionary else {}
	var blend: Dictionary = splat.get("blend", {}) if splat.get("blend") is Dictionary else {}
	var level: Dictionary = blend.get("level", {}) if blend.get("level") is Dictionary else {}
	size_meters = float(ground.get("size_meters", 256.0))
	var road: Variant = ground.get("road")
	var macro: Variant = ground.get("macro")
	var weather: Dictionary = manifest.get("weather", {}) if manifest.get("weather") is Dictionary else {}
	var snow_block: Variant = weather.get("snow")
	var snow: Variant = null
	if snow_block is Dictionary and (snow_block as Dictionary).get("cover") is Dictionary:
		var cover: Dictionary = (snow_block as Dictionary)["cover"]
		if cover.get("texture") != null:
			snow = cover
	var noise := ProcNoise.texture()

	material = ShaderMaterial.new()
	material.shader = load("res://view/shaders/ground.gdshader")
	var set_u := func(name: String, value: Variant) -> void:
		material.set_shader_parameter(name, value)

	set_u.call("u_albedo_0", pkg.texture(String(base["texture"])))
	for i in range(3):
		set_u.call("u_albedo_%d" % (i + 1), pkg.texture(String((slots[i] as Dictionary)["texture"])))
	if ground.get("biome_splat") is Dictionary:
		set_u.call("u_biome_splat", pkg.texture(String((ground["biome_splat"] as Dictionary)["image"]), false))
	if splat.has("image"):
		set_u.call("u_splat", pkg.texture(String(splat["image"]), false))
	set_u.call("u_noise", noise)
	set_u.call("u_tile_meters", Vector4(
		float(base.get("texel_meters", 1.0)),
		float((slots[0] as Dictionary).get("texel_meters", 1.0)),
		float((slots[1] as Dictionary).get("texel_meters", 1.0)),
		float((slots[2] as Dictionary).get("texel_meters", 1.0))))
	set_u.call("u_world_origin", Vector2(-size_meters * 0.5, -size_meters * 0.5))
	set_u.call("u_world_extent", Vector2(size_meters, size_meters))
	# Both hard-coded in the viewer (index.html:3339-3340).
	set_u.call("u_noise_tile_meters", 17.0)
	set_u.call("u_macro_tile_meters", 26.0)
	set_u.call("u_edge_softness", _number(blend, "edge_softness", 0.12))
	set_u.call("u_edge_noise_strength", _number(blend, "edge_noise_strength", 0.35))
	set_u.call("u_macro_tint_strength", _number(blend, "macro_tint_strength", 0.15))
	set_u.call("u_stochastic", 1.0)
	set_u.call("u_debug_mode", 0)
	set_u.call("u_bomb_meters", _number(blend, "bomb_meters", 0.0))
	set_u.call("u_bomb_rotate", _number(blend, "bomb_rotate", 1.0))
	set_u.call("u_edge_shadow", _number(blend, "edge_shadow", 0.0))
	set_u.call("u_edge_shadow_width", _number(blend, "edge_shadow_width", 0.4))
	set_u.call("u_edge_ink", _number(blend, "edge_ink", 0.0))
	set_u.call("u_edge_ink_width", _number(blend, "edge_ink_width", 0.12))
	set_u.call("u_edge_fine_meters", _number(blend, "edge_fine_meters", 0.7))
	set_u.call("u_edge_fine_strength", _number(blend, "edge_fine_strength", 0.0))
	set_u.call("u_edge_rim", _number(blend, "edge_rim", 0.0))
	set_u.call("u_flow_meters", _number(blend, "flow_meters", 200.0))
	set_u.call("u_edge_streak", _number(blend, "edge_streak", 0.0))
	set_u.call("u_smudge_meters", _number(blend, "smudge_meters", 0.3))
	set_u.call("u_smudge", _number(blend, "smudge", 0.0))
	set_u.call("u_edge_bleed", _number(blend, "edge_bleed", 0.0))
	set_u.call("u_edge_bleed_width", _number(blend, "edge_bleed_width", 1.0))
	set_u.call("u_stroke", _number(blend, "stroke", 0.0))
	set_u.call("u_stroke_meters", _number(blend, "stroke_meters", 5.0))
	set_u.call("u_stroke_cover", _number(blend, "stroke_cover", 1.0))
	var used_channels := 0
	for channel in ["r", "g", "b"]:
		if by_channel.has(channel):
			used_channels += 1
	set_u.call("u_biome_slots", float(used_channels))
	set_u.call("u_exposure", _number(blend, "exposure", 1.0))
	set_u.call("u_level", Vector4(
		Plates.level_gain(base, level),
		Plates.level_gain(slots[0], level),
		Plates.level_gain(slots[1], level),
		Plates.level_gain(slots[2], level)))
	# The road.
	var road_block: Dictionary = road if road is Dictionary else {}
	set_u.call("u_has_road", 1.0 if road is Dictionary else 0.0)
	set_u.call("u_albedo_road", pkg.texture(String(road_block["texture"])) if road is Dictionary else pkg.texture(String(base["texture"])))
	set_u.call("u_road_tile_meters", float(road_block.get("texel_meters", 1.0)) if road is Dictionary else 1.0)
	set_u.call("u_level_road", Plates.level_gain(road, level))
	set_u.call("u_road_edge_softness", _number(blend, "road_edge_softness", 0.10))
	set_u.call("u_road_noise_tile_meters", _number(blend, "road_noise_tile_meters", 3.0))
	set_u.call("u_road_noise_strength", _number(blend, "road_noise_strength", 0.45))
	# The macro field. Loaded as data: the shader compares the plate against
	# its own measured sRGB mean, so it must see the file's values.
	var macro_block: Dictionary = macro if macro is Dictionary else {}
	set_u.call("u_has_macro", 1.0 if macro is Dictionary else 0.0)
	set_u.call("u_macro_plate", pkg.texture(String(macro_block["texture"]), false) if macro is Dictionary else noise)
	var macro_meters := 1.0
	if macro is Dictionary:
		macro_meters = float(macro_block.get("period_meters", 0.0))
		if macro_meters == 0.0:
			macro_meters = float(macro_block.get("texel_meters", 1.0))
	set_u.call("u_macro_plate_meters", macro_meters)
	set_u.call("u_macro_plate_mean", float(macro_block.get("luma_mean", 0.5)) if macro is Dictionary else 0.5)
	set_u.call("u_macro_strength", float(macro_block.get("strength", 0.0)) if macro is Dictionary else 0.0)
	# The snow cover.
	var snow_spec: Dictionary = snow if snow is Dictionary else {}
	set_u.call("u_has_snow", 1.0 if snow is Dictionary else 0.0)
	set_u.call("u_albedo_snow", pkg.texture(String(snow_spec["texture"])) if snow is Dictionary else pkg.texture(String(base["texture"])))
	set_u.call("u_snow_tile_meters", float(snow_spec.get("texel_meters", 1.0)) if snow is Dictionary else 1.0)
	set_u.call("u_level_snow", Plates.level_gain(snow, level))
	set_u.call("u_snow_cover", 0.0)
	# The coast.
	set_u.call("u_shore_noise_tile_meters", _number(blend, "shore_noise_tile_meters", 4.0))
	set_u.call("u_shore_noise_strength", _number(blend, "shore_noise_strength", 0.5))
	set_u.call("u_shore_rim", _number(blend, "shore_rim", 0.14))

	ground_level = Plates.level_gain(base, level)
	shadow_scale = _number(blend, "shadow_scale", 1.0)
	shadow_strength = _number(blend, "shadow_strength", 1.0)
	decal_gain = _number(blend, "decal_gain", 1.0)

	if fu != null:
		fu.register(material)

	var plane := PlaneMesh.new()
	plane.size = Vector2(size_meters, size_meters)
	plane.subdivide_width = GROUND_SEGMENTS - 1
	plane.subdivide_depth = GROUND_SEGMENTS - 1
	plane.material = material
	mesh_instance = MeshInstance3D.new()
	mesh_instance.name = "GroundPlane"
	mesh_instance.mesh = plane
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mesh_instance)

func update(world, _delta: float, _cam: Dictionary) -> void:
	if material == null or world == null:
		return
	# The viewer writes `u_snow_cover` beside the shared uniforms every frame
	# (index.html:5531); it is a per-material uniform, so its module owns it.
	var weather: Variant = world.get("weather")
	if weather is Dictionary:
		set_snow_cover(float((weather as Dictionary).get("snow", 0.0)))

## The snow on the ground, `world.weather.snow`.
func set_snow_cover(value: float) -> void:
	if material == null or is_equal_approx(value, _snow_cover):
		return
	_snow_cover = value
	material.set_shader_parameter("u_snow_cover", value)

## Dev knobs, the viewer's keyboard debug controls (index.html:5276-5290).
func set_debug_mode(mode: int) -> void:
	if material != null:
		material.set_shader_parameter("u_debug_mode", clampi(mode, 0, 6))

func set_stochastic(on: bool) -> void:
	if material != null:
		material.set_shader_parameter("u_stochastic", 1.0 if on else 0.0)

func set_uniform(name: String, value: Variant) -> void:
	if material != null:
		material.set_shader_parameter(name, value)

static func _number(block: Dictionary, key: String, fallback: float) -> float:
	var value: Variant = block.get(key)
	if value is float or value is int:
		return float(value)
	return fallback
