class_name WeatherView
extends Node3D
## The weather in the frame: the rain pool, the snowfall pool, the standing
## water the rain leaves, the snow cover the frame owner forwards to the ground
## and the water, and the strike's flash envelope.
##
## Ported from the viewer's weather section (index.html :3930-4202):
## `buildRain` / `buildFall` / `fitFall` / `updateRain` / `updateFall`,
## `updateWet`, `updateSnowCover`, and `flashEnvelope`.
##
## WIRING THE FRAME OWNER OWES THIS MODULE
## - `set_ground_hook(callable)`: called with the snow factor every frame, for
##   the ground material's `u_snow_cover` (viewer :5531).
## - `set_water_hook(callable)`: called with the same value, for the water
##   material's `u_ice` (viewer :5532).
## - `set_decal_hook(callable)`: optional; called with the same value so the
##   dry decals can fade under the cover (`updateSnowCover`, viewer :3515-3521).
##   The dry decals belong to the decal module; this module owns only the
##   conditional (wet) ones.
## - `set_wet_hook(callable)`: optional; when the decal module builds the
##   conditional decals itself, wire this and WeatherView drops its own pool and
##   forwards `update_wet` instead. Exactly one of the two draws the puddles.
## - `flash(world) * WeatherView.FLASH_GAIN` is what Main writes into
##   FrameUniforms as `u_flash`.

const RAIN_SHADER := "res://view/shaders/rain.gdshader"
const WET_SHADER := "res://view/shaders/wet_decal.gdshader"
## `ORDER.rain`, over everything; and `ORDER.decal`, under the cards.
const RAIN_PRIORITY := 6
const DECAL_PRIORITY := 1
## `DECAL_Y` (index.html :180).
const DECAL_Y := 0.014
## The shared `u_flash` is the envelope at this gain (viewer :5534).
const FLASH_GAIN := 0.85
## Nearer layers fall a little faster, farther a little slower (`fitFall`).
const PACES: Array[float] = [1.25, 1.0, 0.8, 0.65]
## Per-layer alpha (`buildFall`).
const LAYER_WEIGHTS: Array[float] = [0.95, 0.75, 0.55, 0.4]
## The four parallax depths, in metres in front of the lens (`buildFall`).
const LAYER_DEPTHS: Array[float] = [2.6, 4.2, 6.4, 9.0]

## `{instance, multimesh, material, depths, layers, spec, last, custom,
## frustum_x, frustum_y, scroll_x, scroll_y}`; empty when the run authored none.
var rain_pool: Dictionary = {}
var snow_pool: Dictionary = {}
## `{instance, multimesh, material, entries}` per conditional decal id.
var wet_pools: Array = []

var _flash_seconds: float = 0.5
var _fov: float = 35.0
var _aspect: float = 16.0 / 9.0
var _distance: float = 18.0
var _fitted := Vector2(-1.0, -1.0)
## The puddles are re-aimed on a yaw change, and once on the first frame in
## case the frame owner opens with `changed` false.
var _oriented: bool = false
var _cam: Dictionary = {}
var _rng := RandomNumberGenerator.new()
var _ground_hook: Callable = Callable()
var _water_hook: Callable = Callable()
var _decal_hook: Callable = Callable()
var _wet_hook: Callable = Callable()

func setup(pkg, world, fu) -> void:
	var manifest: Dictionary = pkg.manifest
	var camera: Dictionary = manifest.get("camera", {}) if manifest.get("camera") is Dictionary else {}
	_fov = float(camera.get("fov_degrees", 35.0))
	_distance = float(camera.get("distance_meters", 18.0))
	_rng.seed = int(pkg.layout.get("seed", 0)) * 2654435761 + 7

	var weather: Dictionary = manifest.get("weather", {}) if manifest.get("weather") is Dictionary else {}
	var rain: Dictionary = weather.get("rain", {}) if weather.get("rain") is Dictionary else {}
	var snow: Dictionary = weather.get("snow", {}) if weather.get("snow") is Dictionary else {}
	var strike: Dictionary = rain.get("strike", {}) if rain.get("strike") is Dictionary else {}
	_flash_seconds = float(strike.get("flash_seconds", 0.5))

	rain_pool = _build_fall(pkg, rain.get("drops"), 0.3, 0.45, 0.0, "Rain")
	# Snowfall is the drops technique with round cells: full width, slow,
	# opaque, and swaying, which is the whole difference between rain and snow.
	snow_pool = _build_fall(pkg, snow.get("drops"), 1.0, 0.7, 0.012, "Snowfall")
	_build_wet_decals(pkg, fu)
	_fit_all()

# --- the rain and snowfall pools -------------------------------------------

func _build_fall(pkg, spec_value: Variant, narrow: float, opacity: float,
		sway: float, label: String) -> Dictionary:
	if not (spec_value is Dictionary):
		return {}
	var spec: Dictionary = spec_value
	var cells: Array = spec.get("cells", []) if spec.get("cells") is Array else []
	if cells.is_empty():
		return {}
	var texture: Texture2D = pkg.texture(str(spec.get("atlas", "")))
	if texture == null:
		return {}
	var count: int = maxi(1, int(spec.get("count_per_screen", 0)))
	var layers: int = clampi(int(spec.get("layers", 3)), 1, 4)

	var material := ShaderMaterial.new()
	material.shader = load(RAIN_SHADER)
	material.render_priority = RAIN_PRIORITY
	material.set_shader_parameter("u_map", texture)
	material.set_shader_parameter("u_count", float(count))
	material.set_shader_parameter("u_size", float(spec.get("height_meters", 0.25)))
	material.set_shader_parameter("u_narrow", narrow)
	material.set_shader_parameter("u_opacity", opacity)
	material.set_shader_parameter("u_sway", sway)
	material.set_shader_parameter("u_rain", 0.0)
	material.set_shader_parameter("u_weights", Vector4(
		LAYER_WEIGHTS[0], LAYER_WEIGHTS[1], LAYER_WEIGHTS[2], LAYER_WEIGHTS[3]))
	var sheet_width := float(spec.get("width_px", 1024))
	var sheet_height := float(spec.get("height_px", 1024))
	var windows: Array[Vector4] = []
	var aspects: Array[float] = []
	for index in range(mini(2, cells.size())):
		var cell: Dictionary = cells[index]
		windows.append(Vector4(
			float(cell.get("x", 0)) / sheet_width, float(cell.get("y", 0)) / sheet_height,
			float(cell.get("w", sheet_width)) / sheet_width,
			float(cell.get("h", sheet_height)) / sheet_height))
		aspects.append(float(cell.get("w", 1)) / maxf(float(cell.get("h", 1)), 1.0))
	while windows.size() < 2:
		windows.append(windows[0])
		aspects.append(aspects[0])
	material.set_shader_parameter("u_cell_a", windows[0])
	material.set_shader_parameter("u_cell_b", windows[1])
	material.set_shader_parameter("u_aspect_a", aspects[0])
	material.set_shader_parameter("u_aspect_b", aspects[1])

	var depths: Array[float] = []
	for index in range(layers):
		depths.append(LAYER_DEPTHS[index])
	while depths.size() < 4:
		depths.append(depths[depths.size() - 1])
	material.set_shader_parameter("u_depths", Vector4(depths[0], depths[1], depths[2], depths[3]))

	# The round cell, if the sheet drew one. The viewer looks for the kind
	# `drop` and nothing else (`buildFall` :3964), so the snow sheet's `speck`
	# is never drawn — its flakes are all cell 0. Kept, quirk and all: the map
	# reads this as "the drop/speck cell", which the code does not do.
	var drop_cell := -1
	for index in range(cells.size()):
		if str((cells[index] as Dictionary).get("kind", "")) == "drop":
			drop_cell = index
			break

	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.material = material
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_custom_data = true
	multimesh.mesh = quad
	multimesh.instance_count = count
	# The pack is kept as well as uploaded: `get_instance_custom_data` reads
	# back zeros under the headless (dummy) rendering server, so the test — and
	# anything that ever rerolls the field — needs the array itself.
	var packs := PackedColorArray()
	for i in range(count):
		var layer := i % layers
		# Mostly streaks; a drop now and then, and only in the near layers.
		var cell_index := 0
		if drop_cell >= 1 and layer < 2 and _rng.randf() < 0.15:
			cell_index = 1
		var scale := (0.35 if cell_index == 1 else 1.0) * (0.7 + _rng.randf() * 0.6)
		multimesh.set_instance_transform(i, Transform3D.IDENTITY)
		# (seed.x, seed.y, layer + 8 * cell, scale); the index and the layer's
		# weight are derived in the shader from INSTANCE_ID and the layer.
		var pack := Color(_rng.randf(), _rng.randf(),
			float(layer) + 8.0 * float(cell_index), scale)
		packs.append(pack)
		multimesh.set_instance_custom_data(i, pack)
	var instance := MultiMeshInstance3D.new()
	instance.name = label
	instance.multimesh = multimesh
	# The drops live in view space: nothing about the pool's own box is real.
	instance.custom_aabb = AABB(Vector3(-4096.0, -4096.0, -4096.0), Vector3(8192.0, 8192.0, 8192.0))
	instance.visible = false
	add_child(instance)
	return {
		"instance": instance, "multimesh": multimesh, "material": material,
		"depths": depths, "layers": layers, "spec": spec, "last": null, "custom": packs,
		"frustum_x": Vector4.ONE, "frustum_y": Vector4.ONE,
		"scroll_x": Vector4.ZERO, "scroll_y": Vector4.ZERO,
	}

## Frustum size at each layer's depth and the fall pace; on resize, and when the
## camera's distance moves (the viewer only had `resize`, because only the dev
## zoom moved the distance).
func _fit_all() -> void:
	_fit_fall(rain_pool)
	_fit_fall(snow_pool)

func _fit_fall(pool: Dictionary) -> void:
	if pool.is_empty() or _aspect <= 0.0 or not is_finite(_aspect):
		return
	var v_fov := deg_to_rad(_fov)
	# The authored fall speed is metres per second AT THE GROUND: a drop crosses
	# the screen at the rate the ground's frustum says, and nearer layers a
	# little faster. Measured against a near layer's own tiny frustum, eleven
	# metres a second read as static noise, not rain.
	var ground_height := 2.0 * tan(v_fov / 2.0) * (_distance if _distance > 0.0 else 18.0)
	var speed := float((pool["spec"] as Dictionary).get("fall_speed_meters_per_second", 1.0))
	var frustum_x := Vector4.ZERO
	var frustum_y := Vector4.ZERO
	var speeds := Vector4.ZERO
	var depths: Array = pool["depths"]
	for i in range(4):
		var height := 2.0 * tan(v_fov / 2.0) * float(depths[i]) * 1.1
		frustum_x[i] = height * _aspect
		frustum_y[i] = height
		speeds[i] = (speed / maxf(ground_height, 0.0001)) * PACES[i]
	pool["frustum_x"] = frustum_x
	pool["frustum_y"] = frustum_y
	var material: ShaderMaterial = pool["material"]
	material.set_shader_parameter("u_frustum_x", frustum_x)
	material.set_shader_parameter("u_frustum_y", frustum_y)
	material.set_shader_parameter("u_speeds", speeds)

func update_rain(rain: float, yaw: float) -> void:
	_update_fall(rain_pool, rain, yaw)

func update_fall(snow: float, yaw: float) -> void:
	_update_fall(snow_pool, snow, yaw)

func _update_fall(pool: Dictionary, factor: float, yaw: float) -> void:
	if pool.is_empty():
		return
	var material: ShaderMaterial = pool["material"]
	material.set_shader_parameter("u_rain", factor)
	(pool["instance"] as MultiMeshInstance3D).visible = factor > 0.005
	# Parallax: the camera slides over the world and the drops, which hang in
	# the air between the lens and the ground, slide against it by their own
	# depth's share of the frustum, nearer ones more.
	var target: Vector3 = _cam.get("target", Vector3.ZERO)
	var position: Vector3 = _cam.get("position", Vector3(0.0, 1.0, 1.0))
	var right := Vector3(cos(yaw), 0.0, -sin(yaw))
	var offset := position - target
	var up_length := sqrt(offset.x * offset.x + offset.z * offset.z)
	if up_length <= 0.0:
		up_length = 1.0
	var up := Vector3(-offset.x / up_length, 0.0, -offset.z / up_length)
	var last: Variant = pool["last"]
	var previous: Vector3 = last if last is Vector3 else target
	pool["last"] = target
	var delta_x := target.x - previous.x
	var delta_z := target.z - previous.z
	var along_right := delta_x * right.x + delta_z * right.z
	var along_up := delta_x * up.x + delta_z * up.z
	var scroll_x: Vector4 = pool["scroll_x"]
	var scroll_y: Vector4 = pool["scroll_y"]
	var frustum_x: Vector4 = pool["frustum_x"]
	var frustum_y: Vector4 = pool["frustum_y"]
	for i in range(4):
		scroll_x[i] -= along_right / maxf(frustum_x[i], 0.0001)
		scroll_y[i] -= along_up / maxf(frustum_y[i], 0.0001)
	pool["scroll_x"] = scroll_x
	pool["scroll_y"] = scroll_y
	material.set_shader_parameter("u_scroll_x", scroll_x)
	material.set_shader_parameter("u_scroll_y", scroll_y)

# --- the standing water ----------------------------------------------------

func _build_wet_decals(pkg, fu) -> void:
	var ground: Dictionary = pkg.manifest.get("ground", {}) if pkg.manifest.get("ground") is Dictionary else {}
	var specs: Dictionary = ground.get("decals", {}) if ground.get("decals") is Dictionary else {}
	var layout: Dictionary = pkg.layout
	if specs.is_empty():
		return
	# A decal that belongs under a prop draws only if that prop's card can.
	var drawable: Dictionary = {}
	var props: Dictionary = pkg.manifest.get("props", {}) if pkg.manifest.get("props") is Dictionary else {}
	for raw: Dictionary in layout.get("entities", []):
		if str(raw.get("kind", "")) == "prop":
			drawable[str(raw.get("id", ""))] = props.has(str(raw.get("prop", "")))
	var grouped: Dictionary = {}
	for entry: Dictionary in layout.get("decals", []):
		if str(entry.get("condition", "")) == "":
			continue
		var decal_id := str(entry.get("decal", ""))
		if not specs.has(decal_id):
			continue
		var under := str(entry.get("under", ""))
		if under != "" and drawable.get(under, true) == false:
			continue
		if not grouped.has(decal_id):
			grouped[decal_id] = []
		(grouped[decal_id] as Array).append(entry)
	# [blend] decal_gain: a skirt is drawn as pale soil and would sit on a dark
	# turf as a stain; the ground's level, then the authored dimming.
	var gain := _decal_gain(pkg.manifest)
	for decal_id: String in grouped:
		var spec: Dictionary = specs[decal_id]
		var texture: Texture2D = pkg.texture(str(spec.get("image", "")))
		if texture == null:
			continue
		var material := ShaderMaterial.new()
		material.shader = load(WET_SHADER)
		material.render_priority = DECAL_PRIORITY
		material.set_shader_parameter("u_map", texture)
		material.set_shader_parameter("u_tint", Vector3(gain, gain, gain))
		material.set_shader_parameter("u_opacity", 0.0)
		if fu != null:
			fu.register(material)
		var quad := QuadMesh.new()
		quad.size = Vector2.ONE
		quad.material = material
		var entries: Array = grouped[decal_id]
		var multimesh := MultiMesh.new()
		multimesh.transform_format = MultiMesh.TRANSFORM_3D
		multimesh.mesh = quad
		multimesh.instance_count = entries.size()
		var instance := MultiMeshInstance3D.new()
		instance.name = "Wet_" + decal_id
		instance.multimesh = multimesh
		instance.visible = false
		var half := float(ground.get("size_meters", 256.0))
		instance.custom_aabb = AABB(Vector3(-half, -8.0, -half), Vector3(half * 2.0, 16.0, half * 2.0))
		add_child(instance)
		wet_pools.append({
			"instance": instance, "multimesh": multimesh, "material": material,
			"entries": entries, "spec": spec,
		})
	_orient_wet(0.0)

## The linear gain the ground plate is levelled by, times [blend] decal_gain
## (`levelGain(base)` index.html :3296-3301, `buildDecals` :3494-3495).
static func _decal_gain(manifest: Dictionary) -> float:
	var ground: Dictionary = manifest.get("ground", {}) if manifest.get("ground") is Dictionary else {}
	var splat: Dictionary = ground.get("splat", {}) if ground.get("splat") is Dictionary else {}
	var blend: Dictionary = splat.get("blend", {}) if splat.get("blend") is Dictionary else {}
	var biomes: Dictionary = ground.get("biomes", {}) if ground.get("biomes") is Dictionary else {}
	var base_id := str(ground.get("base_biome", ""))
	var level := 1.0
	if biomes.has(base_id):
		var base: Dictionary = biomes[base_id]
		var luma: Variant = base.get("luma_mean")
		var levels: Dictionary = blend.get("level", {}) if blend.get("level") is Dictionary else {}
		var target: Variant = levels.get(base_id, base.get("value_target"))
		if luma != null and target != null:
			level = clampf(_to_linear(float(target)) / maxf(_to_linear(float(luma)), 0.01), 0.5, 2.5)
	var decal_gain := 1.0
	if blend.get("decal_gain") != null:
		decal_gain = float(blend["decal_gain"])
	return level * decal_gain

static func _to_linear(value: float) -> float:
	return value / 12.92 if value <= 0.04045 else pow((value + 0.055) / 1.055, 2.4)

## A patch is a ground piece under the look contract, like the litter: its marks
## carry their shadow along their lower edge, so the patch keeps its lower edge
## toward the camera and rotation_degrees is only a jitter.
func _orient_wet(yaw: float) -> void:
	for pool: Dictionary in wet_pools:
		var spec: Dictionary = pool["spec"]
		var width := float(spec.get("width_meters", 1.0))
		var height := float(spec.get("height_meters", 1.0))
		var multimesh: MultiMesh = pool["multimesh"]
		var entries: Array = pool["entries"]
		for index in range(entries.size()):
			var entry: Dictionary = entries[index]
			var scale := float(entry.get("scale", 1.0))
			var spin := yaw + deg_to_rad(float(entry.get("rotation_degrees", 0.0)))
			var basis := Basis(Vector3.RIGHT, -PI / 2.0) * Basis(Vector3.BACK, spin) \
				* Basis.IDENTITY.scaled(Vector3(width * scale, height * scale, 1.0))
			multimesh.set_instance_transform(index, Transform3D(basis, Vector3(
				float(entry.get("x", 0.0)), DECAL_Y, float(entry.get("z", 0.0)))))

## Standing water fades with wetness; a dry world shows none.
func update_wet(wet: float) -> void:
	if _wet_hook.is_valid():
		_wet_hook.call(wet)
		return
	for pool: Dictionary in wet_pools:
		(pool["instance"] as MultiMeshInstance3D).visible = wet > 0.01
		(pool["material"] as ShaderMaterial).set_shader_parameter("u_opacity", wet)

## The cover the frame owner forwards: the ground's `u_snow_cover`, the water's
## `u_ice`, and the dry decals' fade, none of which this module owns.
func update_snow_cover(snow: float) -> void:
	if _ground_hook.is_valid():
		_ground_hook.call(snow)
	if _water_hook.is_valid():
		_water_hook.call(snow)
	if _decal_hook.is_valid():
		_decal_hook.call(snow)

func set_ground_hook(hook: Callable) -> void:
	_ground_hook = hook

func set_water_hook(hook: Callable) -> void:
	_water_hook = hook

func set_decal_hook(hook: Callable) -> void:
	_decal_hook = hook

## Hand the puddles to the decal module: this pool goes dark and forwards.
func set_wet_hook(hook: Callable) -> void:
	_wet_hook = hook
	for pool: Dictionary in wet_pools:
		(pool["instance"] as MultiMeshInstance3D).visible = false

# --- the frame -------------------------------------------------------------

func update(world, _delta: float, cam: Dictionary) -> void:
	_cam = cam
	var resolution: Vector2 = cam.get("resolution", Vector2(1600.0, 900.0))
	var position: Vector3 = cam.get("position", Vector3.ZERO)
	var target: Vector3 = cam.get("target", Vector3.ZERO)
	var distance := position.distance_to(target)
	if distance <= 0.0:
		distance = 18.0
	if resolution != _fitted or absf(distance - _distance) > 0.001:
		_fitted = resolution
		_distance = distance
		_aspect = resolution.x / maxf(resolution.y, 1.0)
		_fit_all()

	var weather: Dictionary = world.weather
	var rain := float(weather.get("rain", 0.0))
	var snow := float(weather.get("snow", 0.0))
	var flash_value := flash(world) * FLASH_GAIN
	var night := float(world.night)
	var time := float(world.time)
	for pool: Dictionary in [rain_pool, snow_pool]:
		if pool.is_empty():
			continue
		var material: ShaderMaterial = pool["material"]
		material.set_shader_parameter("u_time", time)
		material.set_shader_parameter("u_night", night)
		material.set_shader_parameter("u_flash", flash_value)

	var yaw := float(cam.get("yaw", 0.0))
	update_rain(rain, yaw)
	update_fall(snow, yaw)
	# The puddles go under the snow with the skirts.
	update_wet(float(weather.get("wet", 0.0)) * (1.0 - snow))
	update_snow_cover(snow)
	if bool(cam.get("changed", false)) or not _oriented:
		_oriented = true
		_orient_wet(yaw)

## The strike's flash for this instant. Main writes `u_flash = flash * FLASH_GAIN`.
func flash(world) -> float:
	var weather: Dictionary = world.weather
	return flash_envelope(float(world.time) - float(weather.get("flash_at", -99.0)), _flash_seconds)

## The flash: two pulses and a tail, the way a real strike reads. Feel, not
## contract (index.html :442-448).
static func flash_envelope(age: float, seconds: float) -> float:
	if age < 0.0 or age > seconds:
		return 0.0
	if age < 0.05:
		return 1.0
	if age < 0.09:
		return 0.3
	if age < 0.16:
		return 0.9
	return maxf(0.0, 0.9 * (1.0 - (age - 0.16) / maxf(0.01, seconds - 0.16)))
