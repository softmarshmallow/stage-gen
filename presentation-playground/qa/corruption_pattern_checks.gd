extends SceneTree

## Native coordinate proof using an emissive area without vignette/refraction.
const FIELD = preload("res://addons/game_presentation/effects/ominous_corruption.gd")
const OUTPUT := "res://qa/corruption-pattern"
var _errors: Array[String] = []
var _metrics: Array[Dictionary] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Corruption pattern checks require native shader rendering.")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	for factor in [1, 2]:
		root.size = Vector2i(1280, 900) * factor
		await _fixture(factor)
	var output := FileAccess.open(OUTPUT.path_join("checks.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"shader_sha256": FileAccess.get_sha256("res://addons/game_presentation/effects/shaders/ominous_corruption.gdshader"), "checks": _metrics, "errors": _errors}, "\t"))
	for issue: String in _errors: printerr("FAIL corruption pattern: " + issue)
	if _errors.is_empty(): print("PASS corruption pattern: native 1x/2x world translation/zoom correspondence, visible emissive motion, fixed UI pixels, clock invariance, atomic transform validation, and reset/cleanup")
	quit(0 if _errors.is_empty() else 1)


func _fixture(factor: int) -> void:
	var holder := Control.new()
	root.add_child(holder)
	var background := ColorRect.new()
	background.color = Color(0.01, 0.01, 0.01)
	background.size = Vector2(1280, 900)
	holder.add_child(background)
	var field := FIELD.new()
	holder.add_child(field)
	_expect(field.configure({"screen": false, "darkness": 0.0, "mist_strength": 0.0, "refraction_px": 0.0, "aura_px": 0.0, "glow_strength": 1.0, "tint": Color.WHITE}).is_empty(), "The isolated emissive field must configure.")
	field.set_rect(Rect2(-512, -512, 2304, 1924))
	field.set_strength(1.0)
	field.set_time(3.75)
	_expect(field.get_pattern_transform() == Transform2D(0.0, Vector2(-512, -512)), "Unbound patterns must default to source-local coordinates.")
	var ui := ColorRect.new()
	ui.color = Color(0.2, 0.7, 0.85)
	ui.position = Vector2(24, 24)
	ui.size = Vector2(220, 54)
	holder.add_child(ui)
	field.set_pattern_transform(Transform2D.IDENTITY)
	var base := await _frame("identity-" + str(factor))
	var translation := Vector2(48, 32)
	_expect(field.set_pattern_transform(Transform2D(0.0, translation)).is_empty(), "World translation must bind without moving the source mask.")
	var shifted := await _frame("translation-" + str(factor))
	_pattern_correspondence(base, shifted, factor, false)
	var zoom := Transform2D(Vector2(2, 0), Vector2(0, 2), Vector2.ONE * (-0.5 / factor))
	_expect(field.set_pattern_transform(zoom).is_empty(), "Positive world zoom must bind.")
	var zoomed := await _frame("zoom-" + str(factor))
	_pattern_correspondence(base, zoomed, factor, true)
	var ui_rect := Rect2i(Vector2(24, 24) * factor, Vector2(220, 54) * factor)
	_expect(base.get_region(ui_rect).get_data() == shifted.get_region(ui_rect).get_data() and base.get_region(ui_rect).get_data() == zoomed.get_region(ui_rect).get_data(), "World movement must not move or shade the later-drawn UI.")
	_expect(field.get_time() == 3.75 and field.get_source_rect() == Rect2(-512, -512, 2304, 1924), "Changing pattern space must not alter the host clock or source-mask geometry.")
	for invalid: Transform2D in [Transform2D(0.1, Vector2.ZERO), Transform2D(Vector2.ZERO, Vector2(0, 1), Vector2.ZERO), Transform2D(Vector2(-1, 0), Vector2(0, 1), Vector2.ZERO), Transform2D(Vector2(1, 0), Vector2(0, 1), Vector2(INF, 0))]:
		_expect(not field.set_pattern_transform(invalid).is_empty() and field.get_pattern_transform() == zoom and field.get_time() == 3.75, "Invalid rotation, singularity, reflection, and nonfinite input must leave the active pattern unchanged.")
	field.reset_pattern_transform()
	_expect(field.get_pattern_transform() == Transform2D(0.0, Vector2(-512, -512)), "Reset must restore source-local behavior.")
	field.set_rect(Rect2(-320, -280, 2304, 1924))
	_expect(field.get_pattern_transform().origin == Vector2(-320, -280), "An unbound pattern must follow later source-rect placement.")
	field.clear()
	_expect(field.get_pattern_transform() == Transform2D.IDENTITY and not field.visible and field.get_strength() == 0.0 and field.get_time() == 0.0, "Clear must remove explicit pattern binding and active effect state.")
	holder.queue_free()
	for frame in 3: await process_frame


func _pattern_correspondence(base: Image, moved: Image, factor: int, zoom: bool) -> void:
	var aligned_error := 0.0
	var stationary_error := 0.0
	var lit_samples := 0
	var count := 0
	for y in range(120 * factor, 360 * factor, 2):
		for x in range(80 * factor, 480 * factor, 2):
			var target := Vector2i(x * 2, y * 2) if zoom else Vector2i(x + 48 * factor, y + 32 * factor)
			var expected := base.get_pixel(x, y)
			var aligned := moved.get_pixelv(target)
			var fixed := moved.get_pixel(x, y)
			aligned_error += _distance(expected, aligned)
			stationary_error += _distance(expected, fixed)
			if expected.r + expected.g + expected.b > 0.1: lit_samples += 1
			count += 1
	var ratio := aligned_error / maxf(0.000001, stationary_error)
	var label := ("zoom" if zoom else "translation") + " " + str(factor) + "x"
	_expect(lit_samples > 20 and stationary_error / count > 0.0001, "The emissive pattern must be visible and move instead of staying screen-fixed: " + label)
	_expect(ratio < 0.20 and aligned_error / count < 0.01, "Transformed pixel positions must preserve the frozen world pattern: " + label + " (error ratio " + str(ratio) + ")")
	_metrics.append({"check": label, "samples": count, "lit_samples": lit_samples, "aligned_mean_error": aligned_error / count, "stationary_mean_error": stationary_error / count, "aligned_to_stationary_ratio": ratio})


func _distance(a: Color, b: Color) -> float:
	return absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b)


func _frame(label: String) -> Image:
	for frame in 3: await process_frame
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	picture.convert(Image.FORMAT_RGBA8)
	_expect(picture.get_size() == root.size, "The coordinate fixture must render at native window resolution.")
	_expect(picture.save_png(OUTPUT.path_join(label + ".png")) == OK, "Pattern capture must save: " + label)
	return picture


func _expect(condition: bool, message: String) -> void:
	if not condition and not _errors.has(message): _errors.append(message)
