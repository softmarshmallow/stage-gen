class_name CameraRig
extends Node3D

## The camera: an oblique rig on a fixed pitch, a yaw that moves in detents, a
## follow that eases, and a trauma shake.
##
## A port of `applyRig` (viewer/index.html:4835-4847), the yaw easing
## (:5464-5476), the follow and shake (:5694-5709) and the mode framings
## (:5130-5148). Godot world space is the simulation's space, so the offset
## formula is the viewer's, unchanged: nothing flips z.

const YAW_SNAP_RESPONSE := 0.22
const YAW_SNAP_EPSILON := 1e-4
const SHAKE_METERS := 0.32
const SHAKE_ROLL := 0.035
const TRAUMA_DECAY := 1.7
const VERDICT_SIZE := Vector2i(1600, 900)
const ZOOM_RANGE := Vector2(8.0, 44.0)
const ZOOM_STEP := 1.5
const GALLERY_PAN := 14.0
const NEAR := 0.5
const FAR := 300.0

var camera: Camera3D = null
## Radians. `yaw` is where the camera is, `yaw_target` where the detent put it.
var yaw: float = 0.0
var yaw_target: float = 0.0
var yaw_step: float = PI * 0.25
var yaw_allowed: bool = true
var pitch: float = deg_to_rad(55.0)
var distance: float = 18.0
var follow_lerp: float = 0.08
var target: Vector3 = Vector3.ZERO
var offset: Vector3 = Vector3.ZERO
var trauma: float = 0.0
var mode: String = "play"
## Device pixels per logical pixel, the viewer's `min(devicePixelRatio, 2)`.
## Only `u_resolution` and the puff pixel scale read it.
var pixel_ratio: float = 1.0
## The camp, for the verdict framing.
var camp_position: Vector3 = Vector3.ZERO
## The billboard basis every card copies: the viewer's `cardQuaternion`, which
## is refreshed inside `applyRig` only, so it carries neither the follow nor
## the shake's roll (index.html:2494, :5709 — the cards do not counter-roll).
var card_basis: Basis = Basis.IDENTITY

var _changed: bool = true

func setup(pkg, world, _fu) -> void:
	var manifest: Dictionary = pkg.manifest
	var spec: Dictionary = manifest.get("camera", {}) if manifest.get("camera") is Dictionary else {}
	pitch = deg_to_rad(_number(spec, "pitch_degrees", 55.0))
	distance = _number(spec, "distance_meters", 18.0)
	follow_lerp = _number(spec, "follow_lerp", 0.08)
	yaw = deg_to_rad(_number(spec, "yaw_degrees", 45.0))
	yaw_target = yaw
	yaw_step = deg_to_rad(_number(spec, "yaw_step_degrees", 45.0))
	yaw_allowed = spec.get("rotation_allowed") != false
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else manifest.get("layout", {})
	var camp: Variant = layout.get("camp_position")
	if camp is Dictionary:
		camp_position = Vector3(float((camp as Dictionary).get("x", 0.0)), 0.0, float((camp as Dictionary).get("z", 0.0)))
	if world != null:
		target = Vector3(world.player.x, 0.0, world.player.z)

	camera = Camera3D.new()
	camera.name = "Camera"
	camera.near = NEAR
	camera.far = FAR
	camera.fov = _number(spec, "fov_degrees", 35.0)
	# `keep_aspect = KEEP_HEIGHT` makes `fov` the vertical field of view, which
	# is what three's PerspectiveCamera means by it.
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.current = true
	add_child(camera)
	apply_rig()

## The rig itself. Cards stay perpendicular to the view axis at any yaw, so the
## depth buffer still orders them by foot position without a sort.
func apply_rig() -> void:
	offset = Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	if camera == null:
		return
	# The look_at basis, built here rather than read back off the node so the
	# shake's roll never reaches a billboard.
	var back := offset.normalized()
	var right := Vector3.UP.cross(back).normalized()
	card_basis = Basis(right, back.cross(right), back)
	camera.position = target + offset
	if camera.is_inside_tree():
		camera.look_at(target, Vector3.UP)
	_changed = true

## Ease toward the detent Q/E selected. Nothing happens once it arrives, so a
## settled camera costs no billboard work. Returns whether it moved.
func ease_yaw(delta: float) -> bool:
	if absf(yaw_target - yaw) <= YAW_SNAP_EPSILON:
		return false
	var k := 1.0 - pow(1.0 - YAW_SNAP_RESPONSE, delta * 60.0)
	yaw += (yaw_target - yaw) * k
	if absf(yaw_target - yaw) <= YAW_SNAP_EPSILON:
		yaw = yaw_target
	apply_rig()
	return true

## One detent per press; refused when the run forbids rotation or in verdict.
func turn(direction: int) -> void:
	if not yaw_allowed or mode == "verdict":
		return
	yaw_target += signf(float(direction)) * yaw_step

func set_zoom(value: float) -> void:
	distance = clampf(value, ZOOM_RANGE.x, ZOOM_RANGE.y)
	apply_rig()

func zoom_by(steps: float) -> void:
	set_zoom(distance + steps * ZOOM_STEP)

## The gallery pans the target instead of following, in camera-yaw space.
func pan(input_x: float, input_z: float, delta: float) -> void:
	var step := GALLERY_PAN * delta
	var c := cos(yaw)
	var s := sin(yaw)
	target.x += (input_x * c + input_z * s) * step
	target.z += (-input_x * s + input_z * c) * step
	apply_rig()

## The follow and the shake, in the viewer's order: the target eases toward the
## player (never in verdict), the camera is placed and aimed, and the shake is
## applied afterwards in camera-local space so the cards do not counter-roll.
func follow_and_shake(world, delta: float) -> void:
	if camera == null:
		return
	# Deviation from the viewer's `if (mode !== 'verdict')` (:5694): the follow
	# runs in `play` only. In gallery the target is the rows' own (5, 0, 5) and
	# WASD pans it — a follow there drags the pan straight back to the player
	# and frames the world instead of the gallery, which is not what the
	# reference gallery frame (camera 12.30, 14.74, 12.30) shows.
	if mode == "play" and world != null:
		var goal := Vector3(world.player.x, 0.0, world.player.z)
		target = target.lerp(goal, 1.0 - pow(1.0 - follow_lerp, delta * 60.0))
	camera.position = target + offset
	if camera.is_inside_tree():
		camera.look_at(target, Vector3.UP)
	if trauma > 0.0:
		trauma = maxf(0.0, trauma - delta * TRAUMA_DECAY)
		var s := trauma * trauma
		var t: float = (world.time if world != null else 0.0) * 31.0
		var nx := sin(t) * 0.6 + sin(t * 2.3 + 1.7) * 0.4
		var ny := sin(t * 1.7 + 0.9) * 0.6 + sin(t * 3.1 + 2.2) * 0.4
		camera.translate_object_local(Vector3(nx * SHAKE_METERS * s, ny * SHAKE_METERS * s, 0.0))
		camera.rotate_object_local(Vector3(0.0, 0.0, 1.0), sin(t * 1.3 + 0.4) * SHAKE_ROLL * s)

func add_trauma(amount: float) -> void:
	trauma = minf(1.0, trauma + amount)

## Enter a framing. `verdict` pins the camera on the camp, stands the player
## just south of it and lights the fire when it is dark enough to matter;
## `gallery` parks the target where `buildGallery` lays its rows.
func set_mode(next: String, world = null) -> void:
	mode = next
	if next == "gallery":
		target = Vector3(5.0, 0.0, 5.0)
	elif next == "verdict":
		target = Vector3(camp_position.x, 0.0, camp_position.z)
		if world != null:
			world.player.x = camp_position.x
			world.player.z = camp_position.z + 1.8
			if world.night > 0.4:
				for entity: Dictionary in world.entities:
					if String(entity.get("prop_id", "")) == "campfire":
						entity["state"] = "lit"
						entity["dirty"] = true
						entity["burn"] = 1e6
						break
	apply_rig()

## The camera facts every view module is handed each frame.
func cam_state(changed: bool, resolution: Vector2) -> Dictionary:
	return {
		"yaw": yaw,
		"basis": card_basis,
		"position": camera.position if camera != null else Vector3.ZERO,
		"target": target,
		"changed": changed or _changed,
		"pixel_ratio": pixel_ratio,
		"resolution": resolution,
	}

## Called by the frame owner once it has handed `cam` to every module.
func clear_changed() -> void:
	_changed = false

static func _number(block: Dictionary, key: String, fallback: float) -> float:
	var value: Variant = block.get(key)
	if value is float or value is int:
		return float(value)
	return fallback
