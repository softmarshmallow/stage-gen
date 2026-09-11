extends SceneTree

## Concrete host integration: camera/manpu attachment, per-actor materials,
## silhouette coverage and sequential replacement remain compatible together.
const STAGE = preload("res://games/bishoujo_afterlight/cast_stage.gd")
var _errors: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var stage = STAGE.new()
	root.add_child(stage)
	var picture := Image.create(20, 30, false, Image.FORMAT_RGBA8)
	picture.fill(Color(0.7, 0.4, 0.2, 1.0))
	var texture := ImageTexture.create_from_image(picture)
	var profiles: Array = []
	var textures := {}
	for id: String in ["nami", "yuzu", "sena", "riko"]:
		profiles.append({"id": id, "eye_uv": [0.5, 0.14]})
		textures[id] = texture
	_expect(stage.initialize(profiles, textures).is_empty(), "Prepared profiles and manpu must initialize.")
	var pair: Array[String] = ["nami", "yuzu"]
	_expect(stage.set_cast(pair).is_empty(), "The first pair must stage.")
	stage.focus("yuzu")
	stage.mark("yuzu", "surprise")
	stage.set_projection("yuzu", true)
	stage.advance(0.13)
	stage.present(Transform2D.IDENTITY)
	var sprite: TextureRect = stage._sprites["yuzu"]
	var mark: TextureRect = stage._mark_nodes["yuzu:surprise"]
	var actor_before := Rect2(sprite.position, sprite.size)
	var mark_before := Rect2(mark.position, mark.size)
	var camera := Transform2D(Vector2(1.8, 0), Vector2(0, 1.8), Vector2(-480, -200))
	stage.present(camera)
	_expect(Rect2(sprite.position, sprite.size).is_equal_approx(camera * actor_before), "Camera must transform the complete posed actor.")
	_expect(Rect2(mark.position, mark.size).is_equal_approx(camera * mark_before), "Manpu must share camera scale and attachment without screen clamping.")
	_expect(sprite.material != null and stage._sprites["nami"].material == null, "Projection belongs only to its configured actor.")
	var frozen := sprite.position
	stage.present(camera)
	_expect(sprite.position == frozen, "Repeated rendering must not advance focus, marks, or projection clocks.")
	_expect(not stage.handoff("yuzu", "nami", "sena").is_empty(), "Invalid handoff order must fail without replacing the pair.")
	_expect(stage.visible_ids() == pair, "Rejected handoff must preserve active cast.")
	_expect(stage.handoff("nami", "yuzu", "sena").is_empty(), "An ordered pair must begin its sequential replacement.")
	stage.advance(0.2)
	stage.present(Transform2D.IDENTITY)
	var outgoing: TextureRect = stage._sprites["nami"]
	_expect(outgoing.modulate.r < 1.0 and is_equal_approx(outgoing.modulate.a, 1.0), "Departure must darken color while preserving silhouette alpha.")
	_expect(not stage._sprites["sena"].visible, "Arrival must remain absent during departure.")
	stage.advance(8.0)
	stage.present(Transform2D.IDENTITY)
	var next_pair: Array[String] = ["yuzu", "sena"]
	_expect(stage.visible_ids() == next_pair and not stage.is_busy(), "A large delta must settle at survivor/incoming without skipping the resulting cast.")
	_expect(is_equal_approx(stage.get_actor_rect("yuzu").get_center().x, 410.0), "Survivor must end at the original left slot.")
	_expect(is_equal_approx(stage.get_actor_rect("sena").get_center().x, 890.0), "Arrival must end at the right slot.")
	stage.dismiss("sena")
	stage.advance(0.25)
	stage.present(Transform2D.IDENTITY)
	_expect(stage._sprites["sena"].modulate.r < 1.0 and is_equal_approx(stage._sprites["sena"].modulate.a, 1.0), "Standalone dismissal must preserve the same color-before-coverage sequence.")
	stage.set_cast(pair)
	stage.present(Transform2D.IDENTITY)
	_expect(not stage.is_busy() and stage.visible_ids() == pair and stage._marks.is_empty(), "Immediate scene placement must cancel old motion and marks.")
	stage.free()
	for issue: String in _errors:
		printerr("FAIL Afterlight cast stage: " + issue)
	if _errors.is_empty():
		print("PASS Afterlight cast stage: camera/manpu composition, actor-local projection, alpha-matte departure, sequential handoff, cancellation and frozen rendering")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)
