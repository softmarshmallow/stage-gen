extends SceneTree


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	var packed := load("res://main.tscn") as PackedScene
	if packed == null:
		push_error("Asset consumer scene could not be loaded.")
		quit(1)
		return
	var scene := packed.instantiate()
	root.add_child(scene)
	await process_frame
	var image := scene.get_node("SuppliedImage") as TextureRect
	if not scene.errors.is_empty() or scene.loaded_size == Vector2i.ZERO or image.texture == null:
		push_error("Asset consumer did not load the supplied image.")
		quit(1)
		return
	print("asset consumer loaded %d x %d" % [scene.loaded_size.x, scene.loaded_size.y])
	quit(0)
