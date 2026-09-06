extends RefCounted

## The 2D layers, headless: the kit's readings of the world, the death sheet
## showing on `dead` with the cause's headline, the craft panel following
## `craft_open` and writing the sim's one-shot inputs, the HUD building a slot
## per pack slot and its card for the chosen one, and every layer taking a
## scale. Nothing is drawn; a Control tree stands up under the dummy display
## server, which is enough to prove the layers build and read.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_ui_layers: could not open %s" % TestHarness.RUN_DIR)
		return
	_kit_reads_items(h, w)
	_kit_names_a_death(h)
	_death_screen_follows_dead(h, w)
	_craft_panel_follows_craft_open(h, w)
	_hud_builds_the_pack(h, w)
	_layers_take_a_scale(h, w)
	_args_carry_the_new_flags(h)


func _kit_reads_items(h: TestHarness, w: World) -> void:
	var m: Dictionary = w.manifest
	h.assert_eq(UiKit.item_name(m, "axe"), "Flint axe", "the display name")
	h.assert_eq(UiKit.item_name(m, "no_such_thing"), "no such thing", "an unknown id opens its underscores")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "berry")), "eat", "berries are eaten")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "poultice")), "apply", "a poultice is applied")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "torch")), "light", "a torch is lit")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "warm_stone")), "warm", "a stone is warmed")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "axe")), "", "a tool has no use button")
	h.assert_eq(UiKit.use_verb(UiKit.item_spec(m, "grass_cloak")), "", "a cloak works from the pack")
	h.assert_eq(UiKit.use_hint(UiKit.item_spec(m, "axe"), {"item": "axe", "count": 1, "uses": 7}),
		"chops · 7 uses left", "a tool's hint counts its uses")
	h.assert_eq(UiKit.use_hint(UiKit.item_spec(m, "cooked_berry"), null),
		"+45 hunger · +10 warmth", "a food's hint lists what it gives")
	h.assert_eq(UiKit.use_hint(UiKit.item_spec(m, "log"), null), "a material", "a log is a material")
	h.assert_eq(UiKit.inv_count([{"item": "log", "count": 3}, null, {"item": "log", "count": 2}], "log"), 5,
		"the pack's count sums the stacks")
	h.assert_eq(UiKit.slot_capacity(m, [{"item": "backpack", "count": 1, "uses": null}], 12), 16,
		"a carried pack adds its slots")
	h.assert_eq(UiKit.clock_text(125.0), "2:05", "the clock text")


func _kit_names_a_death(h: TestHarness) -> void:
	h.assert_eq(UiKit.death_headline("cold"), "You froze.", "the cold's headline")
	h.assert_eq(UiKit.death_headline("hunger"), "You starved.", "the hunger's headline")
	h.assert_eq(UiKit.death_headline("hurt"), "You did not last.", "the hound's headline")
	h.assert_eq(UiKit.death_headline(""), "You did not last.", "an unknown cause still has one")


func _death_screen_follows_dead(h: TestHarness, w: World) -> void:
	var screen := DeathScreen.new()
	screen.setup(SimFixture.package(), w, null)
	h.assert_false(screen.visible, "the sheet is down while the player lives")
	screen.handle_event({"type": "death", "cause": "cold"})
	w.dead = true
	screen.update(w, 0.0, {})
	h.assert_true(screen.visible, "and up once the world says dead")
	h.assert_eq(screen.cause, "cold", "with the event's cause")
	var count := [0]
	screen.restart_requested.connect(func() -> void: count[0] += 1)
	screen._on_begin_again()
	h.assert_eq(count[0], 1, "the button asks for a restart")
	w.dead = false
	screen.update(w, 0.0, {})
	h.assert_false(screen.visible, "a living world takes the sheet down")
	screen.free()


func _craft_panel_follows_craft_open(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.craft_open = false
	w.dead = false
	var panel := CraftPanel.new()
	panel.setup(SimFixture.package(), w, null)
	h.assert_false(panel.visible, "the table is closed")
	w.craft_open = true
	panel.update(w, 0.0, {})
	h.assert_true(panel.visible, "and open with the world's flag")
	var recipes: Array = (w.manifest["crafting"] as Dictionary)["recipes"]
	h.assert_eq(panel._rows.get_child_count(), recipes.size(), "one row per recipe")
	panel._on_craft()
	h.assert_true(bool(w.input["menu_confirm"]), "the Craft button is the sim's confirm")
	panel._on_close()
	h.assert_true(bool(w.input["craft_toggle"]), "the close button is the sim's toggle")
	SimFixture.release(w)
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	panel._on_row_input(click, 3)
	h.assert_eq(w.input["menu_select"], 3, "a clicked row is the sim's select")
	h.assert_false(bool(w.input["menu_confirm"]), "one click does not make")
	panel._on_row_input(click, 3)
	h.assert_true(bool(w.input["menu_confirm"]), "the second click on the same row makes")
	SimFixture.release(w)
	w.craft_open = false
	panel.update(w, 0.0, {})
	h.assert_false(panel.visible, "closed again")
	panel.free()


func _hud_builds_the_pack(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.dead = false
	w.craft_open = false
	Inventory.inv_add(w, "berry", 3)
	Inventory.inv_add(w, "axe", 1)
	w.selected = 0
	var hud := Hud.new()
	hud.setup(SimFixture.package(), w, null)
	h.assert_eq(hud._slot_cells.size(), 12, "a slot per pack slot")
	h.assert_eq(hud._card_name.text, "Berries ×3", "the card names the chosen stack")
	h.assert_false(hud._use_button.disabled, "berries can be used")
	h.assert_eq(hud._use_button.text, "Eat", "and the button says how")
	w.selected = 1
	hud.update(w, 0.0, {})
	h.assert_eq(hud._card_name.text, "Flint axe", "the card follows the selection")
	h.assert_true(hud._use_button.disabled, "a tool has no use")
	h.assert_false(hud._drop_button.disabled, "but can be dropped")
	w.selected = 5
	hud.update(w, 0.0, {})
	h.assert_true(hud._drop_button.disabled, "an empty slot drops nothing")
	Inventory.inv_add(w, "backpack", 1)
	hud.update(w, 0.0, {})
	h.assert_eq(hud._slot_cells.size(), 16, "a carried pack grows the hotbar")
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_RIGHT
	click.pressed = true
	hud._on_slot_input(click, 0)
	h.assert_eq(w.input["select"], 0, "a right-click selects the slot")
	h.assert_true(bool(w.input["use"]), "and uses it")
	SimFixture.release(w)
	hud._on_use()
	h.assert_true(bool(w.input["use"]), "the Use button is the sim's use")
	hud._on_drop()
	h.assert_true(bool(w.input["drop"]), "the Drop button is the sim's drop")
	SimFixture.release(w)
	# The hover names the thing under the pointer.
	var pine := SimFixture.prop(w, "p2", "pine", "grown", 0.0, 1.0)
	w.entities.append(pine)
	hud.set_hover({"entity": pine, "target": Targeting.target_for(w, pine), "point": null}, Vector2(800.0, 450.0))
	hud.update(w, 0.0, {})
	h.assert_true(hud._tooltip_panel.visible, "a hovered pine shows a tip")
	h.assert_true(hud._tooltip.text.find("chop") >= 0, "naming the chop (%s)" % hud._tooltip.text)
	hud.set_hover({})
	hud.update(w, 0.0, {})
	h.assert_false(hud._tooltip_panel.visible, "and none off the world")
	w.dead = true
	hud.update(w, 0.0, {})
	h.assert_false(hud._hotbar_panel.visible, "the dead have no hotbar")
	w.dead = false
	hud.free()


func _layers_take_a_scale(h: TestHarness, w: World) -> void:
	for layer in [Hud.new(), CraftPanel.new(), DeathScreen.new(), WorldMap.new()]:
		layer.setup(SimFixture.package(), w, null)
		layer.set_ui_scale(2.0)
		h.assert_near(layer.transform.get_scale().x, 2.0, 1e-6, "%s scales as a whole" % layer.get_class())
		layer.set_ui_scale(1.0)
		h.assert_near(layer.transform.get_scale().x, 1.0, 1e-6, "and back")
		layer.free()


func _args_carry_the_new_flags(h: TestHarness) -> void:
	var args := RunArgs.parse(PackedStringArray(["--run", "/tmp/r", "--night-floor", "0.38", "--ui-scale", "1.5", "--fullscreen"]))
	h.assert_near(args.night_floor, 0.38, 1e-9, "--night-floor")
	h.assert_near(args.ui_scale, 1.5, 1e-9, "--ui-scale")
	h.assert_true(args.fullscreen, "--fullscreen as a bare flag")
	var plain := RunArgs.parse(PackedStringArray(["--run", "/tmp/r"]))
	h.assert_near(plain.night_floor, 0.0, 1e-9, "the game's night keeps nothing by default")
	h.assert_false(plain.fullscreen, "windowed by default")
	var off := RunArgs.parse(PackedStringArray(["--fullscreen=false", "--run", "/tmp/r"]))
	h.assert_false(off.fullscreen, "--fullscreen=false")
	h.assert_eq(off.run, "/tmp/r", "and the run still parses after it")
