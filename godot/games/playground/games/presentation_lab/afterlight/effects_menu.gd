extends "res://games/presentation_lab/afterlight/study_host.gd"

## The laboratory owns this study menu; effects expose no menu or view API.
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	_ui = Control.new()
	_ui.name = "AfterlightEffectsMenu"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(32, 24, 1216, 96), Color("211b28"))
	_label_text("game.kicker", Rect2(56, 36, 400, 18), 12, ACCENT)
	_label_text("study.effects.title", Rect2(54, 51, 670, 53), 37, INK)
	_build_language_picker(Rect2(758, 52, 248, 40))
	_return_button = _button_text("ui.return_to_story", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("game:bishoujo_afterlight"))
	_label_text("study.effects.heading", Rect2(64, 141, 950, 38), 28, INK)
	_label_text("study.effects.description", Rect2(64, 188, 1090, 28), 18, MUTED)
	var studies := [
		["intertitle_study", "intertitle"],
		["drift_study", "drift"],
		["halo_study", "halo"],
		["actor_motion_study", "motion"],
		["sigh_puff_study", "puff"],
		["sprite_burst_study", "burst"],
		["background_blackout_study", "blackout"],
		["cast_pan_study", "cast_pan"],
		["ambient_particles_study", "ambient"],
		["transmission_voice_study", "transmission_voice"],
	]
	for index in studies.size():
		var entry: Array = studies[index]
		var x := 56.0 + (index % 2) * 596.0
		var y := 226.0 + floorf(float(index) / 2.0) * 105.0
		_panel(Rect2(x, y, 572, 97), Color("251f2e"))
		_label_text("study.%s.title" % entry[1], Rect2(x + 20, y + 8, 530, 25), 19, INK)
		var description := _label_text("study.%s.description" % entry[1], Rect2(x + 20, y + 39, 354, 50), 14, MUTED)
		# The host helper enables wrapping after its initial size assignment.
		description.size = Vector2(354, 50)
		_button_text("ui.explore", Rect2(x + 400, y + 49, 150, 37), _open_study.bind(str(entry[0])))
	_button("Ominous effects", Rect2(646, 780, 294, 48), _open_study.bind("ominous_study"))
	_button("Presentation Lab", Rect2(988, 780, 235, 48), func() -> void: navigate.emit("menu"))
	_button_text("ui.walking_approach", Rect2(64, 780, 235, 48), _open_study.bind("approach_study"))
	_button_text("ui.eye_transitions", Rect2(315, 780, 235, 48), _open_study.bind("eye_study"))


func _refresh_language() -> void:
	_update_language_picker()


func _open_study(route_id: String) -> void:
	navigate.emit(route_id)


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))


func _process(_delta: float) -> void:
	pass


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F6:
		super._input(event)
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE:
		navigate.emit("menu")
		get_viewport().set_input_as_handled()
