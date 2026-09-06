class_name Decals
extends Node3D

## The skirts and the pads: the marks the layout painted on the ground under
## the props, so a trunk does not meet the turf on a hard line.
##
## A port of `buildDecals` (viewer :3467), `orientDecals` (:3526),
## `updateSnowCover` (:3515) and `retintDecals` (:3445).
##
## Three things the viewer's comments call out and this keeps:
##
##   * a decal whose `under` prop is not drawable is skipped — a skirt or a pad
##     on its own is a stain on the ground (:3471);
##   * the DEPTH TEST stays on. `renderOrder` only sorts within a queue, so a
##     transparent decal always drew after every opaque card; at a 55 degree
##     pitch a flat ground quad projects just ABOVE its anchor, which is exactly
##     where the trunk stands, and with the test off every skirt painted over
##     the foot of its own tree (:3483-3491);
##   * a patch keeps its lower edge toward the camera and re-aims on every yaw
##     change, because its marks carry their shadow along that edge;
##     `rotation_degrees` is only a jitter (:3523-3531).
##
## 1608 decals over five pictures, so they are drawn as one MultiMesh per
## picture rather than 1608 nodes; the shader is the card shader with
## `u_billboard = 0`, which leaves the node's own basis alone.

## Just clear of the ground plate and under the litter (viewer :180).
const DECAL_Y := 0.014
## `ORDER.decal` (viewer :187): under the contact shadows.
const DECAL_PRIORITY := 1
const CARD_BLEND_SHADER := "res://view/shaders/card_blend.gdshader"

## The conditional decals — the puddles the rain leaves — are the weather's, and
## `view/shaders/wet_decal.gdshader` is where they are drawn. Set this true if
## this module should own them instead; the code for both is here.
var own_conditional: bool = false

var package: Variant = null
var manifest: Dictionary = {}
var uniforms: Variant = null

## One group per picture: `{node, multimesh, material, entries, conditional}`.
var _groups: Array = []
var _yaw: float = INF
var _snow: float = -1.0
var _wet: float = -1.0


func setup(pkg, world, fu) -> void:
	package = pkg
	manifest = pkg.manifest
	uniforms = fu
	_build(pkg.layout if not pkg.layout.is_empty() else manifest.get("layout", {}))
	orient(float(Cards.field(world, "camera_yaw", 0.0)))


func update(world, _delta: float, cam: Dictionary) -> void:
	if bool(cam.get("changed", false)) or not is_equal_approx(float(cam.get("yaw", 0.0)), _yaw):
		orient(float(cam.get("yaw", 0.0)))
	var weather: Variant = Cards.field(world, "weather", {})
	var snow := float(Cards.field(weather, "snow", 0.0))
	var wet := float(Cards.field(weather, "wet", 0.0))
	set_snow_cover(snow)
	set_wet(wet * (1.0 - snow))


func set_mode(mode: String) -> void:
	visible = mode != "gallery"


# --- the build --------------------------------------------------------------

func _build(layout: Dictionary) -> void:
	var specs: Dictionary = manifest.get("ground", {}).get("decals", {})
	# A prop the manifest lost is not drawn, so neither is its skirt.
	var drawable := {}
	var props: Dictionary = manifest.get("props", {})
	for raw: Variant in layout.get("entities", []):
		if raw is Dictionary and String((raw as Dictionary).get("kind", "")) == "prop":
			drawable[String((raw as Dictionary).get("id", ""))] = props.has(String((raw as Dictionary).get("prop", "")))
	# [blend] decal_gain: a skirt is drawn as pale soil and would sit on a dark
	# turf as a stain; the ground's own level, then the authored dimming.
	var gain := ground_level(manifest) * decal_gain(manifest)
	var buckets := {}
	for entry: Variant in layout.get("decals", []):
		if not (entry is Dictionary):
			continue
		var row: Dictionary = entry
		var id := String(row.get("decal", ""))
		var spec: Variant = specs.get(id)
		if not (spec is Dictionary):
			continue
		var under := String(row.get("under", ""))
		if under != "" and drawable.get(under, true) == false:
			continue
		var conditional := row.get("condition") != null and String(row.get("condition", "")) != ""
		if conditional and not own_conditional:
			continue
		var key := "%s|%s" % [id, "wet" if conditional else "dry"]
		if not buckets.has(key):
			buckets[key] = {"spec": spec, "conditional": conditional, "entries": []}
		(buckets[key]["entries"] as Array).append(row)
	for key: String in buckets.keys():
		var bucket: Dictionary = buckets[key]
		_groups.append(_group(bucket["spec"], bucket["entries"], bool(bucket["conditional"]), gain))


func _group(spec: Dictionary, entries: Array, conditional: bool, gain: float) -> Dictionary:
	var material := ShaderMaterial.new()
	material.shader = load(CARD_BLEND_SHADER)
	material.set_shader_parameter("u_map", package.texture(String(spec.get("image", ""))))
	material.set_shader_parameter("u_frame_uv", Vector4(0.0, 0.0, 1.0, 1.0))
	material.set_shader_parameter("u_flip", 0.0)
	material.set_shader_parameter("u_alpha_cutoff", Cards.ALPHA_CUTOFF)
	# A decal is built with `soft: true`, so it never alpha-tests and keeps its
	# real alpha (viewer :3481).
	material.set_shader_parameter("u_soft", 1.0)
	material.set_shader_parameter("u_opacity", 0.0 if conditional else 1.0)
	material.set_shader_parameter("u_tint", Vector3(gain, gain, gain))
	material.set_shader_parameter("u_sway_mode", 0.0)
	material.set_shader_parameter("u_sway_amplitude", 0.0)
	# A patch lies on the ground: it keeps the transform it is given.
	material.set_shader_parameter("u_billboard", 0.0)
	material.render_priority = DECAL_PRIORITY
	if uniforms != null:
		uniforms.register(material)
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.surface_set_material(0, material)
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.mesh = quad
	multi.instance_count = entries.size()
	var node := MultiMeshInstance3D.new()
	node.multimesh = multi
	node.visible = not conditional
	var extent := float(manifest.get("ground", {}).get("size_meters", 256.0))
	node.custom_aabb = AABB(Vector3(-extent, -4.0, -extent), Vector3(extent * 2.0, 8.0, extent * 2.0))
	add_child(node)
	return {
		"node": node,
		"multimesh": multi,
		"material": material,
		"entries": entries,
		"conditional": conditional,
		"width": float(spec.get("width_meters", 1.0)),
		"height": float(spec.get("height_meters", 1.0)),
	}


# --- the per-frame writes ---------------------------------------------------

## Re-aim every patch: its lower edge stays toward the camera, and
## `rotation_degrees` is a jitter on top of the yaw (viewer :3526).
func orient(yaw: float) -> void:
	_yaw = yaw
	for group: Dictionary in _groups:
		var multi: MultiMesh = group["multimesh"]
		var entries: Array = group["entries"]
		var base_width := float(group["width"])
		var base_height := float(group["height"])
		for index in entries.size():
			var entry: Dictionary = entries[index]
			var scale := float(entry.get("scale", 1.0)) if entry.get("scale") != null else 1.0
			var spin := yaw + deg_to_rad(float(entry.get("rotation_degrees", 0.0)))
			# three's Euler XYZ is Rx then Rz; the quad's own size is the
			# innermost factor, which is what `PlaneGeometry(w * s, h * s)` was.
			var basis := Basis(Vector3(1.0, 0.0, 0.0), -PI / 2.0) * Basis(Vector3(0.0, 0.0, 1.0), spin)
			basis = basis * Basis.from_scale(Vector3(base_width * scale, base_height * scale, 1.0))
			multi.set_instance_transform(
				index,
				Transform3D(basis, Vector3(float(entry.get("x", 0.0)), DECAL_Y, float(entry.get("z", 0.0)))),
			)


## The snow buries the skirts and the path: every dry decal fades with the cover
## (viewer :3515).
func set_snow_cover(snow: float) -> void:
	if is_equal_approx(snow, _snow):
		return
	_snow = snow
	var opacity := 1.0 - 0.85 * clampf(snow, 0.0, 1.0)
	for group: Dictionary in _groups:
		if bool(group["conditional"]):
			continue
		(group["material"] as ShaderMaterial).set_shader_parameter("u_opacity", opacity)


## The standing water comes up with the wet (viewer `updateWet`, :4165).
func set_wet(wet: float) -> void:
	if is_equal_approx(wet, _wet):
		return
	_wet = wet
	for group: Dictionary in _groups:
		if not bool(group["conditional"]):
			continue
		(group["node"] as Node3D).visible = wet > 0.01
		(group["material"] as ShaderMaterial).set_shader_parameter("u_opacity", wet)


# --- the gain ---------------------------------------------------------------

## sRGB to linear, the exact curve the viewer uses (:3295).
static func to_linear(value: float) -> float:
	return value / 12.92 if value <= 0.04045 else pow((value + 0.055) / 1.055, 2.4)


## `levelGain(base)` for the base biome (viewer :3296-3302, :3388): each plate is
## levelled from its measured sRGB mean to its authored target as a linear gain,
## clamped so a wildly off plate is visibly off rather than silently rescued.
static func ground_level(manifest: Dictionary) -> float:
	var ground: Dictionary = manifest.get("ground", {})
	var biomes: Dictionary = ground.get("biomes", {})
	var base_id := String(ground.get("base_biome", ""))
	var plate: Variant = biomes.get(base_id)
	if not (plate is Dictionary) or (plate as Dictionary).get("luma_mean") == null:
		return 1.0
	var levels: Dictionary = ground.get("splat", {}).get("blend", {}).get("level", {})
	var target: Variant = levels.get(base_id, (plate as Dictionary).get("value_target"))
	if target == null:
		return 1.0
	return minf(2.5, maxf(0.5, to_linear(float(target)) / maxf(0.01, to_linear(float((plate as Dictionary)["luma_mean"])))))


## `[blend] decal_gain` (run full-v66: 0.62).
static func decal_gain(manifest: Dictionary) -> float:
	var blend: Dictionary = manifest.get("ground", {}).get("splat", {}).get("blend", {})
	return float(blend.get("decal_gain", 1.0)) if blend.get("decal_gain") != null else 1.0


func group_count() -> int:
	return _groups.size()


func instance_count() -> int:
	var total := 0
	for group: Dictionary in _groups:
		total += (group["entries"] as Array).size()
	return total
