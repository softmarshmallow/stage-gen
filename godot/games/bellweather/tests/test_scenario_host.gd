extends RefCounted

const Program = preload("res://addons/scenario_runtime/program.gd")
const Runtime = preload("res://addons/scenario_runtime/runtime.gd")

func run(h: TestHarness) -> void:
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/sideview_platformer/manifest.json"))
	var world := PlatformerWorld.create(PlatformerMaps.parse(manifest), manifest)
	world.player["x"] = 546.933333333
	world.intent = PlatformerWorld.neutral_intent()
	world.intent["interact"] = true
	world.events.begin_frame()
	PlatformerDialogueSystem.prompt(world, {"dt": 33.0, "now": 2000.0, "frame": 60})
	var saved: Dictionary = PlatformerDialogueSystem.snapshot(world)
	h.assert_eq(saved["scenario"]["kind"], "scenario-runtime-snapshot", "conversation snapshot pins its program")
	var restored := PlatformerWorld.create(PlatformerMaps.parse(manifest), manifest)
	var inventory := restored.inventory.duplicate(true)
	h.assert_true(PlatformerDialogueSystem.restore(restored, JSON.parse_string(JSON.stringify(saved))), "a game can rebind and resume its conversation")
	h.assert_eq(restored.dialogue, world.dialogue, "resume preserves the published dialogue view")
	h.assert_eq(restored.inventory, inventory, "resume does not replay gameplay rewards")
	restored.dialogue_policy["hold_world"] = false
	restored.intent = PlatformerWorld.neutral_intent()
	PlatformerDialogueSystem.update(restored, {"dt": 33.0, "now": 2033.0, "frame": 61})
	h.assert_false(restored.hold, "the game can keep combat running during a conversation")
	restored.dialogue_policy["hold_world"] = true
	PlatformerDialogueSystem.update(restored, {"dt": 33.0, "now": 2066.0, "frame": 62})
	h.assert_true(restored.hold, "Bellweather retains its default conversation hold")
	var invalid := saved.duplicate(true)
	invalid["scenario"]["program_fingerprint"] = "sha256:changed"
	h.assert_false(PlatformerDialogueSystem.restore(restored, invalid), "changed content refuses the saved conversation")
	_portraits(h)
	h.done()

func _portraits(h: TestHarness) -> void:
	var world := PlatformerWorld.new()
	world.scenario = Program.parse({"kind": "scenario-program-v2", "schema_version": 2, "entry": "start", "cast": [{"actor_id": "guide", "expressions": ["neutral", "curious"]}], "endings": [{"outcome_id": "done"}], "blocks": [{"label": "start", "statements": [{"kind": "line", "speaker": "guide", "expression": "curious", "text": "An off-stage speaker."}, {"kind": "end", "outcome": "done"}]}]})
	world.dialogue_state = Runtime.initial_state(world.scenario)
	world.dialogue = {}
	var box := PlatformerDialogueBox.new()
	box._portrait = TextureRect.new()
	box._name = Label.new()
	box._body = Label.new()
	for child: Control in [box._portrait, box._name, box._body]: box.add_child(child)
	box._safe_rect = Rect2(0, 0, 600, 180)
	box._portrait.size = Vector2(144, 180)
	var image := Image.create(16, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color.WHITE)
	box._sheets = {"guide": {"texture": ImageTexture.create_from_image(image), "columns": 2, "rows": 1, "expressions": PackedStringArray(["neutral", "curious"])}}
	box.sync(world)
	h.assert_true(box._portrait.visible, "dialogue portrait does not require stage occupancy")
	h.assert_eq((box._portrait.texture as AtlasTexture).region.position.x, 8.0, "off-stage line selects its authored expression")
	h.assert_true(box._body.size.x < 600, "portrait leaves a text column")
	h.assert_true(box.configure_presentation({"portrait": "none"}).is_empty(), "game can explicitly omit speaker portraits")
	box.sync(world)
	h.assert_false(box._portrait.visible, "omitted portrait is hidden")
	h.assert_eq(box._body.size.x, 600.0, "omitted portrait reflows the text")
	box.free()
