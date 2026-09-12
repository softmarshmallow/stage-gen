extends SceneTree

## Synthetic proof of local catalog admission, per-stage state and subclass
## control callbacks. Actual cast/camera pixels remain covered by game suites.
const PROFILE = preload("res://presentation/stage_profile.gd")
const HOST = preload("res://tests/fixtures/navigation/stage_host.gd")
var _errors: Array[String] = []

class FixtureContent extends RefCounted:
	var documents := {}
	var pictures := {}
	var requested: Array[String] = []

	func read_json(path: String) -> Dictionary:
		requested.append(path)
		return {"value": documents.get(path), "errors": []}

	func load_texture(path: String, _mipmaps: bool) -> Dictionary:
		requested.append(path)
		return {"resource": ImageTexture.create_from_image(pictures[path]) if pictures.has(path) else null, "errors": []}


func _initialize() -> void:
	_run.call_deferred()


func _expect(value: bool, message: String) -> void:
	if not value: _errors.append(message)


func _image(width: int, height: int, alpha: bool = false) -> Image:
	var picture := Image.create(width, height, false, Image.FORMAT_RGBA8 if alpha else Image.FORMAT_RGB8)
	picture.fill(Color(0.2, 0.4, 0.6, 0.5 if alpha else 1.0))
	return picture


func _host() -> Control:
	var host := HOST.new()
	var profile := PROFILE.new()
	var fixture := FixtureContent.new()
	fixture.pictures = {"actor.png": _image(16, 24), "square.png": _image(8, 8, true), "wide.png": _image(12, 8), "place.png": _image(32, 24), "alpha.png": _image(32, 24, true)}
	fixture.documents = {
		"contact.json": {"touch_point": [0.4, 0.3], "touch_radius": 0.05},
		"marks.json": {"manpu": [{"id": "mark", "file": "square.png"}]},
		"places.json": {"locations": [{"id": "place", "name": "Place", "detail": "Detail", "background": "place.png"}]},
	}
	profile.content_loader = fixture
	profile.asset_paths = {"actor": "res://actor.png"}
	profile.contact_actor_id = "actor"
	profile.contact_layout_path = "res://contact.json"
	profile.manpu_catalog_path = "res://marks.json"
	profile.manpu_ids.assign(["mark"])
	profile.location_catalog_path = "res://places.json"
	profile.location_ids.assign(["place"])
	host.stage_profile = profile
	return host


func _run() -> void:
	var host := _host()
	var other := _host()
	host._load_assets()
	host._load_manpu()
	host._load_locations()
	_expect(host._load_errors.is_empty() and host._textures.actor.get_size() == Vector2(16, 24), "Prepared images must retain their dimensions through the adapter.")
	_expect(host._layout_loaded and host._touch_point == Vector2(0.4, 0.3) and is_equal_approx(host._touch_radius, 0.05), "The contact binding belongs to the same local catalog adapter.")
	_expect(host._manpu_textures.mark.get_size() == Vector2(8, 8) and host._location_textures.place.get_size() == Vector2(32, 24), "Catalog textures must retain their independently supplied sizes.")
	_expect(host.stage_profile.content_loader.requested.has("actor.png") and not host.stage_profile.content_loader.requested.has("res://actor.png"), "Historical project prefixes are interpreted only by the local adapter.")
	_expect(other._textures.is_empty() and other._locations.is_empty() and other._load_errors.is_empty(), "Stage instances must not share loaded catalog state or diagnostics.")
	other.stage_profile.content_loader.documents["marks.json"].manpu[0].file = "wide.png"
	other.stage_profile.content_loader.documents["places.json"].locations[0].background = "alpha.png"
	other._load_manpu()
	other._load_locations()
	_expect(other._manpu_textures.is_empty() and other._locations.is_empty() and other._load_errors.size() == 4, "Non-square marks and translucent scenery must be refused, including missing required bindings.")
	_expect(host._load_errors.is_empty(), "Another adapter's refusal must not contaminate a valid stage.")
	host.size = Vector2(1280, 900)
	root.add_child(host)
	host._build_interface()
	host._mode = "dialogue"
	host._layout_interface()
	_expect(host.get_child_count() == 21 and host.get_child(0) == host._title and host.get_child(20) == host._effect_strength_label, "Control construction must preserve the authored child order.")
	_expect(host._title.position == Vector2(32, 22) and host._line.position == Vector2(32, 703) and host._line.size == Vector2(1216, 54), "Control layout must preserve authored dialogue geometry.")
	_expect(host._full_button.position == Vector2(362, 801) and host._full_button.size == Vector2(130, 38), "The lab's primary mode controls retain their fixed-canvas geometry.")
	host._full_button.pressed.emit()
	host._next_button.pressed.emit()
	host._restart_button.pressed.emit()
	_expect(host.actions == ["full_body", "advance", "restart"], "Constructed controls must call the owning subclass exactly once.")
	var elapsed: float = host._elapsed
	var renders: int = host.render_updates
	host._layout_interface()
	_expect(host.render_updates == renders + 1 and host._elapsed == elapsed, "Layout requests rendering without owning a presentation clock.")
	host.queue_free()
	other.free()
	await process_frame
	for issue: String in _errors: printerr("FAIL stage seams: " + issue)
	if _errors.is_empty(): print("PASS stage seams: catalog admission, contact binding, instance isolation, child order, authored layout and subclass callbacks")
	quit(0 if _errors.is_empty() else 1)
