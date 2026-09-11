extends Control

## Concrete 3D rendering proof for the lab. The caller supplies evaluated manpu
## samples; this preview owns no animation clocks or event lifetime decisions.
## One logical pixel maps to WORLD_PIXEL_SIZE meters. Offsets are proportional
## to the original mark height and follow the camera-facing character plane.
const DESIGN_SIZE := Vector2(1280, 900)
const WORLD_PIXEL_SIZE := 1.0 / 240.0
var _viewport: SubViewport
var _world: Node3D
var _camera_3d: Camera3D
var _actor: Sprite3D
var _puffs: Dictionary = {}
var _surface: TextureRect
var _actor_rect := Rect2()
var _anchor_uv := Vector2.ZERO
var _mark_height := 0.0
var _mark_texture: Texture2D
var _samples: Array = []
var _angle := 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_viewport = SubViewport.new()
	_viewport.name = "BillboardViewport"
	_viewport.size = Vector2i(DESIGN_SIZE)
	_viewport.own_world_3d = true
	_viewport.transparent_bg = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)
	_world = Node3D.new()
	_viewport.add_child(_world)
	_camera_3d = Camera3D.new()
	_camera_3d.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera_3d.set_orthogonal(DESIGN_SIZE.y * WORLD_PIXEL_SIZE, 0.05, 100.0)
	_camera_3d.current = true
	_world.add_child(_camera_3d)
	_actor = _sprite("ActorBillboard", 0)
	_surface = TextureRect.new()
	_surface.texture = _viewport.get_texture()
	_surface.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_surface.stretch_mode = TextureRect.STRETCH_SCALE
	_surface.size = DESIGN_SIZE
	_surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_surface)
	set_angle(0.0)
	sync_resolution()


func bind_actor(texture: Texture2D, rect: Rect2, anchor_uv: Vector2, mark_texture: Texture2D, mark_height: float) -> void:
	_actor.texture = texture
	_actor_rect = rect
	_anchor_uv = anchor_uv
	_mark_texture = mark_texture
	_mark_height = mark_height
	_actor.pixel_size = rect.size.y * WORLD_PIXEL_SIZE / texture.get_height()
	_actor.position = Vector3((rect.get_center().x - 640.0) * WORLD_PIXEL_SIZE,
		(450.0 - rect.get_center().y) * WORLD_PIXEL_SIZE, 0.0)
	present(_samples)


func set_angle(degrees: float) -> void:
	_angle = degrees
	var radians := deg_to_rad(degrees)
	_camera_3d.position = Vector3(sin(radians) * 6.0, 0.0, cos(radians) * 6.0)
	_camera_3d.look_at(Vector3.ZERO, Vector3.UP)
	present(_samples)


func present(samples: Array) -> void:
	_samples = samples.duplicate(true)
	if _actor.texture == null or _mark_texture == null:
		return
	var active := {}
	var right := _camera_3d.global_basis.x
	var up := _camera_3d.global_basis.y
	var toward_camera := _camera_3d.global_basis.z
	var local_anchor := (_anchor_uv - Vector2(0.5, 0.5)) * _actor_rect.size
	for entry: Dictionary in _samples:
		var key := str(entry["key"])
		var sample: Dictionary = entry["sample"]
		active[key] = true
		if not _puffs.has(key):
			_puffs[key] = _sprite("Puff_" + key, 1)
		var puff: Sprite3D = _puffs[key]
		var frame_texture: Texture2D = entry.get("texture", _mark_texture)
		puff.texture = frame_texture
		puff.pixel_size = _mark_height * WORLD_PIXEL_SIZE / frame_texture.get_height()
		# Automatic billboarding discards a sprite's authored in-plane rotation.
		# Keep the camera-facing plane explicitly, then turn about its center.
		puff.billboard = BaseMaterial3D.BILLBOARD_DISABLED
		puff.centered = true
		var camera_basis := Basis(right, up, toward_camera)
		var local_rotation := Basis(Vector3.BACK, -deg_to_rad(float(sample.get("rotation_degrees", 0.0))))
		puff.basis = camera_basis * local_rotation * Basis.from_scale(Vector3.ONE * float(sample["scale"]))
		var local := local_anchor + _mark_height * Vector2(float(sample["offset_x_ratio"]), float(sample["offset_y_ratio"]))
		puff.position = _actor.position + right * local.x * WORLD_PIXEL_SIZE - up * local.y * WORLD_PIXEL_SIZE + toward_camera * 0.02
		var brightness := float(sample["brightness"])
		puff.modulate = Color(brightness, brightness, brightness, float(sample["opacity"]))
	for key: String in _puffs.keys():
		if not active.has(key):
			var puff: Sprite3D = _puffs[key]
			_world.remove_child(puff)
			puff.queue_free()
			_puffs.erase(key)


func set_preview_visible(enabled: bool) -> void:
	visible = enabled
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS if enabled else SubViewport.UPDATE_DISABLED
	if enabled: sync_resolution()


func sync_resolution() -> void:
	if _viewport == null:
		return
	var extent := get_viewport().get_final_transform().basis_xform(DESIGN_SIZE).abs()
	var output_size := Vector2i(maxi(1, roundi(extent.x)), maxi(1, roundi(extent.y)))
	if _viewport.size != output_size:
		_viewport.size = output_size


func _sprite(node_name: String, priority: int) -> Sprite3D:
	var sprite := Sprite3D.new()
	sprite.name = node_name
	sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	sprite.shaded = false
	sprite.render_priority = priority
	sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_world.add_child(sprite)
	return sprite
